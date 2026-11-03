"use client";
import { useEffect, useRef, useState } from "react";
import { CubeIcon, ArrowsOutSimpleIcon } from "@phosphor-icons/react";
import type { Molecule } from "@/lib/types";
import { errorMessage } from "@/lib/api";

export function MoleculeViewer({ molecule }: { molecule: Molecule }) {
  const container = useRef<HTMLDivElement>(null);
  const reset = useRef<(() => void) | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;
    setError(null);
    void import("3dmol")
      .then((module) => {
        if (disposed || !container.current) return;
        const viewer = module.createViewer(container.current, {
          backgroundColor: "#fafaf7",
          antialias: true,
        });
        viewer.addModel(molecule.xyz, "xyz");
        viewer.setStyle(
          {},
          { stick: { radius: 0.13 }, sphere: { scale: 0.27 } },
        );
        viewer.zoomTo();
        viewer.render();
        reset.current = () => {
          viewer.zoomTo();
          viewer.render();
        };
        const observer = new ResizeObserver(() => {
          viewer.resize();
          viewer.render();
        });
        observer.observe(container.current);
        cleanup = () => {
          observer.disconnect();
          viewer.clear();
          container.current?.replaceChildren();
          reset.current = null;
        };
      })
      .catch((problem: unknown) => {
        if (!disposed) setError(errorMessage(problem));
      });
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [molecule]);
  return (
    <div className="molecule-3d">
      <div
        className="viewer-canvas"
        ref={container}
        aria-label={`${molecule.formula} 的交互式三维结构`}
      />
      <div className="viewer-hint">
        <CubeIcon size={15} />
        拖动旋转 · 滚轮缩放
      </div>
      <button
        className="icon-button viewer-reset"
        onClick={() => reset.current?.()}
        aria-label="重置三维视角"
      >
        <ArrowsOutSimpleIcon size={18} />
      </button>
      {error && (
        <p className="viewer-error" role="alert">
          三维视图不可用：{error}
        </p>
      )}
    </div>
  );
}

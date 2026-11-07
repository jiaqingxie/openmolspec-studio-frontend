"use client";
import { useEffect, useRef, useState } from "react";

export function Molecule3D({ xyz, formula }: { xyz: string | null; formula?: string }) {
  const container = useRef<HTMLDivElement>(null);
  const resetRef = useRef<(() => void) | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;
    setError(null);
    if (!xyz) return;
    void import("3dmol")
      .then((module) => {
        if (disposed || !container.current) return;
        const viewer = module.createViewer(container.current, {
          backgroundColor: "#ffffff",
          antialias: true,
        });
        viewer.addModel(xyz, "mol");
        viewer.setStyle({}, { stick: { radius: 0.14 }, sphere: { scale: 0.28 } });
        viewer.zoomTo();
        viewer.render();
        resetRef.current = () => {
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
          resetRef.current = null;
        };
      })
      .catch((problem: unknown) => {
        if (!disposed) setError(problem instanceof Error ? problem.message : String(problem));
      });
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [xyz]);

  return (
    <div>
      <div
        ref={container}
        className="border rounded bg-white position-relative"
        style={{ height: 360 }}
        aria-label="interactive 3D structure"
      />
      {!xyz && !error && (
        <div
          className="d-flex align-items-center justify-content-center text-secondary border rounded bg-white"
          style={{ height: 360, marginTop: -362, fontSize: "0.85rem", pointerEvents: "none" }}
        >
          awaiting molecule…
        </div>
      )}
      {xyz && (
        <div className="d-flex justify-content-between align-items-center mt-1">
          <span className="text-secondary" style={{ fontSize: "0.75rem" }}>
            drag to rotate · scroll to zoom{formula ? ` · ${formula}` : ""}
          </span>
          <button type="button" className="btn btn-sm btn-outline-secondary py-0" onClick={() => resetRef.current?.()}>
            Reset view
          </button>
        </div>
      )}
      {error && (
        <div className="alert alert-danger py-1 px-2 mt-1 mb-0" style={{ fontSize: "0.8rem" }}>
          3D view unavailable: {error}
        </div>
      )}
    </div>
  );
}

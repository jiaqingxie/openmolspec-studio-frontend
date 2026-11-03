"use client";
import { useRef, useState } from "react";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import type { Ketcher } from "ketcher-core";
import "ketcher-react/dist/index.css";
import { Dialog } from "./dialog";
import { errorMessage } from "@/lib/api";

export default function KetcherEditor({
  smiles,
  onApply,
  onClose,
}: {
  smiles: string;
  onApply: (smiles: string) => Promise<void>;
  onClose: () => void;
}) {
  const editor = useRef<Ketcher | null>(null);
  const [provider] = useState(() => new StandaloneStructServiceProvider());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  async function apply() {
    if (!editor.current) return;
    setError(null);
    setBusy(true);
    try {
      const value = await editor.current.getSmiles();
      if (!value.trim()) throw new Error("请先绘制一个分子");
      await onApply(value);
      onClose();
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      title="绘制分子"
      subtitle="使用 Ketcher 编辑结构，应用后解析分子与三维坐标"
      onClose={onClose}
      wide
    >
      <div className="ketcher-host">
        <Editor
          disableMacromoleculesEditor
          staticResourcesUrl="/"
          structServiceProvider={provider}
          errorHandler={(message: string) => setError(message)}
          onInit={(ketcher) => {
            editor.current = ketcher;
            if (smiles.trim()) {
              void ketcher
                .setMolecule(smiles)
                .catch((problem: unknown) => setError(errorMessage(problem)))
                .finally(() => setReady(true));
            } else setReady(true);
          }}
        />
      </div>
      <div className="editor-footer">
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <button className="button" onClick={onClose}>
          取消
        </button>
        <button
          className="button button-primary"
          disabled={busy || !ready}
          onClick={() => void apply()}
        >
          {!ready ? "编辑器加载中…" : busy ? "正在解析…" : "应用结构"}
        </button>
      </div>
    </Dialog>
  );
}

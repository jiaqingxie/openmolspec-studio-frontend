"use client";
import { useRef, useState } from "react";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import type { Ketcher } from "ketcher-core";
import "ketcher-react/dist/index.css";

export default function KetcherPanel({
  initialSmiles,
  onApply,
}: {
  initialSmiles: string;
  onApply: (smiles: string) => void;
}) {
  const editor = useRef<Ketcher | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [provider] = useState(() => new StandaloneStructServiceProvider());

  async function apply() {
    if (!editor.current) return;
    setError(null);
    try {
      const value = await editor.current.getSmiles();
      if (!value.trim()) throw new Error("canvas is empty");
      onApply(value);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : String(problem));
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="ketcher-host-light h-[430px] overflow-hidden rounded-lg">
        <Editor
          disableMacromoleculesEditor
          staticResourcesUrl="/"
          structServiceProvider={provider}
          errorHandler={(message: string) => setError(message)}
          onInit={(ketcher) => {
            editor.current = ketcher;
            if (initialSmiles.trim()) {
              void ketcher
                .setMolecule(initialSmiles)
                .catch(() => {})
                .finally(() => setReady(true));
            } else {
              setReady(true);
            }
          }}
        />
      </div>
      {error && (
        <p className="text-danger mt-1 mb-1" style={{ fontSize: "0.8rem" }}>
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={() => void apply()}
        disabled={!ready}
        className="btn btn-sm btn-primary mt-1"
      >
        Use this structure
      </button>
    </div>
  );
}

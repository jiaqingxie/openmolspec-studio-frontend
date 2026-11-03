"use client";
import { useRef, useState } from "react";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import type { Ketcher } from "ketcher-core";
import {
  ArrowDownLeftIcon,
  PaperclipIcon,
  SpinnerGapIcon,
} from "@phosphor-icons/react";
import "ketcher-react/dist/index.css";
import { api, errorMessage } from "@/lib/api";
import { setEditorMolecule } from "@/lib/editor";
import type { Attachment } from "@/lib/types";
import { Dialog } from "./dialog";

export default function MoleculeComposer({
  initialSmiles,
  onInsert,
  onAttach,
  signedIn,
  onClose,
}: {
  initialSmiles: string;
  onInsert: (smiles: string) => void;
  onAttach: (attachment: Attachment) => void;
  signedIn: boolean;
  onClose: () => void;
}) {
  const editor = useRef<Ketcher | null>(null);
  const [provider] = useState(() => new StandaloneStructServiceProvider());
  const [smiles, setSmiles] = useState(initialSmiles);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState<"load" | "insert" | "attach" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(!!initialSmiles.trim());

  async function load() {
    if (!editor.current || !smiles.trim() || busy) return;
    setBusy("load");
    setError(null);
    try {
      await setEditorMolecule(editor.current, smiles.trim());
      setDirty(false);
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(null);
    }
  }
  async function apply(action: "insert" | "attach") {
    if (!editor.current || !ready || busy) return;
    setBusy(action);
    setError(null);
    try {
      // A typed SMILES is applied before export, so stale canvas content cannot be sent.
      if (dirty) {
        if (!smiles.trim())
          throw new Error("请先输入 SMILES 或在画布中绘制分子");
        await setEditorMolecule(editor.current, smiles.trim());
        setDirty(false);
      }
      const value = await editor.current.getSmiles();
      if (!value.trim()) throw new Error("请先在画布中绘制一个分子");
      if (action === "insert") onInsert(value.trim());
      else {
        const molecule = await api.resolveMolecule({ smiles: value });
        onAttach(await api.attachMolecule(molecule.id));
      }
      onClose();
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(null);
    }
  }
  return (
    <Dialog
      title="分子编辑器"
      subtitle="画下你的分子，或从一段 SMILES 开始。"
      onClose={() => {
        if (!busy) onClose();
      }}
      wide
    >
      <form
        className="editor-smiles-row"
        onSubmit={(event) => {
          event.preventDefault();
          void load();
        }}
      >
        <label htmlFor="editor-smiles">SMILES</label>
        <input
          id="editor-smiles"
          aria-label="分子 SMILES"
          placeholder="例如 CCO"
          value={smiles}
          disabled={!ready || !!busy}
          onChange={(event) => {
            setSmiles(event.target.value);
            setDirty(true);
          }}
        />
        <button
          className="button"
          type="submit"
          disabled={!ready || !!busy || !smiles.trim()}
        >
          {busy === "load" ? "载入中…" : "载入画布"}
        </button>
      </form>
      <div className="ketcher-host">
        <Editor
          disableMacromoleculesEditor
          staticResourcesUrl="/"
          structServiceProvider={provider}
          errorHandler={(message: string) => setError(message)}
          onInit={(ketcher) => {
            editor.current = ketcher;
            if (initialSmiles.trim())
              void setEditorMolecule(ketcher, initialSmiles)
                .then(() => setDirty(false))
                .catch((problem: unknown) => setError(errorMessage(problem)))
                .finally(() => setReady(true));
            else setReady(true);
          }}
        />
      </div>
      {error && (
        <p className="editor-error error-text" role="alert">
          {error}
        </p>
      )}
      <div className="molecule-editor-footer">
        <span>
          {!ready ? "编辑器加载中…" : "结构准备好后，选择一种方式加入对话"}
        </span>
        <div>
          <button
            className="button"
            disabled={!ready || !!busy}
            onClick={() => void apply("insert")}
          >
            <ArrowDownLeftIcon size={16} />
            插入 SMILES
          </button>
          <button
            className="button button-primary"
            disabled={!signedIn || !ready || !!busy}
            onClick={() => void apply("attach")}
          >
            {busy === "attach" ? (
              <SpinnerGapIcon size={16} className="spin" />
            ) : (
              <PaperclipIcon size={16} />
            )}
            {busy === "attach"
              ? "正在保存…"
              : signedIn
                ? "添加为附件"
                : "登录后可保存附件"}
          </button>
        </div>
      </div>
    </Dialog>
  );
}

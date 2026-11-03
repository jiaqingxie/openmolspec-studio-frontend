"use client";
import { useEffect, useState } from "react";
import {
  CheckIcon,
  CopyIcon,
  PencilSimpleIcon,
  SpinnerGapIcon,
} from "@phosphor-icons/react";
import { errorMessage } from "@/lib/api";
import { loadAttachment, type AttachmentContent } from "@/lib/attachments";
import type { Attachment } from "@/lib/types";
import { Dialog } from "./dialog";
import { MoleculeViewer } from "./molecule-viewer";
import { SpectrumChart } from "./spectrum-chart";

export function AttachmentPreview({
  attachment,
  onClose,
  onEdit,
}: {
  attachment: Attachment;
  onClose: () => void;
  onEdit: (smiles: string) => void;
}) {
  const [content, setContent] = useState<AttachmentContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"2d" | "3d">("2d");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let active = true;
    void loadAttachment(attachment)
      .then((loaded) => {
        if (active) setContent(loaded);
      })
      .catch((problem: unknown) => {
        if (active) setError(errorMessage(problem));
      });
    return () => {
      active = false;
    };
  }, [attachment]);
  return (
    <Dialog
      title={attachment.formula || attachment.name}
      subtitle={
        attachment.kind === "molecule"
          ? "分子结构附件"
          : `${attachment.modality === "raman" ? "Raman" : "IR"} 光谱附件`
      }
      onClose={onClose}
    >
      {!content && !error && (
        <div className="preview-loading" role="status">
          <SpinnerGapIcon size={22} className="spin" />
          正在打开附件…
        </div>
      )}
      {error && (
        <p className="preview-error error-text" role="alert">
          {error}
        </p>
      )}
      {content?.kind === "molecule" && (
        <div className="attachment-preview-body">
          <div className="preview-toolbar">
            <span>
              {content.molecule.formula}
              <small>
                {content.molecule.molecular_weight.toFixed(3)} g/mol
              </small>
            </span>
            <div className="view-toggle" aria-label="结构视图">
              <button
                aria-pressed={view === "2d"}
                onClick={() => setView("2d")}
              >
                2D
              </button>
              <button
                aria-pressed={view === "3d"}
                onClick={() => setView("3d")}
              >
                3D
              </button>
            </div>
          </div>
          <div className="attachment-molecule-view">
            {view === "2d" ? (
              <img
                alt={`${content.molecule.formula} 的二维分子结构`}
                src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(content.molecule.svg)}`}
              />
            ) : (
              <MoleculeViewer molecule={content.molecule} />
            )}
          </div>
          <div className="preview-smiles">
            <span>SMILES</span>
            <code>{content.molecule.smiles}</code>
            <button
              className="icon-button"
              aria-label="复制 SMILES"
              onClick={() => {
                void navigator.clipboard
                  .writeText(content.molecule.smiles)
                  .then(() => setCopied(true))
                  .catch(() => setError("复制失败，请选中 SMILES 后手动复制"));
              }}
            >
              {copied ? <CheckIcon size={16} /> : <CopyIcon size={16} />}
            </button>
          </div>
          {content.molecule.applicability &&
            !content.molecule.applicability.model_eligible && (
              <div className="spectrum-quality">
                <p>此结构可预览。当前结构超出光谱预测模型的适用范围。</p>
                <ul>
                  {content.molecule.applicability.reasons.map(
                    (reason, index) => (
                      <li key={index}>{reason}</li>
                    ),
                  )}
                </ul>
              </div>
            )}
          <div className="preview-footer">
            <span>已保存的结构 · {content.molecule.atom_count} 个原子</span>
            <button
              className="button"
              onClick={() => onEdit(content.molecule.smiles)}
            >
              <PencilSimpleIcon size={15} />
              编辑为新分子
            </button>
          </div>
        </div>
      )}
      {content?.kind === "spectrum" && (
        <div className="attachment-preview-body">
          <SpectrumChart spectrum={content.spectrum} />
          <p className="spectrum-input-note">
            已保存的数据 · {content.spectrum.wavenumber.length} 个采样点
          </p>
        </div>
      )}
    </Dialog>
  );
}

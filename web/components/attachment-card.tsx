"use client";
import { useEffect, useState } from "react";
import {
  AtomIcon,
  ArrowUpRightIcon,
  WaveformIcon,
  XIcon,
} from "@phosphor-icons/react";
import { api } from "@/lib/api";
import type { Attachment } from "@/lib/types";

export function AttachmentCard({
  attachment,
  onOpen,
  onRemove,
}: {
  attachment: Attachment;
  onOpen: () => void;
  onRemove?: () => void;
}) {
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setSvg(null);
    if (attachment.molecule_id)
      void api
        .molecule(attachment.molecule_id)
        .then((molecule) => {
          if (active) setSvg(molecule.svg);
        })
        .catch(() => {
          /* Preview remains openable and shows a useful error. */
        });
    return () => {
      active = false;
    };
  }, [attachment.molecule_id]);
  return (
    <div className={`research-attachment ${attachment.kind}`}>
      <button
        type="button"
        className="attachment-open"
        aria-label={`打开附件 ${attachment.name}`}
        onClick={onOpen}
      >
        <span className="attachment-thumbnail">
          {svg ? (
            <img
              alt=""
              src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`}
            />
          ) : attachment.kind === "molecule" ? (
            <AtomIcon size={24} />
          ) : (
            <WaveformIcon size={25} />
          )}
        </span>
        <span className="attachment-description">
          <strong>{attachment.formula || attachment.name}</strong>
          <small>
            {attachment.kind === "molecule"
              ? "分子结构"
              : `${attachment.modality === "raman" ? "Raman" : "IR"} 光谱`}
            <span>点击查看</span>
          </small>
        </span>
        <ArrowUpRightIcon size={14} className="attachment-arrow" />
      </button>
      {onRemove && (
        <button
          type="button"
          className="attachment-remove"
          aria-label={`移除附件 ${attachment.name}`}
          onClick={onRemove}
        >
          <XIcon size={13} />
        </button>
      )}
    </div>
  );
}

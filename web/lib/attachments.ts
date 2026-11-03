import { api } from "./api.ts";
import type { Attachment, Molecule, Spectrum } from "./types.ts";

export type AttachmentContent =
  | { kind: "molecule"; molecule: Molecule }
  | { kind: "spectrum"; spectrum: Spectrum };

/** Persisted coordinates are scientific inputs: never reconstruct them from SMILES. */
export async function loadAttachment(
  attachment: Attachment,
): Promise<AttachmentContent> {
  if (attachment.kind === "molecule") {
    if (!attachment.molecule_id)
      throw new Error("附件缺少已保存的分子结构，请重新上传");
    return {
      kind: "molecule",
      molecule: await api.molecule(attachment.molecule_id),
    };
  }
  if (!attachment.spectrum_id)
    throw new Error("附件缺少已保存的光谱，请重新上传");
  return {
    kind: "spectrum",
    spectrum: await api.spectrum(attachment.spectrum_id),
  };
}

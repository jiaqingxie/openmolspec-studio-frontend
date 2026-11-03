import type {
  Attachment,
  MessageInput,
  Modality,
  SpectrumMetadata,
} from "./types.ts";

export interface SpectrumReference {
  id: string;
  name: string;
  modality: Modality;
}
export interface PendingUpload {
  id: string;
  file: File;
  modality: Modality;
  metadata?: SpectrumMetadata;
}

export interface ComposerDraft {
  text: string;
  attachments: Attachment[];
  spectra?: SpectrumReference[];
  pendingUploads?: PendingUpload[];
}

/** A send may complete after the user has already started their next question. */
export function settleSubmittedDraft(
  current: ComposerDraft,
  submitted: ComposerDraft,
): ComposerDraft {
  const sentIds = new Set(
    submitted.attachments.map((attachment) => attachment.id),
  );
  return {
    ...current,
    ...(current.spectra && {
      spectra: current.spectra.filter(
        (item) => !submitted.spectra?.some((sent) => sent.id === item.id),
      ),
    }),
    text: current.text === submitted.text ? "" : current.text,
    attachments: current.attachments.filter(
      (attachment) => !sentIds.has(attachment.id),
    ),
  };
}

/** Keep the user's question intact when a modal editor inserts a structure. */
export function insertSmiles(
  draft: string,
  smiles: string,
  range = { start: draft.length, end: draft.length },
): { text: string; caret: number } {
  const before = draft.slice(0, range.start);
  const after = draft.slice(range.end);
  const insertion = `${before && !before.endsWith("\n") ? "\n" : ""}SMILES: ${smiles.trim()}`;
  return {
    text:
      before +
      insertion +
      (after && !after.startsWith("\n") ? "\n" : "") +
      after,
    caret: before.length + insertion.length,
  };
}

export function createMessageInput(
  draft: string,
  attachments: Attachment[],
  spectra: SpectrumReference[] = [],
): MessageInput | null {
  if (!draft.trim() && !attachments.length && !spectra.length) return null;
  return {
    content: draft.trim() || "请查看这些附件，帮我分析其中的分子或光谱信息。",
    mode: "deep",
    ...(spectra.length && {
      context: Object.fromEntries(
        spectra.map(({ modality, id }) => [`${modality}_id`, id]),
      ),
    }),
    attachment_ids: attachments.map((attachment) => attachment.id),
  };
}

export const promptPresets = [
  { label: "预测分子光谱", text: "请预测这个分子的理论 IR 和 Raman 光谱：\n" },
  {
    label: "根据光谱检索分子",
    text: "请根据这份光谱检索候选分子，并说明匹配依据。",
  },
  {
    label: "根据光谱推测结构",
    text: "请根据这份光谱推测可能的分子结构，并说明候选结构的局限。",
  },
  {
    label: "根据光谱估算能隙",
    text: "请根据这份光谱估算 HOMO–LUMO 能隙，并说明模型的适用范围。",
  },
] as const;

export function appendPromptPreset(draft: string, preset: string) {
  return draft.trim() ? `${draft.trimEnd()}\n\n${preset}` : preset;
}

export function agentReadiness(agent?: {
  configured: boolean;
  verified?: boolean;
}) {
  if (!agent) return "服务状态未知";
  if (!agent.configured) return "模型未配置";
  return agent.verified ? "模型已验证" : "模型已配置 · 尚未验证";
}

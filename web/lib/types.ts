export type Operation =
  | "predict_spectra"
  | "retrieve"
  | "predict_gap"
  | "generate";
export type Modality = "ir" | "raman";
export type Mode = "quick" | "deep";
export interface Capabilities {
  device: string;
  root: string;
  domain: "theoretical";
  capabilities: Record<Operation, { available: boolean; detail: string }>;
}
export interface ServiceStatus {
  chemistry: Capabilities | null;
  chemistry_error?: string | { code?: string; message?: string };
  agent: { configured: boolean; verified?: boolean; model: string | null };
  version: string;
}
export interface Attachment {
  id: string;
  name: string;
  kind: "spectrum" | "molecule";
  modality?: Modality;
  spectrum_id?: string;
  molecule_id?: string;
  smiles?: string;
  formula?: string;
  size: number;
}
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  status: "completed" | "running" | "failed";
  attachments: Attachment[];
  tool_calls: Record<string, unknown>[];
  context?: ContextReferences;
}
export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
export interface Conversation extends ConversationSummary {
  messages: Message[];
  active_run_id: string | null;
}
export interface Molecule {
  id: string;
  smiles: string;
  formula: string;
  molecular_weight: number;
  atom_count: number;
  inchi_key: string;
  molblock: string;
  xyz: string;
  applicability?: {
    model_eligible: boolean;
    reasons: string[];
    elements: string[];
  };
  svg: string;
}
export interface SpectrumMetadata {
  axis_unit: "cm^-1" | "nm" | "unknown";
  intensity_unit: string;
  domain: "theoretical" | "experimental" | "unknown";
  axis_mode: "explicit" | "model_grid";
}
export interface Spectrum extends Partial<Omit<SpectrumMetadata, "axis_unit">> {
  axis_unit?: SpectrumMetadata["axis_unit"] | "index";
  id: string;
  name: string;
  modality: Modality;
  wavenumber: number[];
  intensity: number[];
  raw?: {
    wavenumber: number[] | null;
    intensity: number[];
    axis_unit: string;
    intensity_unit: string;
  } | null;
  quality?: { model_eligible: boolean; reasons: string[] };
  processing?: { steps: string[] };
  provenance?: { source?: string; job_id?: string; molecule_id?: string };
}
export interface Job {
  id: string;
  operation: Operation;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  inputs: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  result: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
}
export interface ContextReferences {
  molecule_id?: string;
  smiles?: string;
  ir_id?: string;
  raman_id?: string;
  nmr_h?: number[];
  nmr_c?: number[];
}
export interface MessageInput {
  request_id?: string;
  content: string;
  mode: Mode;
  attachment_ids?: string[];
  context?: ContextReferences;
}
export type RunEvent =
  | {
      event: "run";
      data: { id: string; user_message: Message; assistant_message_id: string };
    }
  | { event: "status"; data: { stage: string; label: string } }
  | {
      event: "tool_start";
      data: { id: string; name: string; args: Record<string, unknown> };
    }
  | {
      event: "tool_end";
      data: { id: string; name: string; result: Record<string, unknown> };
    }
  | { event: "delta"; data: { content: string } }
  | { event: "done"; data: { message: Message; job_ids: string[] } }
  | { event: "error"; data: { code: string; message: string } };
export type PersistedRunEvent = RunEvent & { id: number };

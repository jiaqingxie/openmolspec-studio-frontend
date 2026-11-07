import type { ToolSlug } from "./tools";
import { demoSample, demoPredict, demoCandidates, demoGap, demoGenerate, demoStatus } from "./demo";

export interface StatusResponse {
  device: string;
  tools: Record<ToolSlug, boolean>;
}

export interface SampleMeta {
  sample_id: string;
  source: string;
  smiles: string;
}

export interface SampleResponse {
  ir: number[];
  raman: number[];
  nmr_h: number[];
  nmr_c: number[];
  meta: SampleMeta;
}

export interface MoleculeResponse {
  xyz: string;
  formula: string;
  atoms: number;
  source: string;
}

export interface PredictResponse {
  wavenumber: number[];
  ir: number[];
  raman: number[];
  nmr_h: number[];
  nmr_c: number[];
  modes: { frequency: number; ir_activity: number; raman_activity: number }[];
}

export interface Candidate {
  smiles: string;
  similarity?: number;
  score?: number;
  backend?: string;
}

export interface RetrieveResponse {
  candidates: Candidate[];
}

export interface GapResponse {
  gap_ev: number;
  benchmark_mae_ev: number;
  benchmark_r2_ev: number;
}

export interface GenerateResponse {
  candidates: Candidate[];
  note: string;
}

export interface SpectrumPayload {
  wavenumber?: number[] | null;
  intensity: number[];
}

export interface SpectrumQuery {
  ir?: SpectrumPayload | null;
  raman?: SpectrumPayload | null;
  nmr_h?: number[] | null;
  nmr_c?: number[] | null;
  limit?: number;
}

export interface Result<T> {
  data: T;
  demo: boolean;
}

export const API_BASE =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL
    ? process.env.NEXT_PUBLIC_API_URL
    : "";

async function get<T>(path: string, fallback: () => T): Promise<Result<T>> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return { data: (await response.json()) as T, demo: false };
  } catch {
    return { data: fallback(), demo: true };
  }
}

async function post<T>(path: string, body: unknown, fallback: () => T): Promise<Result<T>> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.detail ?? `HTTP ${response.status}`);
    }
    return { data: (await response.json()) as T, demo: false };
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("HTTP")) throw error;
    return { data: fallback(), demo: true };
  }
}

export const fetchStatus = () => get<StatusResponse>("/api/status", demoStatus);
export const fetchSample = () => get<SampleResponse>("/api/sample", demoSample);
export const resolveMolecule = (smiles: string) =>
  post<MoleculeResponse>("/api/molecule", { smiles }, () => {
    throw new Error("后端不可用");
  });
export const predictSpectra = (smiles: string) =>
  post<PredictResponse>("/api/predict", { smiles }, demoPredict);
export const retrieve = (query: SpectrumQuery) =>
  post<RetrieveResponse>(
    "/api/retrieve",
    query,
    () => ({ candidates: demoCandidates(query.limit ?? 8) }),
  );
export const predictGap = (query: SpectrumQuery) =>
  post<GapResponse>("/api/gap", query, demoGap);
export const generate = (query: SpectrumQuery) =>
  post<GenerateResponse>("/api/generate", query, () => demoGenerate(query.limit ?? 8));
export const structureImageUrl = (smiles: string) =>
  `${API_BASE}/api/render?smiles=${encodeURIComponent(smiles)}`;

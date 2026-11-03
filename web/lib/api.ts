import type { AccessToken, Account, McpEndpoints, Usage } from "./account";
import type {
  Attachment,
  Conversation,
  ConversationSummary,
  Job,
  MessageInput,
  Modality,
  Molecule,
  Operation,
  ServiceStatus,
  Spectrum,
  SpectrumMetadata,
} from "./types";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请稍后重试";
}
async function check(response: Response): Promise<Response> {
  if (response.ok) return response;
  if (response.status === 401 && typeof window !== "undefined")
    window.dispatchEvent(new Event("molspec-session-expired"));
  let message = `请求失败 (${response.status})`;
  let code = "http_error";
  try {
    const body = await response.json();
    if (body.error?.message) {
      message = body.error.message;
      code = body.error.code ?? code;
    } else if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail))
      message = body.detail
        .map((item: { msg?: string }) => item.msg)
        .join("；");
  } catch {
    /* A proxy or disconnected service may return an HTML error. */
  }
  throw new ApiError(message, code, response.status);
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await check(
    await fetch(`/api${path}`, { cache: "no-store", ...init }),
  );
  if (response.status === 204) return undefined as T;
  return response.json();
}
function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
export const api = {
  account: () => request<Account>("/account"),
  mockLogin: (identity: string) =>
    request<void>("/auth/mock", json({ identity })),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  usage: () => request<Usage>("/account/usage"),
  tokens: () => request<{ tokens: AccessToken[] }>("/account/tokens"),
  createToken: (name: string, expires_in_days: number) =>
    request<{ token: string; record: AccessToken }>(
      "/account/tokens",
      json({ name, expires_in_days }),
    ),
  revokeToken: (id: string) =>
    request<void>(`/account/tokens/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  mcpEndpoints: () => request<McpEndpoints>("/integrations/mcp"),
  status: () => request<ServiceStatus>("/status"),
  conversations: () => request<ConversationSummary[]>("/conversations"),
  conversation: (id: string) =>
    request<Conversation>(`/conversations/${encodeURIComponent(id)}`),
  createConversation: () =>
    request<ConversationSummary>("/conversations", json({})),
  deleteConversation: (id: string) =>
    request<void>(`/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  sendMessage: async (id: string, input: MessageInput, signal: AbortSignal) => {
    const path = `/api/conversations/${encodeURIComponent(id)}/messages`;
    const body = json(input);
    for (let attempt = 0; ; attempt++) {
      try {
        return await check(await fetch(path, { ...body, signal }));
      } catch (problem) {
        const transient =
          problem instanceof TypeError ||
          (problem instanceof ApiError && [502, 504].includes(problem.status));
        if (attempt || !input.request_id || signal.aborted || !transient)
          throw problem;
      }
    }
  },
  runEvents: async (id: string, after: number, signal: AbortSignal) =>
    check(
      await fetch(`/api/runs/${encodeURIComponent(id)}/events?after=${after}`, {
        signal,
        cache: "no-store",
      }),
    ),
  cancelRun: (id: string) =>
    request<Record<string, unknown>>(`/runs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  resolveMolecule: (input: { smiles?: string; xyz?: string }) =>
    request<Molecule>("/molecules/resolve", json(input)),
  molecule: (id: string) =>
    request<Molecule>(`/molecules/${encodeURIComponent(id)}`),
  attachMolecule: (id: string) =>
    request<Attachment>("/attachments/molecule", json({ molecule_id: id })),
  spectrum: (id: string) =>
    request<Spectrum>(`/spectra/${encodeURIComponent(id)}`),
  parseSpectrum: (content: string, name: string, modality: Modality) =>
    request<Spectrum>("/spectra/parse", json({ content, name, modality })),
  jobs: () => request<Job[]>("/jobs"),
  job: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
  submitJob: (operation: Operation, inputs: Record<string, unknown>) =>
    request<Job>(
      "/jobs",
      json({ operation, inputs, request_id: crypto.randomUUID() }),
    ),
  cancelJob: (id: string) =>
    request<Job>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  upload: async (
    file: File,
    modality: Modality = "ir",
    metadata?: SpectrumMetadata,
  ) => {
    if (file.size > 10 * 1024 * 1024) throw new Error("文件超过 10 MiB 上限");
    const data = new FormData();
    data.append("file", file);
    data.append("modality", modality);
    if (metadata)
      for (const [key, value] of Object.entries(metadata))
        data.append(key, value);
    return request<Attachment>("/uploads", { method: "POST", body: data });
  },
};

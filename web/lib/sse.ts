import type { PersistedRunEvent } from "./types.ts";

interface SSEFrame {
  id: string;
  event: string;
  data: string;
}

/** Incremental SSE framing. A stream may split at any UTF-8 byte or CRLF boundary. */
export class SSEDecoder {
  private buffer = "";
  private id = "";
  private event = "message";
  private data: string[] = [];

  push(chunk: string): SSEFrame[] {
    this.buffer += chunk;
    const frames: SSEFrame[] = [];
    while (true) {
      const match = /[\r\n]/.exec(this.buffer);
      if (!match) break;
      const at = match.index;
      if (this.buffer[at] === "\r" && at === this.buffer.length - 1) break;
      const line = this.buffer.slice(0, at);
      const size =
        this.buffer[at] === "\r" && this.buffer[at + 1] === "\n" ? 2 : 1;
      this.buffer = this.buffer.slice(at + size);
      if (!line) {
        if (this.data.length)
          frames.push({
            id: this.id,
            event: this.event,
            data: this.data.join("\n"),
          });
        this.id = "";
        this.event = "message";
        this.data = [];
        continue;
      }
      if (line.startsWith(":")) continue;
      const separator = line.indexOf(":");
      const field = separator < 0 ? line : line.slice(0, separator);
      let value = separator < 0 ? "" : line.slice(separator + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "data") this.data.push(value);
      else if (field === "event") this.event = value;
      else if (field === "id" && !value.includes("\0")) this.id = value;
    }
    return frames;
  }
}

const eventNames = new Set([
  "run",
  "status",
  "tool_start",
  "tool_end",
  "delta",
  "done",
  "error",
]);

export async function* readRunEvents(
  response: Response,
): AsyncGenerator<PersistedRunEvent> {
  if (!response.ok) throw new Error(`连接失败 (${response.status})`);
  if (!response.body) throw new Error("服务器未返回事件流");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const sse = new SSEDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const frame of sse.push(decoder.decode(value, { stream: true }))) {
        if (!eventNames.has(frame.event)) continue;
        const id = Number(frame.id);
        if (!Number.isSafeInteger(id) || id < 1)
          throw new Error("服务器事件编号无效");
        let data: unknown;
        try {
          data = JSON.parse(frame.data);
        } catch {
          throw new Error("服务器事件数据无法解析");
        }
        if (!data || typeof data !== "object")
          throw new Error("服务器事件数据无效");
        yield { id, event: frame.event, data } as PersistedRunEvent;
      }
    }
  } finally {
    // A terminal event can end iteration before the server closes the connection.
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

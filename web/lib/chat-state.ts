import type { Message, PersistedRunEvent } from "./types.ts";

export interface ToolProgress {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "running" | "completed";
  result?: Record<string, unknown>;
}
export interface RunState {
  messages: Message[];
  runId: string | null;
  assistantId: string | null;
  lastEventId: number;
  tools: ToolProgress[];
  stage: string;
  error: string | null;
  jobIds: string[];
  terminal: boolean;
}
export function initialRunState(messages: Message[] = []): RunState {
  return {
    messages,
    runId: null,
    assistantId: null,
    lastEventId: 0,
    tools: [],
    stage: "",
    error: null,
    jobIds: [],
    terminal: false,
  };
}
export function applyRunEvent(
  state: RunState,
  event: PersistedRunEvent,
): RunState {
  if (event.id <= state.lastEventId || state.terminal) return state;
  let next = { ...state, lastEventId: event.id };
  switch (event.event) {
    case "run": {
      const { id, user_message, assistant_message_id } = event.data;
      const messages = state.messages.filter(
        (message) => message.id !== assistant_message_id,
      );
      if (!messages.some((message) => message.id === user_message.id))
        messages.push(user_message);
      messages.push({
        id: assistant_message_id,
        role: "assistant",
        content: "",
        created_at: user_message.created_at,
        status: "running",
        attachments: [],
        tool_calls: [],
      });
      next = {
        ...next,
        messages,
        runId: id,
        assistantId: assistant_message_id,
      };
      break;
    }
    case "status":
      next.stage = event.data.label;
      break;
    case "tool_start":
      next.tools = [
        ...state.tools.filter((tool) => tool.id !== event.data.id),
        { ...event.data, status: "running" },
      ];
      break;
    case "tool_end":
      next.tools = state.tools.map((tool) =>
        tool.id === event.data.id
          ? { ...tool, status: "completed", result: event.data.result }
          : tool,
      );
      break;
    case "delta":
      next.messages = state.messages.map((message) =>
        message.id === state.assistantId
          ? { ...message, content: message.content + event.data.content }
          : message,
      );
      break;
    case "done":
      next.messages = [
        ...state.messages.filter(
          (message) => message.id !== event.data.message.id,
        ),
        event.data.message,
      ];
      next.terminal = true;
      next.stage = "";
      next.jobIds = event.data.job_ids;
      break;
    case "error":
      next.error = event.data.message;
      next.terminal = true;
      next.stage = "";
      next.messages = state.messages.map((message) =>
        message.id === state.assistantId
          ? { ...message, status: "failed" }
          : message,
      );
      break;
  }
  return next;
}

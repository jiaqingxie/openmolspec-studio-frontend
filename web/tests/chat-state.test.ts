import { test } from "node:test";
import assert from "node:assert/strict";
import { initialRunState, applyRunEvent } from "../lib/chat-state.ts";
import type { Message, PersistedRunEvent } from "../lib/types.ts";
const user: Message = {
  id: "u1",
  role: "user",
  content: "inspect CCO",
  created_at: "now",
  status: "completed",
  attachments: [],
  tool_calls: [],
};
const start: PersistedRunEvent = {
  id: 1,
  event: "run",
  data: { id: "run1", user_message: user, assistant_message_id: "a1" },
};

test("replays a persisted run without duplicating the existing user or partial assistant", () => {
  const partial: Message = {
    ...user,
    id: "a1",
    role: "assistant",
    content: "old partial",
    status: "running",
  };
  let state = applyRunEvent(initialRunState([user, partial]), start);
  state = applyRunEvent(state, {
    id: 2,
    event: "delta",
    data: { content: "fresh" },
  });
  state = applyRunEvent(state, {
    id: 2,
    event: "delta",
    data: { content: "fresh" },
  });
  assert.equal(state.messages.length, 2);
  assert.equal(state.messages[1].content, "fresh");
  assert.equal(state.lastEventId, 2);
});

test("tracks tool progress and atomically replaces the assistant with the final stored message", () => {
  let state = applyRunEvent(initialRunState(), start);
  state = applyRunEvent(state, {
    id: 2,
    event: "tool_start",
    data: { id: "t1", name: "inspect_molecule", args: { smiles: "CCO" } },
  });
  state = applyRunEvent(state, {
    id: 3,
    event: "tool_end",
    data: { id: "t1", name: "inspect_molecule", result: { molecule_id: "m1" } },
  });
  const final: Message = {
    ...user,
    id: "a1",
    role: "assistant",
    content: "A stored answer",
    tool_calls: [{ id: "t1" }],
  };
  state = applyRunEvent(state, {
    id: 4,
    event: "done",
    data: { message: final, job_ids: ["j1"] },
  });
  assert.deepEqual(state.messages[1], final);
  assert.equal(state.tools[0].status, "completed");
  assert.equal(state.terminal, true);
  assert.deepEqual(state.jobIds, ["j1"]);
});

test("an error is terminal and marks the partial assistant failed", () => {
  let state = applyRunEvent(initialRunState(), start);
  state = applyRunEvent(state, {
    id: 2,
    event: "error",
    data: { code: "unconfigured", message: "Provider not configured" },
  });
  assert.equal(state.terminal, true);
  assert.equal(state.messages[1].status, "failed");
  assert.equal(state.error, "Provider not configured");
});

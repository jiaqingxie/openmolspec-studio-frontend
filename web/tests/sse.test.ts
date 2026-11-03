import { test } from "node:test";
import assert from "node:assert/strict";
import { SSEDecoder, readRunEvents } from "../lib/sse.ts";

test("buffers partial events, CRLF across chunks, and joins data fields", () => {
  const decoder = new SSEDecoder();
  assert.deepEqual(decoder.push(": heartbeat\r\nid: 7\r"), []);
  assert.deepEqual(
    decoder.push('\nevent: delta\r\ndata: {"content":\r\ndata: "hello"}\r\n\r'),
    [],
  );
  assert.deepEqual(decoder.push("\n"), [
    { id: "7", event: "delta", data: '{"content":\n"hello"}' },
  ]);
});

test("does not dispatch an unterminated event or reuse event-specific fields", () => {
  const decoder = new SSEDecoder();
  assert.deepEqual(
    decoder.push("id: 1\nevent: status\ndata: {}\n\ndata: x\n\n"),
    [
      { id: "1", event: "status", data: "{}" },
      { id: "", event: "message", data: "x" },
    ],
  );
  assert.deepEqual(decoder.push("event: delta\ndata: unfinished"), []);
});

test("reads UTF-8 split across chunks and ignores heartbeat frames", async () => {
  const bytes = new TextEncoder().encode(
    ': ping\n\nid: 2\nevent: delta\ndata: {"content":"分子"}\n\n',
  );
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      for (let i = 0; i < bytes.length; i++) c.enqueue(bytes.slice(i, i + 1));
      c.close();
    },
  });
  const events = [];
  for await (const event of readRunEvents(new Response(stream)))
    events.push(event);
  assert.deepEqual(events, [
    { id: 2, event: "delta", data: { content: "分子" } },
  ]);
});

test("fails visibly on malformed persisted data", async () => {
  const response = new Response("id: 3\nevent: delta\ndata: nope\n\n");
  await assert.rejects(async () => {
    for await (const _ of readRunEvents(response)) {
      /* consume */
    }
  }, /事件数据/);
});

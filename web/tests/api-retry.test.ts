import assert from "node:assert/strict";
import { test } from "node:test";
import { api } from "../lib/api.ts";

test("an interrupted POST retry sends the same client-generated request ID and payload", async (t) => {
  const bodies: unknown[] = [];
  t.mock.method(
    globalThis,
    "fetch",
    async (_path: string, init: RequestInit) => {
      bodies.push(JSON.parse(init.body as string));
      if (bodies.length === 1) throw new TypeError("connection reset");
      return new Response("event: run\ndata: {}\n\n", {
        headers: { "X-Run-Id": "persisted-run" },
      });
    },
  );
  const input = {
    content: "比较光谱",
    mode: "deep" as const,
    request_id: "ca9756a5-69ec-4289-a778-6b70b403c0e6",
    context: { ir_id: "saved-ir" },
  };
  const response = await api.sendMessage(
    "conversation",
    input,
    new AbortController().signal,
  );
  assert.deepEqual(bodies, [input, input]);
  assert.equal(response.headers.get("X-Run-Id"), "persisted-run");
});

test("spectrum uploads forward declared domain, units and axis format as multipart fields", async (t) => {
  t.mock.method(
    globalThis,
    "fetch",
    async (path: string, init: RequestInit) => {
      assert.equal(path, "/api/uploads");
      assert.ok(init.body instanceof FormData);
      assert.equal(init.body.get("modality"), "raman");
      assert.equal(init.body.get("axis_unit"), "nm");
      assert.equal(init.body.get("intensity_unit"), "counts");
      assert.equal(init.body.get("domain"), "experimental");
      assert.equal(init.body.get("axis_mode"), "explicit");
      return Response.json({ id: "saved-upload" });
    },
  );
  await api.upload(new File(["532,120\n550,210"], "spectrum.csv"), "raman", {
    axis_unit: "nm",
    intensity_unit: "counts",
    domain: "experimental",
    axis_mode: "explicit",
  });
});

test("each separate calculation submission has its own request ID", async (t) => {
  const ids: string[] = [];
  t.mock.method(
    globalThis,
    "fetch",
    async (path: string, init: RequestInit) => {
      assert.equal(path, "/api/jobs");
      const body = JSON.parse(init.body as string);
      assert.equal(body.operation, "predict_gap");
      assert.deepEqual(body.inputs, { molecule_id: "saved-molecule" });
      assert.match(body.request_id, /^[\da-f-]{36}$/);
      ids.push(body.request_id);
      return Response.json({ id: "job" });
    },
  );
  await api.submitJob("predict_gap", { molecule_id: "saved-molecule" });
  await api.submitJob("predict_gap", { molecule_id: "saved-molecule" });
  assert.notEqual(ids[0], ids[1]);
});

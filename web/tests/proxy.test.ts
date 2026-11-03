import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { proxyApiRequest } from "../lib/proxy.ts";

async function listen(server: http.Server) {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string")
    throw new Error("No TCP address");
  return `http://127.0.0.1:${address.port}`;
}
function close(server: http.Server) {
  server.closeAllConnections();
  return new Promise<void>((resolve) => server.close(() => resolve()));
}

test("runtime proxy preserves raw multipart, path/query, status and headers with a fixed upstream host", async () => {
  let observed: {
    body: string;
    path?: string;
    host?: string;
    contentType?: string;
  } | null = null;
  const upstream = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    observed = {
      body: Buffer.concat(chunks).toString(),
      path: req.url,
      host: req.headers.host,
      contentType: req.headers["content-type"],
    };
    res.writeHead(201, {
      "Content-Type": "application/json",
      "X-Run-Id": "run-7",
      Connection: "keep-alive",
    });
    res.end('{"id":"upload-1"}');
  });
  const target = await listen(upstream);
  const proxy = http.createServer((req, res) => {
    void proxyApiRequest(req, res, target);
  });
  const origin = await listen(proxy);
  try {
    const body =
      '--boundary\r\nContent-Disposition: form-data; name="file"; filename="ir.csv"\r\n\r\n400,0.4\r\n--boundary--';
    const response = await fetch(
      `${origin}/api/uploads?modality=ir&name=a%2Fb`,
      {
        method: "POST",
        headers: {
          "Content-Type": "multipart/form-data; boundary=boundary",
          Host: "untrusted.invalid",
        },
        body,
      },
    );
    assert.equal(response.status, 201);
    assert.equal(response.headers.get("x-run-id"), "run-7");
    assert.deepEqual(await response.json(), { id: "upload-1" });
    assert.deepEqual(observed, {
      body,
      path: "/api/uploads?modality=ir&name=a%2Fb",
      host: new URL(target).host,
      contentType: "multipart/form-data; boundary=boundary",
    });
  } finally {
    await close(proxy);
    await close(upstream);
  }
});

test("runtime proxy streams persisted SSE IDs before upstream completion and closes its reader on disconnect", async () => {
  let disconnected!: () => void;
  const upstreamClosed = new Promise<void>((resolve) => {
    disconnected = resolve;
  });
  const upstream = http.createServer((_req, res) => {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Run-Id": "run-8",
    });
    res.write('id: 1\nevent: status\ndata: {"stage":"working"}\n\n');
    res.on("close", disconnected);
  });
  const target = await listen(upstream);
  const proxy = http.createServer((req, res) => {
    void proxyApiRequest(req, res, target);
  });
  const origin = await listen(proxy);
  try {
    const response = await fetch(`${origin}/api/runs/run-8/events?after=0`);
    assert.equal(response.headers.get("content-type"), "text/event-stream");
    const reader = response.body!.getReader();
    const chunk = await reader.read();
    assert.match(new TextDecoder().decode(chunk.value), /id: 1\nevent: status/);
    await reader.cancel();
    await Promise.race([
      upstreamClosed,
      new Promise((_, reject) => {
        const timer = setTimeout(
          () => reject(new Error("Upstream reader was not released")),
          1500,
        );
        timer.unref();
      }),
    ]);
  } finally {
    await close(proxy);
    await close(upstream);
  }
});

test("unavailable application service produces a structured 502 without exposing internal connection errors", async () => {
  const proxy = http.createServer((req, res) => {
    void proxyApiRequest(req, res, "http://127.0.0.1:1");
  });
  const origin = await listen(proxy);
  try {
    const response = await fetch(`${origin}/api/status`);
    assert.equal(response.status, 502);
    const body = await response.json();
    assert.equal(body.error.code, "api_unavailable");
    assert.doesNotMatch(body.error.message, /ECONNREFUSED|127\.0\.0\.1/);
  } finally {
    await close(proxy);
  }
});

test("runtime proxy forwards session Cookie and preserves separate Set-Cookie headers", async () => {
  let incomingCookie: string | undefined;
  const cookies = [
    "session=new-session; Path=/; HttpOnly; SameSite=Lax",
    "old_session=; Path=/; Max-Age=0",
  ];
  const upstream = http.createServer((req, res) => {
    incomingCookie = req.headers.cookie;
    res.writeHead(204, { "Set-Cookie": cookies });
    res.end();
  });
  const target = await listen(upstream);
  const proxy = http.createServer(
    (req, res) => void proxyApiRequest(req, res, target),
  );
  const origin = await listen(proxy);
  try {
    const response = await fetch(`${origin}/api/auth/mock`, {
      method: "POST",
      headers: { Cookie: "session=old-session" },
    });
    assert.equal(incomingCookie, "session=old-session");
    assert.deepEqual(response.headers.getSetCookie(), cookies);
  } finally {
    await close(proxy);
    await close(upstream);
  }
});

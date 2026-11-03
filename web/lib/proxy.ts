import http, {
  type IncomingHttpHeaders,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";
import https from "node:https";

const hopByHop = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);
function forwardHeaders(headers: IncomingHttpHeaders): IncomingHttpHeaders {
  const blocked = new Set(hopByHop);
  for (const name of (headers.connection ?? "").split(","))
    blocked.add(name.trim().toLowerCase());
  return Object.fromEntries(
    Object.entries(headers).filter(
      ([name]) => !blocked.has(name.toLowerCase()),
    ),
  );
}

/** Transport only: the FastAPI application owns validation, persistence, and run lifetimes. */
export function proxyApiRequest(
  request: IncomingMessage,
  response: ServerResponse,
  baseUrl: string,
): Promise<void> {
  return new Promise((resolve) => {
    let target: URL;
    try {
      target = new URL(baseUrl);
      if (target.protocol !== "http:" && target.protocol !== "https:")
        throw new Error("Invalid API protocol");
      // Only pathname/query come from the request. Its Host header and any absolute URL
      // must never change the configured upstream origin.
      const incoming = new URL(request.url ?? "/api", "http://localhost");
      target.pathname = target.pathname.replace(/\/$/, "") + incoming.pathname;
      target.search = incoming.search;
      target.hash = "";
    } catch {
      response.writeHead(502, {
        "Content-Type": "application/json; charset=utf-8",
      });
      response.end(
        JSON.stringify({
          error: {
            code: "api_configuration",
            message: "应用服务地址配置无效，请检查服务端设置",
          },
        }),
      );
      resolve();
      return;
    }
    const headers = forwardHeaders(request.headers);
    headers.host = target.host;
    const transport = target.protocol === "https:" ? https : http;
    const upstream = transport.request(target, {
      method: request.method,
      headers,
    });
    let upstreamResponse: IncomingMessage | null = null;
    let settled = false;
    function finish() {
      if (!settled) {
        settled = true;
        resolve();
      }
    }
    function disconnect() {
      if (!response.writableEnded) {
        upstreamResponse?.destroy();
        upstream.destroy();
      }
      finish();
    }
    response.once("finish", finish);
    response.once("close", disconnect);
    request.once("aborted", disconnect);
    request.once("error", disconnect);
    upstream.once("response", (incoming) => {
      upstreamResponse = incoming;
      if (response.destroyed) {
        incoming.destroy();
        upstream.destroy();
        finish();
        return;
      }
      response.writeHead(
        incoming.statusCode ?? 502,
        forwardHeaders(incoming.headers),
      );
      response.flushHeaders();
      incoming.once("error", () => {
        response.destroy();
        finish();
      });
      incoming.pipe(response);
    });
    upstream.once("error", () => {
      if (response.destroyed) {
        finish();
        return;
      }
      if (response.headersSent) response.destroy();
      else {
        response.writeHead(502, {
          "Content-Type": "application/json; charset=utf-8",
        });
        response.end(
          JSON.stringify({
            error: {
              code: "api_unavailable",
              message: "暂时无法连接应用服务，请检查服务状态后重试",
            },
          }),
        );
      }
      finish();
    });
    request.pipe(upstream);
  });
}

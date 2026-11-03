import Head from "next/head";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeftIcon, PlugsConnectedIcon } from "@phosphor-icons/react";
import { MolspecMark } from "@/components/brand";
import { CopyButton } from "@/components/copy-button";
import { useAccount } from "@/components/account-session";
import { api, errorMessage } from "@/lib/api";
import type { McpEndpoints } from "@/lib/account";
import type { Operation, ServiceStatus } from "@/lib/types";
import { operationLabels } from "@/lib/science";
import { clientVerification, mcpClients } from "@/lib/mcp-guide";

export default function McpGuide() {
  const { account, openPanel } = useAccount();
  const [endpoints, setEndpoints] = useState<McpEndpoints | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [science, setScience] = useState<ServiceStatus["chemistry"]>();
  const [target, setTarget] = useState<keyof McpEndpoints>("local_url");
  const [selected, setSelected] =
    useState<(typeof mcpClients)[number]["id"]>("codex");
  const client =
    mcpClients.find((item) => item.id === selected) ?? mcpClients[0];
  const url = endpoints?.[target];
  const verified = clientVerification[client.id];
  const load = useCallback(async () => {
    setError(null);
    try {
      setEndpoints(await api.mcpEndpoints());
    } catch (problem) {
      setError(errorMessage(problem));
    }
  }, []);
  useEffect(() => {
    void load();
    void api
      .status()
      .then((status) => setScience(status.chemistry))
      .catch(() => setScience(null));
  }, [load]);
  return (
    <>
      <Head>
        <title>连接外部 Agent · MolSpec</title>
        <meta
          name="description"
          content="在 Codex、Claude Code、DeepSeek Harness 和 WorkBuddy 中配置 MolSpec MCP。"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/molspec-mark.svg" type="image/svg+xml" />
      </Head>
      <main className="mcp-guide">
        <nav aria-label="页面导航">
          <Link href="/">
            <ArrowLeftIcon size={17} />
            返回聊天
          </Link>
          <span>
            <MolspecMark size={26} />
            molspec
          </span>
        </nav>
        <header>
          <span className="mcp-eyebrow">
            <PlugsConnectedIcon size={18} /> MCP 配置指南
          </span>
          <h1>连接外部 Agent</h1>
          <p>
            让你常用的 Agent 调用 MolSpec 的分子与光谱工具。每次实际开始的谱学计算消耗
            1 Credit，额度每天北京时间 00:00 刷新。
          </p>
          <button
            className="button button-primary"
            onClick={() =>
              openPanel(account?.authenticated ? "tokens" : "login")
            }
          >
            {account?.authenticated ? "管理访问令牌" : "登录以生成访问令牌"}
          </button>
        </header>
        <section aria-labelledby="mcp-endpoint-title">
          <h2 id="mcp-endpoint-title">选择服务地址</h2>
          <p>
            本地部署时，客户端需能访问启动配置公布的 MCP
            地址。云端部署使用服务方配置的 HTTPS 入口。
          </p>
          <fieldset className="mcp-targets">
            <legend>部署环境</legend>
            <label>
              <input
                type="radio"
                name="target"
                checked={target === "local_url"}
                onChange={() => setTarget("local_url")}
              />
              本地部署{" "}
              <small>
                {endpoints && (endpoints.local_url ? "已配置" : "未配置")}
              </small>
            </label>
            <label>
              <input
                type="radio"
                name="target"
                checked={target === "cloud_url"}
                onChange={() => setTarget("cloud_url")}
              />
              云端服务{" "}
              <small>
                {endpoints && (endpoints.cloud_url ? "已配置" : "待开放")}
              </small>
            </label>
          </fieldset>
          {error ? (
            <div role="alert">
              <p>{error}</p>
              <button className="button" onClick={() => void load()}>
                重试
              </button>
            </div>
          ) : !endpoints ? (
            <p role="status">正在读取服务地址…</p>
          ) : url ? (
            <code className="mcp-url">{url}</code>
          ) : (
            <p>
              {target === "cloud_url"
                ? "云端服务待开放。"
                : "本地 MCP 地址未配置。请在部署配置中设置客户端可访问的入口。"}
            </p>
          )}
        </section>
        <section aria-labelledby="mcp-client-title">
          <h2 id="mcp-client-title">按客户端配置</h2>
          <div className="mcp-clients" aria-label="客户端">
            {mcpClients.map((item) => (
              <button
                key={item.id}
                className="button"
                aria-pressed={selected === item.id}
                onClick={() => setSelected(item.id)}
              >
                {item.name}
              </button>
            ))}
          </div>
          <article key={client.id}>
            <h3>{client.name}</h3>
            <p>
              {client.version} ·{" "}
              <a href={client.docs} target="_blank" rel="noreferrer">
                官方文档
              </a>
            </p>
            <p>
              <strong>{verified?.status ?? "待验证"}</strong> ·{" "}
              {verified?.detail ??
                "官方文档核对于 2026-11-03。客户端实测日期暂无。"}
            </p>
            <ol>
              {client.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            {client
              .config(url ?? "<部署配置中的 MCP 地址>")
              .map(({ name, value }) => (
                <div className="mcp-config" key={name}>
                  <div>
                    <strong>{name}</strong>
                    {url && !error && (
                      <CopyButton key={url} value={value} label="复制配置" />
                    )}
                  </div>
                  <pre>
                    <code>{value}</code>
                  </pre>
                </div>
              ))}
            <p>
              认证使用 MolSpec 访问令牌，通过 Authorization Bearer 请求头发送。
            </p>
            <h4>连接验证</h4>
            <p>
              客户端列出 MolSpec 工具后，试问「请调用 MolSpec 的
              inspect_molecule
              检查乙醇（CCO），并报告分子式。」工具返回结构信息后，再用
              get_capabilities 查看该部署可用的科学能力。
            </p>
            <p>
              请让 Agent 为每次计费任务生成一个
              request_id。网络重试时沿用原值，主动重新计算时生成新的值。
            </p>
            <h4>常见错误</h4>
            <ul>
              <li>{client.troubleshooting}</li>
              <li>
                401 表示需要检查令牌是否已注入、过期或撤销。请使用 MolSpec
                账户生成的令牌。
              </li>
              <li>
                无法连接时，检查客户端能否访问当前部署的
                URL。缺少模型或数据时，服务会返回相应错误。
              </li>
            </ul>
          </article>
        </section>
        <section aria-labelledby="mcp-science-title">
          <h2 id="mcp-science-title">当前网页部署的科学能力</h2>
          {science === undefined ? (
            <p role="status">正在查询计算服务…</p>
          ) : science ? (
            <ul>
              {(Object.keys(operationLabels) as Operation[]).map(
                (operation) => {
                  const capability = science.capabilities[operation];
                  return (
                    <li key={operation}>
                      {operationLabels[operation]} ·{" "}
                      {capability?.available ? "可用" : "缺少资源"}
                      {!capability?.available && capability?.detail && (
                        <details>
                          <summary>查看缺失项</summary>
                          {capability.detail}
                        </details>
                      )}
                    </li>
                  );
                },
              )}
            </ul>
          ) : (
            <p>暂时无法查询计算服务。</p>
          )}
        </section>
        <p className="mcp-footnote">
          复制配置只代表内容已写入剪贴板。连接状态在客户端确认，科学能力以服务查询结果为准。
        </p>
      </main>
    </>
  );
}

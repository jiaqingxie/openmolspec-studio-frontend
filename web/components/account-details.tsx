import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import type { AccessToken, Account, Usage } from "@/lib/account";
import { Dialog } from "./dialog";
import { CopyButton } from "./copy-button";

export type AccountSection = "usage" | "tokens" | "settings";
const titles = {
  usage: "额度与用量",
  tokens: "访问令牌",
  settings: "账户设置",
};
const usageLabels: Record<string, string> = {
  grant: "免费赠送",
  free_credit_grant: "免费赠送",
  daily_credit_grant: "每日额度刷新",
  agent_reply: "Agent 回复",
  predict_spectra: "预测分子光谱",
  retrieve: "根据光谱检索分子",
  generate: "根据光谱推测结构",
  predict_gap: "估算 HOMO–LUMO 能隙",
  recorded: "已记录",
  reserve: "预留",
  settle: "结算",
  release: "释放",
  reserved: "预留",
  settled: "已结算",
  released: "已释放",
  granted: "已发放",
  web: "网页",
  mcp: "外部 MCP",
  system: "系统",
};
function label(value: string) {
  return usageLabels[value] ?? value;
}
function date(value?: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN") : "—";
}

function UsagePanel() {
  const [data, setData] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api.usage());
    } catch (problem) {
      setError(errorMessage(problem));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <>
      <p>额度每天北京时间 00:00 刷新，剩余额度不累积。网页与外部 MCP 共用额度，每次实际开始的谱学计算消耗 1 Credit。</p>
      <button className="button" onClick={() => void load()}>
        刷新用量
      </button>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">正在读取用量…</p>}
      {data && (
        <>
          <dl className="account-balances">
            <div>
              <dt>可用额度</dt>
              <dd>{data.available} Credits</dd>
            </div>
            <div>
              <dt>预留额度</dt>
              <dd>{data.reserved} Credits</dd>
            </div>
          </dl>
          {data.entries.length ? (
            <div
              className="account-table-scroll"
              role="region"
              aria-label="用量明细"
              tabIndex={0}
            >
              <table className="account-table">
                <thead>
                  <tr>
                    {[
                      "时间",
                      "任务",
                      "来源",
                      "额度变化",
                      "状态",
                      "规则版本",
                      "耗时与模型用量",
                    ].map((heading) => (
                      <th key={heading} scope="col">
                        {heading}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.entries.map((entry, index) => (
                    <tr key={entry.task_id ?? index}>
                      <td>{date(entry.created_at)}</td>
                      <td>
                        {label(entry.operation)}
                        {entry.task_id && (
                          <details>
                            <summary>任务 ID</summary>
                            <code>{entry.task_id}</code>
                          </details>
                        )}
                      </td>
                      <td>{label(entry.source)}</td>
                      <td>
                        {entry.amount > 0 ? "+" : ""}
                        {entry.amount}
                      </td>
                      <td>{label(entry.status)}</td>
                      <td>{entry.rule_version}</td>
                      <td>
                        {entry.duration_ms != null && (
                          <span>{entry.duration_ms} ms</span>
                        )}
                        {entry.usage && (
                          <details>
                            <summary>模型用量</summary>
                            <pre>{JSON.stringify(entry.usage, null, 2)}</pre>
                          </details>
                        )}
                        {entry.duration_ms == null && !entry.usage && "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>暂无用量记录。</p>
          )}
        </>
      )}
    </>
  );
}

function TokensPanel() {
  const [tokens, setTokens] = useState<AccessToken[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<AccessToken | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setTokens((await api.tokens()).tokens);
    } catch (problem) {
      setError(errorMessage(problem));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    const name = String(fields.get("name")).trim();
    if (!name) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.createToken(name, Number(fields.get("days")));
      setSecret(result.token);
      form.reset();
      await load();
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(token: AccessToken) {
    setBusy(true);
    setError(null);
    try {
      await api.revokeToken(token.id);
      setConfirm(null);
      await load();
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p>
        外部 Agent 使用 MolSpec
        访问令牌连接你的账户。请为每个客户端单独创建令牌。
      </p>
      <form
        className="account-actions"
        onSubmit={(event) => void create(event)}
      >
        <label>
          令牌名称
          <input name="name" maxLength={80} required placeholder="例如 Codex" />
        </label>
        <label>
          有效期
          <select name="days" defaultValue="30">
            <option value="7">7 天</option>
            <option value="30">30 天</option>
            <option value="90">90 天</option>
          </select>
        </label>
        <button className="button button-primary" disabled={busy || !!secret}>
          生成令牌
        </button>
      </form>
      {secret && (
        <section className="account-secret" aria-label="新令牌">
          <p role="status">
            令牌明文只显示这一次。请将它保存到客户端的凭据设置中。
          </p>
          <code>{secret}</code>
          <div className="account-actions">
            <CopyButton value={secret} label="复制令牌" />
            <button className="button" onClick={() => setSecret(null)}>
              关闭明文
            </button>
          </div>
        </section>
      )}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {!tokens &&
        (error ? (
          <button className="button" onClick={() => void load()}>
            重试
          </button>
        ) : (
          <p role="status">正在读取令牌…</p>
        ))}
      {tokens && !tokens.length && <p>暂无访问令牌。</p>}
      {tokens?.map((token) => (
        <div className="account-token" key={token.id}>
          <strong>{token.name}</strong>
          <span>
            创建于 {date(token.created_at)} · 到期 {date(token.expires_at)}
          </span>
          <span>最近使用 {date(token.last_used_at)}</span>
          {token.revoked_at ? (
            <span>已撤销 · {date(token.revoked_at)}</span>
          ) : Date.parse(token.expires_at) <= Date.now() ? (
            <span>已过期</span>
          ) : confirm?.id === token.id ? (
            <div className="account-actions">
              <span>撤销后，该令牌会立即失效。</span>
              <button
                className="button"
                disabled={busy}
                onClick={() => void revoke(token)}
              >
                确认撤销
              </button>
              <button
                className="button"
                disabled={busy}
                onClick={() => setConfirm(null)}
              >
                取消
              </button>
            </div>
          ) : (
            <button
              className="button"
              disabled={busy}
              onClick={() => setConfirm(token)}
            >
              撤销
            </button>
          )}
        </div>
      ))}
    </>
  );
}

export function AccountDetails({
  section,
  account,
  onClose,
}: {
  section: AccountSection;
  account: Account;
  onClose: () => void;
}) {
  return (
    <Dialog
      title={titles[section]}
      onClose={onClose}
      wide={section !== "settings"}
    >
      <div className="account-panel">
        {section === "usage" && <UsagePanel />}
        {section === "tokens" && <TokensPanel />}
        {section === "settings" && (
          <dl className="account-balances">
            <div>
              <dt>昵称</dt>
              <dd>{account.user?.nickname}</dd>
            </div>
            <div>
              <dt>登录方式</dt>
              <dd>公司账号{account.mock_enabled ? "（模拟登录）" : ""}</dd>
            </div>
          </dl>
        )}
      </div>
    </Dialog>
  );
}

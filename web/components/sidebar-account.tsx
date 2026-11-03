import Link from "next/link";
import { CaretUpIcon, PlugsConnectedIcon } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { MolspecMark } from "./brand";
import { useAccount } from "./account-session";

export function SidebarAccount() {
  const { account, error, refresh, busy, openPanel, changeSession } =
    useAccount();
  const accountLabel = (
    <>
      <span className="workspace-avatar">
        <MolspecMark size={29} />
      </span>
      <span className="account-trigger-copy">
        <strong>
          {account?.user?.nickname ??
            (account ? "访客" : error ? "账户不可用" : "正在读取账户…")}
        </strong>
        <span>
          {account?.authenticated
            ? account.credits
              ? `${account.credits.available} 免费 Credits`
              : "额度暂不可用"
            : account
              ? "使用公司账号登录"
              : error
                ? "展开重试"
                : "请稍候"}
        </span>
      </span>
    </>
  );

  return (
    <div className="sidebar-bottom account-nav">
      <Link className="integration-link" href="/integrations/mcp">
        <PlugsConnectedIcon size={18} />
        连接外部 Agent
      </Link>
      <details
        className="account-menu"
        onKeyDown={(event) => {
          if (event.key === "Escape" && event.currentTarget.open) {
            event.currentTarget.open = false;
            event.currentTarget.querySelector("summary")?.focus();
          }
        }}
      >
        <summary className="workspace-label account-trigger">
          {accountLabel}
          <CaretUpIcon size={15} aria-hidden />
        </summary>
        <div className="account-menu-actions">
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
          {account?.authenticated ? (
            <>
              <button onClick={() => openPanel("usage")}>额度与用量</button>
              <button onClick={() => openPanel("tokens")}>访问令牌</button>
              <button onClick={() => openPanel("settings")}>账户设置</button>
              <button
                disabled={busy}
                onClick={() => void changeSession(api.logout)}
              >
                退出登录
              </button>
            </>
          ) : account ? (
            <button type="button" onClick={() => openPanel("login")}>去登录</button>
          ) : error ? (
            <button onClick={() => void refresh()}>重试</button>
          ) : (
            <p role="status">正在读取账户…</p>
          )}
        </div>
      </details>
    </div>
  );
}

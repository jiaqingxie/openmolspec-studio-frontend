import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, errorMessage } from "@/lib/api";
import type { Account } from "@/lib/account";
import { Dialog } from "./dialog";
import { AccountDetails, type AccountSection } from "./account-details";

function useAccountSession() {
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [panel, openPanel] = useState<AccountSection | "login" | null>(null);
  const [busy, setBusy] = useState(false);
  const version = useRef(0);
  const changing = useRef(false);
  const refresh = useCallback(async () => {
    if (changing.current) return;
    const request = ++version.current;
    try {
      const current = await api.account();
      if (request === version.current) {
        setAccount(current);
        setError(null);
      }
    } catch (problem) {
      if (request === version.current) setError(errorMessage(problem));
    }
  }, []);
  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 15000);
    const update = () => void refresh();
    window.addEventListener("focus", update);
    window.addEventListener("molspec-session-expired", update);
    return () => {
      ++version.current;
      window.clearInterval(interval);
      window.removeEventListener("focus", update);
      window.removeEventListener("molspec-session-expired", update);
    };
  }, [refresh]);

  async function changeSession(action: () => Promise<void>) {
    if (changing.current) return;
    changing.current = true;
    ++version.current;
    setBusy(true);
    setError(null);
    try {
      await action();
      setAccount(null);
      setAccount(await api.account());
      openPanel(null);
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      changing.current = false;
      setBusy(false);
    }
  }

  return { account, error, panel, openPanel, refresh, busy, changeSession };
}

const AccountContext = createContext<ReturnType<
  typeof useAccountSession
> | null>(null);

export function useAccount() {
  const value = useContext(AccountContext);
  if (!value) throw new Error("Account session provider is required");
  return value;
}

export function AccountSession({ children }: { children: ReactNode }) {
  const session = useAccountSession();
  const { account, error, panel, openPanel, refresh, busy, changeSession } =
    session;
  return (
    <AccountContext.Provider value={session}>
      {children}
      {panel === "login" && (
        <Dialog
          title="使用公司账号登录"
          onClose={() => {
            if (!busy) openPanel(null);
          }}
        >
          <div className="account-panel" aria-busy={busy}>
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
            {account?.mock_enabled ? (
              <>
                <p>模拟登录 · 仅用于开发和测试</p>
                <div className="account-actions">
                  {account.identities.map((identity) => (
                    <button
                      className="button"
                      key={identity.id}
                      disabled={busy}
                      onClick={() =>
                        void changeSession(() => api.mockLogin(identity.id))
                      }
                    >
                      {identity.name}
                    </button>
                  ))}
                </div>
              </>
            ) : account ? (
              <p>公司账号登录尚未配置。</p>
            ) : error ? (
              <button className="button" onClick={() => void refresh()}>
                重试
              </button>
            ) : (
              <p role="status">正在读取登录方式…</p>
            )}
          </div>
        </Dialog>
      )}
      {panel && panel !== "login" && account?.authenticated && (
        <AccountDetails
          key={`${account.user?.id}:${panel}`}
          section={panel}
          account={account}
          onClose={() => openPanel(null)}
        />
      )}
    </AccountContext.Provider>
  );
}

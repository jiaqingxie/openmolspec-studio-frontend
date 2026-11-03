import dynamic from "next/dynamic";
import type { AppProps } from "next/app";
import { useEffect, useState, type SetStateAction } from "react";
import { AccountSession, useAccount } from "@/components/account-session";
import type { ComposerDraft } from "@/lib/composer";
import "@/app/globals.css";
import "@/app/molspec.css";
import "@/app/account.css";

const Workspace = dynamic(
  () => import("@/components/workspace").then((module) => module.Workspace),
  {
    ssr: false,
    loading: () => (
      <main className="initial-loading" aria-busy="true">
        molspec<span>正在打开你的分子研究空间…</span>
      </main>
    ),
  },
);
const emptyDraft: ComposerDraft = { text: "", attachments: [] };
const guest = "guest";

function Studio({ Component, pageProps, router }: AppProps) {
  const { account } = useAccount();
  const userId = account?.authenticated ? account.user?.id : undefined;
  const owner = userId ?? guest;
  const home = router.pathname === "/";
  const [visitedChat, setVisitedChat] = useState(home);
  const [lastOwner, setLastOwner] = useState(owner);
  const [drafts, setDrafts] = useState<Record<string, ComposerDraft>>({});

  useEffect(() => {
    if (home) setVisitedChat(true);
  }, [home]);

  if (owner !== lastOwner) {
    setLastOwner(owner);
    const guestDraft = drafts[guest];
    if (
      owner !== guest &&
      (guestDraft?.text || guestDraft?.pendingUploads?.length)
    ) {
      const previous = drafts[owner] ?? emptyDraft;
      setDrafts({
        ...drafts,
        [guest]: emptyDraft,
        [owner]: {
          ...previous,
          text: [previous.text, guestDraft.text].filter(Boolean).join("\n\n"),
          pendingUploads: [
            ...(previous.pendingUploads ?? []),
            ...(guestDraft.pendingUploads ?? []),
          ],
        },
      });
    }
  }

  function setComposer(value: SetStateAction<ComposerDraft>) {
    setDrafts((previous) => ({
      ...previous,
      [owner]:
        typeof value === "function"
          ? value(previous[owner] ?? emptyDraft)
          : value,
    }));
  }

  return (
    <>
      {(home || visitedChat) && (
        <div hidden={!home}>
          <Workspace
            key={owner}
            userId={userId}
            composer={drafts[owner] ?? emptyDraft}
            setComposer={setComposer}
          />
        </div>
      )}
      <Component {...pageProps} />
    </>
  );
}

export default function App(props: AppProps) {
  return (
    <AccountSession>
      <Studio {...props} />
    </AccountSession>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage } from "./api";
import { applyRunEvent, initialRunState, type RunState } from "./chat-state";
import { readRunEvents } from "./sse";
import type { ConversationSummary, MessageInput } from "./types";

function rememberConversation(userId: string | undefined, id: string | null) {
  if (!userId) return;
  const storageKey = `openmolspec.conversation.${userId}`;
  try {
    if (id) localStorage.setItem(storageKey, id);
    else localStorage.removeItem(storageKey);
  } catch {
    /* Storage can be disabled; server persistence still works. */
  }
  const url = new URL(window.location.href);
  if (url.pathname !== "/") return;
  if (id) url.searchParams.set("conversation", id);
  else url.searchParams.delete("conversation");
  const state = window.history.state;
  const path = url.pathname + url.search + url.hash;
  window.history.replaceState(
    state?.__N ? { ...state, as: path, url: path } : state,
    "",
    url,
  );
}
function wait(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    function abort() {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  });
}

export function useChat(userId: string | undefined) {
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [state, setState] = useState<RunState>(() => initialRunState());
  const [loading, setLoading] = useState(!!userId);
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [connection, setConnection] = useState<
    "idle" | "connected" | "reconnecting" | "disconnected"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const current = useRef(state);
  const selected = useRef<string | null>(null);
  const active = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const updateState = useCallback((next: RunState) => {
    current.current = next;
    setState(next);
  }, []);
  const refreshHistory = useCallback(async () => {
    if (!userId) return;
    try {
      setHistory(await api.conversations());
    } catch (problem) {
      setError(errorMessage(problem));
    }
  }, [userId]);

  const monitor = useCallback(
    async (
      first: Response | null,
      id: string,
      signal: AbortSignal,
      version: number,
    ) => {
      let response = first;
      let failures = 0;
      while (!signal.aborted && version === generation.current) {
        try {
          if (!response) {
            if (!current.current.runId) {
              const stored = await api.conversation(id);
              if (signal.aborted || version !== generation.current) return;
              if (!stored.active_run_id) {
                updateState(initialRunState(stored.messages));
                active.current = false;
                setBusy(false);
                setConnection("idle");
                await refreshHistory();
                return;
              }
              current.current = {
                ...current.current,
                runId: stored.active_run_id,
              };
            }
            response = await api.runEvents(
              current.current.runId!,
              current.current.lastEventId,
              signal,
            );
          }
          if (signal.aborted || version !== generation.current) return;
          setConnection("connected");
          for await (const event of readRunEvents(response)) {
            if (signal.aborted || version !== generation.current) return;
            const next = applyRunEvent(current.current, event);
            updateState(next);
            failures = 0;
            if (next.terminal) {
              active.current = false;
              setBusy(false);
              setConnection("idle");
              await refreshHistory();
              return;
            }
          }
          response = null;
          throw new Error("事件流已断开");
        } catch (problem) {
          if (signal.aborted || version !== generation.current) return;
          response = null;
          failures++;
          if (failures >= 5) {
            setConnection("disconnected");
            setError(
              `${errorMessage(problem)}。服务器中的任务会继续运行，可重新连接查看。`,
            );
            return;
          }
          setConnection("reconnecting");
          try {
            await wait(Math.min(1000 * 2 ** (failures - 1), 8000), signal);
          } catch {
            return;
          }
        }
      }
    },
    [refreshHistory, updateState],
  );

  const openConversation = useCallback(
    async (id: string) => {
      controller.current?.abort();
      const version = ++generation.current;
      const abort = new AbortController();
      controller.current = abort;
      selected.current = id;
      setConversationId(id);
      rememberConversation(userId, id);
      setLoading(true);
      setError(null);
      setConnection("idle");
      active.current = false;
      setBusy(false);
      updateState(initialRunState());
      try {
        const conversation = await api.conversation(id);
        if (abort.signal.aborted || version !== generation.current) return;
        const next = initialRunState(conversation.messages);
        next.runId = conversation.active_run_id;
        updateState(next);
        if (conversation.active_run_id) {
          active.current = true;
          setBusy(true);
          void monitor(null, id, abort.signal, version);
        }
      } catch (problem) {
        if (!abort.signal.aborted) {
          if (problem instanceof ApiError && problem.status === 404) {
            selected.current = null;
            setConversationId(null);
            rememberConversation(userId, null);
          }
          setError(errorMessage(problem));
        }
      } finally {
        if (version === generation.current) setLoading(false);
      }
    },
    [monitor, updateState, userId],
  );

  const newConversation = useCallback(() => {
    controller.current?.abort();
    ++generation.current;
    selected.current = null;
    active.current = false;
    setConversationId(null);
    setBusy(false);
    setLoading(false);
    setConnection("idle");
    setError(null);
    updateState(initialRunState());
    rememberConversation(userId, null);
  }, [updateState, userId]);

  const send = useCallback(
    async (input: MessageInput) => {
      if (active.current) return false;
      active.current = true;
      setBusy(true);
      setError(null);
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      const version = ++generation.current;
      try {
        let id = selected.current;
        if (!id) {
          const conversation = await api.createConversation();
          if (abort.signal.aborted || version !== generation.current)
            return false;
          id = conversation.id;
          selected.current = id;
          setConversationId(id);
          rememberConversation(userId, id);
          setHistory((previous) => [conversation, ...previous]);
        }
        updateState(initialRunState(current.current.messages));
        const request = {
          ...input,
          request_id: input.request_id ?? crypto.randomUUID(),
        };
        const response = await api.sendMessage(id, request, abort.signal);
        if (abort.signal.aborted || version !== generation.current)
          return false;
        const runId = response.headers.get("X-Run-Id");
        if (runId) updateState({ ...current.current, runId });
        void monitor(response, id, abort.signal, version);
        return true;
      } catch (problem) {
        if (abort.signal.aborted || version !== generation.current)
          return false;
        active.current = false;
        setBusy(false);
        setError(errorMessage(problem));
        return false;
      }
    },
    [monitor, updateState, userId],
  );

  const cancelRun = useCallback(async () => {
    const id = current.current.runId;
    if (!id || !active.current || cancelling) return;
    const version = generation.current;
    setCancelling(true);
    try {
      await api.cancelRun(id);
      if (version === generation.current && selected.current)
        await openConversation(selected.current);
    } catch (problem) {
      if (version === generation.current) setError(errorMessage(problem));
    } finally {
      setCancelling(false);
    }
  }, [cancelling, openConversation]);

  const deleteConversation = useCallback(
    async (id: string) => {
      try {
        await api.deleteConversation(id);
        setHistory((previous) => previous.filter((item) => item.id !== id));
        if (selected.current === id) newConversation();
      } catch (problem) {
        setError(errorMessage(problem));
      }
    },
    [newConversation],
  );

  useEffect(() => {
    if (!userId) return;
    const url = new URL(window.location.href);
    let id = url.pathname === "/" ? url.searchParams.get("conversation") : null;
    if (!id) {
      try {
        id = localStorage.getItem(`openmolspec.conversation.${userId}`);
      } catch {
        /* optional */
      }
    }
    void refreshHistory();
    if (id) void openConversation(id);
    else setLoading(false);
    return () => {
      controller.current?.abort();
      ++generation.current;
    };
  }, [openConversation, refreshHistory, userId]);

  return {
    history,
    conversationId,
    state,
    loading,
    busy,
    cancelling,
    cancelRun,
    connection,
    error,
    setError,
    openConversation,
    newConversation,
    send,
    deleteConversation,
    refreshHistory,
  };
}

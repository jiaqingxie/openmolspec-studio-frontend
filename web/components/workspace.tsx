"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type SetStateAction } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowClockwiseIcon,
  ArrowRightIcon,
  ArrowUpIcon,
  AtomIcon,
  CaretDownIcon,
  ChatCircleIcon,
  CheckIcon,
  CubeIcon,
  FlaskIcon,
  ListIcon,
  PaperclipIcon,
  PlusIcon,
  SidebarSimpleIcon,
  SpinnerGapIcon,
  StopIcon,
  TrashIcon,
  WaveformIcon,
  XIcon,
} from "@phosphor-icons/react";
import { api, errorMessage } from "@/lib/api";
import {
  createMessageInput,
  agentReadiness,
  appendPromptPreset,
  promptPresets,
  type SpectrumReference,
  insertSmiles,
  settleSubmittedDraft,
  type ComposerDraft,
  type PendingUpload,
} from "@/lib/composer";
import { useChat } from "@/lib/use-chat";
import { toolLabels } from "@/lib/science";
import type {
  Attachment,
  Message,
  Modality,
  ServiceStatus,
  Spectrum,
  SpectrumMetadata,
} from "@/lib/types";
import type { ToolProgress } from "@/lib/chat-state";
import { AttachmentCard } from "./attachment-card";
import { AttachmentPreview } from "./attachment-preview";
import { CalculationResults } from "./calculation-results";
import { SpectrumUpload } from "./spectrum-upload";
import { SpectrumChart } from "./spectrum-chart";
import { StatusDialog } from "./status-dialog";
import { Dialog } from "./dialog";
import { MolspecMark } from "./brand";
import { useAccount } from "./account-session";
import { SidebarAccount } from "./sidebar-account";

const MoleculeComposer = dynamic(() => import("./molecule-composer"), {
  ssr: false,
  loading: () => (
    <div className="loading-overlay" role="status">
      <SpinnerGapIcon size={22} className="spin" />
      正在打开分子编辑器…
    </div>
  ),
});

function jobIdsFromCalls(calls: { result?: unknown }[]) {
  return [
    ...new Set(
      calls.flatMap((call) => {
        const result = call.result;
        return result &&
          typeof result === "object" &&
          "job_id" in result &&
          typeof result.job_id === "string"
          ? [result.job_id]
          : [];
      }),
    ),
  ];
}

function ToolProgressView({ tools }: { tools: ToolProgress[] }) {
  if (!tools.length) return null;
  return (
    <div className="tool-progress">
      {tools.map((tool) => (
        <details key={tool.id} className="tool-step">
          <summary>
            {tool.status === "running" ? (
              <SpinnerGapIcon size={16} className="spin" />
            ) : (
              <CheckIcon size={16} />
            )}
            <span>{toolLabels[tool.name] ?? tool.name}</span>
            <small>{tool.status === "running" ? "进行中" : "已返回"}</small>
            <CaretDownIcon size={13} />
          </summary>
          <div className="tool-data">
            <strong>输入</strong>
            <pre>{JSON.stringify(tool.args, null, 2)}</pre>
            {tool.result && (
              <>
                <strong>工具返回</strong>
                <pre>{JSON.stringify(tool.result, null, 2)}</pre>
              </>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}

function ChatMessage({
  message,
  tools,
  running,
  stage,
  onAttachment,
  onResults,
  onSpectrum,
}: {
  message: Message;
  tools?: ToolProgress[];
  running?: boolean;
  stage?: string;
  onAttachment: (attachment: Attachment) => void;
  onResults: (ids: string[]) => void;
  onSpectrum: (id: string) => void;
}) {
  const user = message.role === "user";
  const jobIds = jobIdsFromCalls(tools || message.tool_calls);
  return (
    <article
      className={`message ${user ? "message-user" : "message-assistant"}`}
    >
      {!user && (
        <div className="assistant-label">
          <MolspecMark size={30} />
          <strong>molspec</strong>
          {message.status === "failed" && (
            <span className="failed-label">本次回答已中断</span>
          )}
        </div>
      )}
      {message.attachments?.length > 0 && (
        <div className="message-attachments">
          {message.attachments.map((attachment) => (
            <AttachmentCard
              key={attachment.id}
              attachment={attachment}
              onOpen={() => onAttachment(attachment)}
            />
          ))}
        </div>
      )}
      {user &&
        (["ir", "raman"] as const).map((modality) => {
          const id = message.context?.[`${modality}_id`];
          if (
            !id ||
            message.attachments?.some((item) => item.spectrum_id === id)
          )
            return null;
          return (
            <button
              key={modality}
              className="button"
              onClick={() => onSpectrum(id)}
            >
              {modality === "ir" ? "IR" : "Raman"} 光谱
            </button>
          );
        })}
      {!user && tools && <ToolProgressView tools={tools} />}
      {!user && !tools?.length && message.tool_calls?.length > 0 && (
        <details className="stored-tools">
          <summary>
            <FlaskIcon size={15} />
            {message.tool_calls.length} 项分析记录
            <CaretDownIcon size={13} />
          </summary>
          <pre>{JSON.stringify(message.tool_calls, null, 2)}</pre>
        </details>
      )}
      {message.content && (
        <div className={`message-content ${user ? "" : "markdown"}`}>
          {user ? (
            message.content
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ children, ...props }) => (
                  <a {...props} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>
      )}
      {running && (
        <div className="stream-status" role="status">
          <span className="thinking-dot" />
          {stage || "正在思考…"}
        </div>
      )}
      {!message.content && !running && message.status === "failed" && (
        <p className="error-text">
          暂时无法完成回答，请稍后重试。你的问题与附件已保存。
        </p>
      )}
      {!user && jobIds.length > 0 && (
        <button
          className="view-calculations text-button"
          onClick={() => onResults(jobIds)}
        >
          <FlaskIcon size={16} />
          查看 {jobIds.length} 项计算结果
          <ArrowRightIcon size={15} />
        </button>
      )}
    </article>
  );
}

export function Workspace({
  userId,
  composer,
  setComposer,
}: {
  userId?: string;
  composer: ComposerDraft;
  setComposer: (draft: SetStateAction<ComposerDraft>) => void;
}) {
  const chat = useChat(userId);
  const { account, openPanel, refresh } = useAccount();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const {
    text: draft,
    attachments,
    spectra = [],
    pendingUploads = [],
  } = composer;
  const composerVersion = useRef(0);
  function setDraft(text: string) {
    setComposer((previous) => ({ ...previous, text }));
  }
  function setAttachments(value: SetStateAction<Attachment[]>) {
    setComposer((previous) => ({
      ...previous,
      attachments:
        typeof value === "function" ? value(previous.attachments) : value,
    }));
  }
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusOpen, setStatusOpen] = useState(false);
  const [spectrumFile, setSpectrumFile] = useState<File | null>(null);
  const [spectrumPreview, setSpectrumPreview] = useState<Spectrum | null>(null);
  async function refreshStatus() {
    try {
      setStatus(await api.status());
      setStatusError(null);
    } catch (problem) {
      setStatus(null);
      setStatusError(errorMessage(problem));
    }
  }
  useEffect(() => {
    void refreshStatus();
    const interval = setInterval(() => void refreshStatus(), 15000);
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    if (chat.state.terminal) {
      void refreshStatus();
      void refresh();
    }
  }, [chat.state.terminal, refresh]);

  const [uploading, setUploading] = useState(false);
  const [attachmentMenu, setAttachmentMenu] = useState(false);
  const [uploadModality, setUploadModality] = useState<Modality>("ir");
  const [uploadKind, setUploadKind] = useState<"spectrum" | "molecule">(
    "spectrum",
  );
  const [editor, setEditor] = useState<{ smiles: string } | null>(null);
  const [preview, setPreview] = useState<Attachment | null>(null);
  const [resultIds, setResultIds] = useState<string[] | null>(null);
  const insertionRange = useRef<{ start: number; end: number } | undefined>(
    undefined,
  );
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const lastMessageId = useRef<string | undefined>(undefined);
  const attachmentPopover = useRef<HTMLDivElement>(null);
  const selectedConversation = chat.history.find(
    (item) => item.id === chat.conversationId,
  );
  const hasMessages = chat.state.messages.length > 0;
  const canSend =
    (!!draft.trim() || attachments.length > 0 || spectra.length > 0) &&
    (status?.agent.configured !== false || !userId) &&
    !pendingUploads.length &&
    !chat.busy &&
    !chat.loading &&
    !uploading;

  useEffect(() => {
    const latestId = chat.state.messages.at(-1)?.id;
    if (latestId !== lastMessageId.current || nearBottom.current)
      bottom.current?.scrollIntoView({ behavior: "instant", block: "end" });
    lastMessageId.current = latestId;
  }, [chat.state.messages, chat.state.tools, chat.state.stage]);
  useEffect(() => {
    if (!attachmentMenu) return;
    function close(event: PointerEvent) {
      if (!attachmentPopover.current?.contains(event.target as Node))
        setAttachmentMenu(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setAttachmentMenu(false);
    }
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [attachmentMenu]);
  useEffect(() => {
    if (!sidebarOpen) return;
    function close(event: KeyboardEvent) {
      if (event.key === "Escape") setSidebarOpen(false);
    }
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [sidebarOpen]);

  function newChat() {
    ++composerVersion.current;
    chat.newConversation();
    setComposer({ text: "", attachments: [] });
    setSpectrumFile(null);
    setSpectrumPreview(null);
    setUploading(false);
    setSidebarOpen(false);
    setAttachmentMenu(false);
    textarea.current?.focus();
  }
  function openEditor(smiles = "") {
    const input = textarea.current;
    insertionRange.current = input
      ? { start: input.selectionStart, end: input.selectionEnd }
      : undefined;
    setPreview(null);
    setResultIds(null);
    setAttachmentMenu(false);
    setSidebarOpen(false);
    setEditor({ smiles });
  }
  function addSmiles(smiles: string) {
    const insertion = insertSmiles(draft, smiles, insertionRange.current);
    setDraft(insertion.text);
    requestAnimationFrame(() => {
      textarea.current?.focus();
      textarea.current?.setSelectionRange(insertion.caret, insertion.caret);
    });
  }
  function addAttachment(attachment: Attachment) {
    if (attachments.length >= 20) {
      chat.setError("一次最多添加 20 个附件");
      return;
    }
    setAttachments((previous) => [...previous, attachment]);
    requestAnimationFrame(() => textarea.current?.focus());
  }
  async function send() {
    if (!canSend) return;
    if (!userId) {
      openPanel("login");
      return;
    }
    const version = composerVersion.current;
    const submitted = composer;
    const input = createMessageInput(draft, attachments, spectra);
    if (
      input &&
      (await chat.send(input)) &&
      version === composerVersion.current
    ) {
      setComposer((current) => settleSubmittedDraft(current, submitted));
      setAttachmentMenu(false);
      nearBottom.current = true;
    }
  }
  function selectUpload(
    kind: "spectrum" | "molecule",
    modality: Modality = "ir",
  ) {
    setUploadKind(kind);
    setUploadModality(modality);
    setAttachmentMenu(false);
    requestAnimationFrame(() => fileInput.current?.click());
  }
  async function inspectSpectrum(id: string) {
    const version = composerVersion.current;
    try {
      const spectrum = await api.spectrum(id);
      if (version === composerVersion.current) setSpectrumPreview(spectrum);
    } catch (problem) {
      if (version === composerVersion.current)
        chat.setError(errorMessage(problem));
    }
  }
  function useSpectrum(reference: SpectrumReference) {
    setComposer((previous) => ({
      ...previous,
      spectra: [
        ...(previous.spectra ?? []).filter(
          (item) => item.modality !== reference.modality,
        ),
        reference,
      ],
    }));
    setResultIds(null);
    requestAnimationFrame(() => textarea.current?.focus());
  }
  function removePendingUpload(id: string) {
    setComposer((previous) => ({
      ...previous,
      pendingUploads: previous.pendingUploads?.filter((item) => item.id !== id),
    }));
  }

  async function upload(
    file: File,
    metadata?: SpectrumMetadata,
    pending?: PendingUpload,
  ) {
    if (!userId) {
      if (pendingUploads.length >= 20) {
        chat.setError("一次最多添加 20 个附件");
        return;
      }
      const entry = {
        id: crypto.randomUUID(),
        file,
        modality: uploadModality,
        metadata,
      };
      setComposer((previous) => ({
        ...previous,
        pendingUploads: [...(previous.pendingUploads ?? []), entry],
      }));
      openPanel("login");
      return;
    }
    if (attachments.length >= 20) {
      chat.setError("一次最多添加 20 个附件");
      return;
    }
    const version = composerVersion.current;
    setUploading(true);
    chat.setError(null);
    try {
      const attachment = await api.upload(
        file,
        pending?.modality ?? uploadModality,
        metadata,
      );
      if (version === composerVersion.current) {
        addAttachment(attachment);
        if (pending) removePendingUpload(pending.id);
      }
    } catch (problem) {
      if (version === composerVersion.current)
        chat.setError(errorMessage(problem));
    } finally {
      if (version === composerVersion.current) setUploading(false);
    }
  }

  return (
    <div
      className={`app-shell molspec-shell ${collapsed ? "sidebar-collapsed" : ""}`}
    >
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="收起导航"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`sidebar ${sidebarOpen ? "mobile-open" : ""}`}
        aria-label="主导航"
      >
        <div className="sidebar-brand">
          <button className="brand" onClick={newChat} aria-label="molspec 首页">
            <MolspecMark size={45} />
            <span>
              molspec<small>你的分子研究伙伴</small>
            </span>
          </button>
          <button
            className="icon-button sidebar-toggle"
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
            onClick={() => {
              setCollapsed(!collapsed);
              setSidebarOpen(false);
            }}
          >
            <SidebarSimpleIcon size={19} />
          </button>
        </div>
        <button className="new-chat" onClick={newChat} title="新建对话">
          <PlusIcon size={20} />
          <span>新建对话</span>
        </button>
        <div className="history-heading">
          <span>最近对话</span>
          <button
            className="icon-button"
            aria-label="刷新对话列表"
            onClick={() => void chat.refreshHistory()}
          >
            <ArrowClockwiseIcon size={15} />
          </button>
        </div>
        <div className="conversation-history">
          {chat.history.length ? (
            chat.history.map((item) => (
              <div
                key={item.id}
                className={`history-row ${chat.conversationId === item.id ? "selected" : ""}`}
              >
                <button
                  className="history-link"
                  title={item.title}
                  onClick={() => {
                    ++composerVersion.current;
                    void chat.openConversation(item.id);
                    setSidebarOpen(false);
                    setComposer({ text: "", attachments: [] });
                    setSpectrumFile(null);
                    setSpectrumPreview(null);
                    setUploading(false);
                    setAttachmentMenu(false);
                  }}
                >
                  <ChatCircleIcon size={15} />
                  <span>{item.title}</span>
                </button>
                <button
                  className="history-delete icon-button"
                  title="删除对话"
                  aria-label={`删除对话 ${item.title}`}
                  disabled={chat.conversationId === item.id && chat.busy}
                  onClick={() => void chat.deleteConversation(item.id)}
                >
                  <TrashIcon size={14} />
                </button>
              </div>
            ))
          ) : (
            <div className="history-empty">
              <ChatCircleIcon size={21} weight="light" />
              <p>一点好奇，一个新发现</p>
              <span>对话会保存在这里</span>
            </div>
          )}
        </div>
        <SidebarAccount />
      </aside>
      <main className="main-canvas">
        <header className="main-topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu"
              aria-label="打开导航菜单"
              aria-expanded={sidebarOpen}
              onClick={() => setSidebarOpen(true)}
            >
              <ListIcon size={23} />
            </button>
            {collapsed && (
              <button
                className="icon-button desktop-expand"
                onClick={() => setCollapsed(false)}
                aria-label="展开导航"
              >
                <SidebarSimpleIcon size={20} />
              </button>
            )}
            <span className="workspace-breadcrumb">
              {hasMessages
                ? (selectedConversation?.title ?? "新的探索")
                : "分子与光谱，聊聊就好"}
            </span>
          </div>
          <span className="topbar-wordmark">
            molspec<span>●</span>
          </span>
        </header>
        <div
          className={`chat-area ${hasMessages ? "has-messages" : "is-empty"}`}
        >
          {!hasMessages && !chat.loading && (
            <section className="welcome">
              <div className="welcome-identity">
                <MolspecMark size={106} />
                <span>molspec</span>
              </div>
              <h1>从一个分子，开始探索</h1>
              <p>画下结构、上传光谱，或直接聊聊你的问题。</p>
            </section>
          )}
          {chat.loading && (
            <div className="conversation-loading" role="status">
              <SpinnerGapIcon className="spin" size={23} />
              <span>正在读取对话…</span>
            </div>
          )}
          {hasMessages && (
            <div
              className="messages-scroll"
              onScroll={(event) => {
                const element = event.currentTarget;
                nearBottom.current =
                  element.scrollHeight -
                    element.scrollTop -
                    element.clientHeight <
                  110;
              }}
            >
              <div
                className="messages"
                role="log"
                aria-label="对话记录"
                aria-live="polite"
                aria-relevant="additions"
              >
                {chat.state.messages.map((message) => (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    tools={
                      message.id === chat.state.assistantId
                        ? chat.state.tools
                        : undefined
                    }
                    running={
                      message.id === chat.state.assistantId &&
                      chat.busy &&
                      !chat.state.terminal
                    }
                    stage={chat.state.stage}
                    onAttachment={setPreview}
                    onResults={setResultIds}
                    onSpectrum={(id) => void inspectSpectrum(id)}
                  />
                ))}
                <div ref={bottom} />
              </div>
            </div>
          )}
          <div className="composer-area">
            {(chat.error || chat.state.error) && (
              <div className="chat-error" role="alert">
                <span>{chat.error || chat.state.error}</span>
                {chat.connection === "disconnected" && chat.conversationId && (
                  <button
                    className="text-button"
                    onClick={() =>
                      void chat.openConversation(chat.conversationId!)
                    }
                  >
                    重新连接
                  </button>
                )}
                {chat.error && (
                  <button
                    className="icon-button"
                    aria-label="关闭错误提示"
                    onClick={() => chat.setError(null)}
                  >
                    <XIcon size={16} />
                  </button>
                )}
              </div>
            )}
            <form
              className={`composer ${chat.busy ? "composer-busy" : ""}`}
              onSubmit={(event) => {
                event.preventDefault();
                void send();
              }}
            >
              {(attachments.length > 0 ||
                spectra.length > 0 ||
                pendingUploads.length > 0 ||
                uploading) && (
                <div className="composer-attachments">
                  {pendingUploads.map((item) => (
                    <span className="attachment-chip" key={item.id}>
                      <PaperclipIcon size={15} />
                      <span>{item.file.name} · 待保存</span>
                      <button
                        type="button"
                        className="text-button"
                        disabled={uploading || chat.busy}
                        onClick={() =>
                          userId
                            ? void upload(item.file, item.metadata, item)
                            : openPanel("login")
                        }
                      >
                        {userId ? "保存附件" : "登录后保存"}
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        disabled={uploading}
                        aria-label={`移除 ${item.file.name}`}
                        onClick={() => removePendingUpload(item.id)}
                      >
                        <XIcon size={14} />
                      </button>
                    </span>
                  ))}
                  {attachments.map((attachment) => (
                    <AttachmentCard
                      key={attachment.id}
                      attachment={attachment}
                      onOpen={() => setPreview(attachment)}
                      onRemove={() =>
                        setAttachments((previous) =>
                          previous.filter((item) => item.id !== attachment.id),
                        )
                      }
                    />
                  ))}
                  {spectra.map((item) => (
                    <span className="attachment-chip" key={item.id}>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => void inspectSpectrum(item.id)}
                      >
                        {item.name}
                      </button>
                      <button
                        type="button"
                        aria-label={`移除 ${item.name}`}
                        onClick={() =>
                          setComposer((previous) => ({
                            ...previous,
                            spectra: previous.spectra?.filter(
                              (reference) => reference.id !== item.id,
                            ),
                          }))
                        }
                      >
                        <XIcon size={13} />
                      </button>
                    </span>
                  ))}
                  {uploading && (
                    <span className="attachment-chip">
                      <SpinnerGapIcon className="spin" size={14} />
                      正在解析文件…
                    </span>
                  )}
                </div>
              )}
              <textarea
                ref={textarea}
                aria-label="输入光谱研究问题"
                placeholder="想了解哪个分子？写下问题，或画一个给我…"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    void send();
                  }
                }}
                disabled={chat.loading}
                rows={3}
              />
              <div className="composer-controls">
                <div className="composer-left">
                  <div
                    className="attachment-popover-anchor"
                    ref={attachmentPopover}
                  >
                    <button
                      type="button"
                      className={`icon-button attach-button ${attachmentMenu ? "selected" : ""}`}
                      aria-label="添加附件"
                      aria-expanded={attachmentMenu}
                      onClick={() => setAttachmentMenu(!attachmentMenu)}
                      disabled={
                        uploading ||
                        chat.busy ||
                        attachments.length + pendingUploads.length >= 20
                      }
                    >
                      <PaperclipIcon size={21} />
                    </button>
                    {attachmentMenu && (
                      <div className="attachment-menu">
                        <span>添加到这次对话</span>
                        <button
                          type="button"
                          onClick={() => selectUpload("spectrum", "ir")}
                        >
                          <WaveformIcon size={17} />
                          IR 光谱<small>CSV / TXT</small>
                        </button>
                        <button
                          type="button"
                          onClick={() => selectUpload("spectrum", "raman")}
                        >
                          <WaveformIcon size={17} />
                          Raman 光谱<small>CSV / TXT</small>
                        </button>
                        <button
                          type="button"
                          onClick={() => selectUpload("molecule")}
                        >
                          <CubeIcon size={17} />
                          分子结构文件<small>XYZ</small>
                        </button>
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    className="draw-molecule-button"
                    onClick={() => openEditor()}
                    disabled={
                      chat.busy ||
                      chat.loading ||
                      uploading ||
                      attachments.length >= 20
                    }
                  >
                    <AtomIcon size={18} />
                    <span>画分子</span>
                  </button>
                </div>
                <div className="composer-right">
                  {chat.busy ? (
                    <button
                      type="button"
                      className="send-button stop-button"
                      aria-label="停止对话分析"
                      title="停止对话分析，已开始的科学计算会继续"
                      disabled={!chat.state.runId || chat.cancelling}
                      onClick={() => void chat.cancelRun()}
                    >
                      {chat.cancelling ? (
                        <SpinnerGapIcon size={18} className="spin" />
                      ) : (
                        <StopIcon size={17} weight="fill" />
                      )}
                    </button>
                  ) : (
                    <button
                      type="submit"
                      className="send-button"
                      aria-label={userId ? "发送消息" : "登录后发送消息"}
                      title={userId ? "发送消息" : "登录后发送消息"}
                      disabled={!canSend}
                    >
                      <ArrowUpIcon size={21} />
                    </button>
                  )}
                </div>
              </div>
            </form>
            <input
              ref={fileInput}
              type="file"
              hidden
              accept={
                uploadKind === "molecule" ? ".xyz" : ".csv,.txt,.tsv,.dat"
              }
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  if (uploadKind === "spectrum") setSpectrumFile(file);
                  else void upload(file);
                }
                event.target.value = "";
              }}
            />
            <div className="composer-presets" aria-label="常用提问">
              {promptPresets.map((preset) => (
                <button
                  type="button"
                  key={preset.label}
                  onClick={() => {
                    setDraft(appendPromptPreset(draft, preset.text));
                    requestAnimationFrame(() => textarea.current?.focus());
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <p className="composer-note">
              {chat.connection === "reconnecting" ? (
                <>
                  <SpinnerGapIcon size={12} className="spin" />
                  正在恢复连接，分析会继续进行
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="readiness-button"
                    onClick={() => setStatusOpen(true)}
                  >
                    {agentReadiness(status?.agent)} · 查看计算能力
                  </button>
                  {account && !userId && (
                    <button
                      type="button"
                      className="readiness-button"
                      onClick={() => openPanel("login")}
                    >
                      登录后使用云端聊天和计算
                    </button>
                  )}
                  <span className="keyboard-hint">
                    Enter 发送 · Shift + Enter 换行
                  </span>
                </>
              )}
            </p>
          </div>
        </div>
        <footer className="canvas-footer">
          <span>molspec</span>
          <span className="footer-dot">·</span>保持好奇，认真求证
        </footer>
      </main>
      {statusOpen && (
        <StatusDialog
          status={status}
          error={statusError}
          onClose={() => setStatusOpen(false)}
          onRefresh={() => void refreshStatus()}
        />
      )}
      {spectrumFile && (
        <SpectrumUpload
          file={spectrumFile}
          onClose={() => setSpectrumFile(null)}
          onSubmit={(metadata) => {
            setSpectrumFile(null);
            void upload(spectrumFile, metadata);
          }}
        />
      )}
      {spectrumPreview && (
        <Dialog
          title={spectrumPreview.name}
          subtitle="已保存的光谱"
          onClose={() => setSpectrumPreview(null)}
          wide
        >
          <div className="attachment-preview-body">
            <SpectrumChart
              key={spectrumPreview.id}
              spectrum={spectrumPreview}
            />
          </div>
        </Dialog>
      )}
      {editor && (
        <MoleculeComposer
          initialSmiles={editor.smiles}
          onInsert={addSmiles}
          onAttach={addAttachment}
          signedIn={!!userId}
          onClose={() => setEditor(null)}
        />
      )}
      {preview && (
        <AttachmentPreview
          key={preview.id}
          attachment={preview}
          onClose={() => setPreview(null)}
          onEdit={openEditor}
        />
      )}
      {resultIds && (
        <CalculationResults
          ids={resultIds}
          onClose={() => setResultIds(null)}
          onMolecule={openEditor}
          onUseSpectrum={useSpectrum}
        />
      )}
    </div>
  );
}

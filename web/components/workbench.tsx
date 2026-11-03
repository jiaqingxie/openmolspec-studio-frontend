"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import {
  AtomIcon,
  ArrowClockwiseIcon,
  ArrowRightIcon,
  CheckCircleIcon,
  CubeIcon,
  FileArrowUpIcon,
  FlaskIcon,
  ListBulletsIcon,
  PencilLineIcon,
  PlusIcon,
  SpinnerGapIcon,
  TrashIcon,
  WaveformIcon,
  XIcon,
} from "@phosphor-icons/react";
import { api, errorMessage } from "@/lib/api";
import {
  selectWorkbenchContext,
  validateMoleculeDraft,
  type SelectedContext,
} from "@/lib/context";
import {
  buildJobInputs,
  jobStatusLabels,
  operationLabels,
} from "@/lib/science";
import type {
  Job,
  Modality,
  Molecule,
  Operation,
  ServiceStatus,
  Spectrum,
  SpectrumMetadata,
} from "@/lib/types";
import { Dialog } from "./dialog";
import { JobResult } from "./job-result";
import { SpectrumUpload } from "./spectrum-upload";
import { SpectrumChart } from "./spectrum-chart";
const KetcherEditor = dynamic(() => import("./ketcher-editor"), {
  ssr: false,
  loading: () => (
    <div className="loading-overlay">
      <SpinnerGapIcon size={24} className="spin" />
      加载结构编辑器…
    </div>
  ),
});
const MoleculeViewer = dynamic(
  () => import("./molecule-viewer").then((module) => module.MoleculeViewer),
  {
    ssr: false,
    loading: () => (
      <div className="preview-empty">
        <CubeIcon size={30} />
        <span>加载三维视图…</span>
      </div>
    ),
  },
);

export function Workbench({
  open,
  initialOperation,
  initialTab,
  status,
  molecule,
  setMolecule,
  spectra,
  setSpectra,
  onClose,
  onContext,
  onStatus,
}: {
  open: boolean;
  initialOperation: Operation;
  initialTab: "inputs" | "jobs";
  status: ServiceStatus | null;
  molecule: Molecule | null;
  setMolecule: (molecule: Molecule) => void;
  spectra: Partial<Record<Modality, Spectrum>>;
  setSpectra: (modality: Modality, spectrum: Spectrum | undefined) => void;
  onClose: () => void;
  onContext: (context: SelectedContext) => void;
  onStatus: () => void;
}) {
  const [operation, setOperation] = useState<Operation>(initialOperation);
  const [tab, setTab] = useState(initialTab);
  const [smiles, setSmiles] = useState("");
  const [view, setView] = useState<"2d" | "3d">("2d");
  const [drawing, setDrawing] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [nmrH, setNmrH] = useState("");
  const [nmrC, setNmrC] = useState("");
  const [limit, setLimit] = useState(5);
  const [spectrumFile, setSpectrumFile] = useState<File | null>(null);
  const [spectrumModality, setSpectrumModality] = useState<Modality>("ir");
  const input = useRef<HTMLInputElement>(null);
  const xyzInput = useRef<HTMLInputElement>(null);
  const activeJob = jobs.find((job) => job.id === selectedId);
  const available = status?.chemistry?.capabilities[operation];
  const hasContextInput =
    !!molecule ||
    !!spectra.ir ||
    !!spectra.raman ||
    !!nmrH.trim() ||
    !!nmrC.trim();

  useEffect(() => {
    if (open) {
      setOperation(initialOperation);
      setTab(initialTab);
      setError(null);
    }
  }, [open, initialOperation, initialTab]);
  useEffect(() => {
    if (molecule) setSmiles(molecule.smiles);
  }, [molecule]);
  useEffect(() => {
    if (!open) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const fresh = await api.jobs();
        if (disposed) return;
        setJobs(fresh);
        setJobsError(null);
      } catch (problem) {
        if (!disposed) setJobsError(errorMessage(problem));
      }
      if (!disposed) timer = setTimeout(() => void poll(), 2500);
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [open]);

  async function resolve(value = smiles) {
    if (!value.trim()) throw new Error("请输入 SMILES 或绘制分子");
    const resolved = await api.resolveMolecule({ smiles: value.trim() });
    setMolecule(resolved);
    setSmiles(resolved.smiles);
  }
  async function run(action: string, work: () => Promise<void>) {
    setWorking(action);
    setError(null);
    try {
      await work();
    } catch (problem) {
      setError(errorMessage(problem));
    } finally {
      setWorking(null);
    }
  }
  async function importSpectrum(
    file: File,
    modality: Modality,
    metadata: SpectrumMetadata,
  ) {
    const attachment = await api.upload(file, modality, metadata);
    if (!attachment.spectrum_id) throw new Error("文件未解析为光谱");
    setSpectra(modality, await api.spectrum(attachment.spectrum_id));
    setSpectrumModality(modality);
  }
  async function submit() {
    const inputs = buildJobInputs(operation, {
      moleculeId: molecule?.id,
      irId: spectra.ir?.id,
      ramanId: spectra.raman?.id,
      nmrH,
      nmrC,
      limit,
    });
    if (operation === "predict_spectra")
      validateMoleculeDraft(molecule, smiles);
    const job = await api.submitJob(operation, inputs);
    setJobs((previous) => [
      job,
      ...previous.filter((item) => item.id !== job.id),
    ]);
    setSelectedId(job.id);
    setTab("jobs");
  }
  if (!open) return null;
  return (
    <>
      <Dialog
        title="分子与光谱工作台"
        subtitle="分子结构、理论光谱与可追溯的科学计算"
        onClose={onClose}
        wide
      >
        <div className="workbench-topline">
          <div className="segmented">
            <button
              className={tab === "inputs" ? "selected" : ""}
              onClick={() => setTab("inputs")}
            >
              <AtomIcon size={17} />
              科学计算
            </button>
            <button
              className={tab === "jobs" ? "selected" : ""}
              onClick={() => setTab("jobs")}
            >
              <ListBulletsIcon size={17} />
              计算任务
              {jobs.length ? (
                <span className="count">{jobs.length}</span>
              ) : null}
            </button>
          </div>
          <button className="text-button" onClick={onStatus}>
            资源状态
            <ArrowRightIcon size={15} />
          </button>
        </div>
        {error && (
          <div className="error-notice workbench-error" role="alert">
            {error}
            <button
              className="icon-button"
              onClick={() => setError(null)}
              aria-label="关闭错误提示"
            >
              <XIcon size={16} />
            </button>
          </div>
        )}
        {tab === "inputs" ? (
          <>
            <div
              className="operation-tabs"
              role="tablist"
              aria-label="计算类型"
            >
              {(Object.keys(operationLabels) as Operation[]).map((item) => (
                <button
                  role="tab"
                  aria-selected={operation === item}
                  key={item}
                  className={operation === item ? "selected" : ""}
                  onClick={() => setOperation(item)}
                >
                  {operationLabels[item]}
                </button>
              ))}
            </div>
            <div className="workbench-grid">
              <section className="input-pane">
                {operation === "predict_spectra" ? (
                  <>
                    <div className="section-title">
                      <h3>分子结构</h3>
                      <span>SMILES / XYZ</span>
                    </div>
                    <label className="field-label" htmlFor="smiles">
                      SMILES
                    </label>
                    <textarea
                      id="smiles"
                      className="code-input"
                      placeholder="输入 SMILES，例如 CCO"
                      value={smiles}
                      onChange={(event) => setSmiles(event.target.value)}
                      rows={3}
                      spellCheck={false}
                    />
                    <div className="input-actions">
                      <button
                        className="button button-primary"
                        disabled={
                          !!working || !smiles.trim() || !status?.chemistry
                        }
                        onClick={() => void run("resolve", () => resolve())}
                      >
                        {working === "resolve" ? (
                          <SpinnerGapIcon className="spin" size={16} />
                        ) : (
                          <AtomIcon size={16} />
                        )}
                        解析分子
                      </button>
                      <button
                        className="button"
                        onClick={() => setDrawing(true)}
                      >
                        <PencilLineIcon size={16} />
                        绘制结构
                      </button>
                      <button
                        className="icon-button"
                        title="导入 XYZ 文件"
                        aria-label="导入 XYZ 文件"
                        onClick={() => xyzInput.current?.click()}
                        disabled={!!working}
                      >
                        <FileArrowUpIcon size={19} />
                      </button>
                    </div>
                    <input
                      ref={xyzInput}
                      type="file"
                      accept=".xyz"
                      hidden
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file)
                          void run("xyz", async () => {
                            if (file.size > 10 * 1024 * 1024)
                              throw new Error("文件超过 10 MiB 上限");
                            setMolecule(
                              await api.resolveMolecule({
                                xyz: await file.text(),
                              }),
                            );
                          });
                        event.target.value = "";
                      }}
                    />
                    {molecule && (
                      <div className="molecule-properties">
                        <div>
                          <span>分子式</span>
                          <strong>{molecule.formula}</strong>
                        </div>
                        <div>
                          <span>分子量</span>
                          <strong>
                            {molecule.molecular_weight.toFixed(3)}{" "}
                            <small>g/mol</small>
                          </strong>
                        </div>
                        <div>
                          <span>原子数</span>
                          <strong>{molecule.atom_count}</strong>
                        </div>
                        <p title={molecule.inchi_key}>{molecule.inchi_key}</p>
                      </div>
                    )}
                    <p className="field-hint">
                      解析并保存结构后，计算绑定当前分子的不可变快照。
                    </p>
                  </>
                ) : (
                  <>
                    <div className="section-title">
                      <h3>输入光谱</h3>
                      <span>理论光谱域</span>
                    </div>
                    <p className="input-description">
                      导入 IR 或 Raman 数据，按需补充 NMR 化学位移。
                    </p>
                    <div className="spectrum-imports">
                      {(["ir", "raman"] as const).map((modality) => (
                        <div
                          className={`spectrum-import ${spectra[modality] ? "has-spectrum" : ""}`}
                          key={modality}
                        >
                          <WaveformIcon size={23} />
                          <div>
                            <strong>
                              {modality === "ir" ? "红外 IR" : "拉曼 Raman"}
                            </strong>
                            <span>
                              {spectra[modality]?.name ??
                                "CSV / TXT / TSV / DAT"}
                            </span>
                          </div>
                          {spectra[modality] ? (
                            <>
                              <button
                                className="icon-button"
                                aria-label={`查看 ${modality} 光谱`}
                                onClick={() => setSpectrumModality(modality)}
                              >
                                <CheckCircleIcon size={18} />
                              </button>
                              <button
                                className="icon-button"
                                aria-label={`移除 ${modality} 光谱`}
                                onClick={() => setSpectra(modality, undefined)}
                              >
                                <XIcon size={17} />
                              </button>
                            </>
                          ) : (
                            <button
                              className="icon-button"
                              aria-label={`导入 ${modality === "ir" ? "IR" : "Raman"} 光谱`}
                              disabled={!!working || !status?.chemistry}
                              onClick={() => {
                                setSpectrumModality(modality);
                                input.current?.click();
                              }}
                            >
                              <PlusIcon size={19} />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                    <input
                      ref={input}
                      type="file"
                      accept=".csv,.txt,.tsv,.dat"
                      hidden
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) setSpectrumFile(file);
                        event.target.value = "";
                      }}
                    />
                    <p className="field-hint">
                      支持两列横轴与强度，或已对齐模型网格的单列强度。文件上限
                      10 MiB。
                    </p>
                    <label className="field-label" htmlFor="nmr-h">
                      ¹H NMR <span>ppm · 选填</span>
                    </label>
                    <input
                      id="nmr-h"
                      className="text-input"
                      placeholder="以逗号或空格分隔"
                      value={nmrH}
                      onChange={(event) => setNmrH(event.target.value)}
                    />
                    <label className="field-label" htmlFor="nmr-c">
                      ¹³C NMR <span>ppm · 选填</span>
                    </label>
                    <input
                      id="nmr-c"
                      className="text-input"
                      placeholder="以逗号或空格分隔"
                      value={nmrC}
                      onChange={(event) => setNmrC(event.target.value)}
                    />
                    {operation !== "predict_gap" && (
                      <label
                        className="field-label limit-field"
                        htmlFor="candidate-limit"
                      >
                        候选数量
                        <input
                          id="candidate-limit"
                          className="text-input"
                          type="number"
                          min={1}
                          max={20}
                          value={limit}
                          onChange={(event) =>
                            setLimit(Number(event.target.value))
                          }
                        />
                      </label>
                    )}
                  </>
                )}
              </section>
              <section className="preview-pane">
                {operation === "predict_spectra" ? (
                  <>
                    <div className="preview-topline">
                      <h3>结构预览</h3>
                      <div className="segmented small">
                        <button
                          className={view === "2d" ? "selected" : ""}
                          onClick={() => setView("2d")}
                        >
                          2D
                        </button>
                        <button
                          className={view === "3d" ? "selected" : ""}
                          onClick={() => setView("3d")}
                        >
                          3D
                        </button>
                      </div>
                    </div>
                    {molecule ? (
                      view === "3d" ? (
                        <MoleculeViewer molecule={molecule} />
                      ) : (
                        <div className="molecule-2d">
                          <img
                            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(molecule.svg)}`}
                            alt={`${molecule.formula} 的二维分子结构`}
                          />
                        </div>
                      )
                    ) : (
                      <div className="preview-empty">
                        <AtomIcon size={46} weight="light" />
                        <p>从一个分子开始</p>
                        <span>输入 SMILES、导入 XYZ，或绘制结构</span>
                      </div>
                    )}
                    {molecule && (
                      <div className="canonical-smiles">
                        <span>Canonical SMILES</span>
                        <code>{molecule.smiles}</code>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="preview-topline">
                      <h3>光谱预览</h3>
                      <div className="segmented small">
                        {(["ir", "raman"] as const).map((modality) => (
                          <button
                            key={modality}
                            className={
                              spectrumModality === modality ? "selected" : ""
                            }
                            onClick={() => setSpectrumModality(modality)}
                          >
                            {modality === "ir" ? "IR" : "Raman"}
                          </button>
                        ))}
                      </div>
                    </div>
                    {spectra[spectrumModality] ? (
                      <SpectrumChart spectrum={spectra[spectrumModality]!} />
                    ) : (
                      <div className="preview-empty">
                        <WaveformIcon size={46} weight="light" />
                        <p>等待光谱数据</p>
                        <span>导入后可查看数据与缩放范围</span>
                      </div>
                    )}
                  </>
                )}
              </section>
            </div>
            <footer className="workbench-footer">
              <div
                className={`capability-note ${available?.available ? "available" : ""}`}
              >
                <span
                  className={`status-dot ${available?.available ? "online" : ""}`}
                />
                <div>
                  <strong>
                    {available?.available
                      ? "计算资源可用"
                      : status?.chemistry
                        ? "此计算缺少模型或数据资源"
                        : "科学计算服务未连接"}
                  </strong>
                  <p>{available?.detail ?? "请检查服务状态后重试"}</p>
                </div>
              </div>
              <div className="workbench-footer-actions">
                <button
                  className="button"
                  disabled={!!working || !hasContextInput}
                  onClick={() =>
                    void run("context", async () => {
                      onContext(
                        selectWorkbenchContext({
                          molecule,
                          draftSmiles: smiles,
                          spectra,
                          nmrH,
                          nmrC,
                        }),
                      );
                      onClose();
                    })
                  }
                >
                  用于对话
                </button>
                <button
                  className="button button-primary"
                  disabled={!!working || !available?.available}
                  onClick={() => void run("submit", submit)}
                >
                  {working === "submit" ? (
                    <SpinnerGapIcon size={17} className="spin" />
                  ) : (
                    <FlaskIcon size={17} />
                  )}
                  开始计算
                </button>
              </div>
            </footer>
          </>
        ) : (
          <div className="jobs-layout">
            <aside className="jobs-list">
              <div className="section-title">
                <h3>全部任务</h3>
                <button
                  className="icon-button"
                  aria-label="刷新计算任务"
                  onClick={() =>
                    void run("jobs", async () => {
                      setJobs(await api.jobs());
                      setJobsError(null);
                    })
                  }
                >
                  <ArrowClockwiseIcon size={17} />
                </button>
              </div>
              {jobsError && <p className="error-text">{jobsError}</p>}
              {!jobs.length && (
                <div className="empty-state">
                  <FlaskIcon size={30} />
                  <p>还没有计算任务</p>
                  <button
                    className="text-button"
                    onClick={() => setTab("inputs")}
                  >
                    创建第一个任务
                    <ArrowRightIcon size={14} />
                  </button>
                </div>
              )}
              {jobs.map((job) => (
                <button
                  key={job.id}
                  className={`job-row ${selectedId === job.id ? "selected" : ""}`}
                  onClick={() => setSelectedId(job.id)}
                >
                  <span>{operationLabels[job.operation]}</span>
                  <span className={`job-state state-${job.status}`}>
                    {jobStatusLabels[job.status]}
                  </span>
                  <small>
                    {new Date(job.created_at).toLocaleString("zh-CN", {
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </small>
                </button>
              ))}
            </aside>
            <div className="job-detail">
              {activeJob ? (
                <>
                  <JobResult
                    job={activeJob}
                    onMolecule={(value) =>
                      void run("resolve", async () => {
                        await resolve(value);
                        setOperation("predict_spectra");
                        setTab("inputs");
                      })
                    }
                  />
                  {activeJob.status === "queued" && (
                    <button
                      className="text-button danger"
                      disabled={!!working}
                      onClick={() =>
                        void run("cancel", async () => {
                          const cancelled = await api.cancelJob(activeJob.id);
                          setJobs((previous) =>
                            previous.map((item) =>
                              item.id === cancelled.id ? cancelled : item,
                            ),
                          );
                        })
                      }
                    >
                      <TrashIcon size={15} />
                      取消排队计算
                    </button>
                  )}
                </>
              ) : (
                <div className="preview-empty">
                  <ListBulletsIcon size={38} weight="light" />
                  <p>选择任务查看结果</p>
                  <span>输入、状态与计算来源会持续保存</span>
                </div>
              )}
            </div>
          </div>
        )}
      </Dialog>
      {spectrumFile && (
        <SpectrumUpload
          file={spectrumFile}
          onClose={() => setSpectrumFile(null)}
          onSubmit={(metadata) => {
            setSpectrumFile(null);
            void run("upload", () =>
              importSpectrum(spectrumFile, spectrumModality, metadata),
            );
          }}
        />
      )}
      {drawing && (
        <KetcherEditor
          smiles={smiles}
          onApply={resolve}
          onClose={() => setDrawing(false)}
        />
      )}
    </>
  );
}

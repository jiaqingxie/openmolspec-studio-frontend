"use client";
import {
  DownloadSimpleIcon,
  FlaskIcon,
  ArrowUpRightIcon,
} from "@phosphor-icons/react";
import type { SpectrumReference } from "@/lib/composer";
import type { Job } from "@/lib/types";
import {
  downloadJson,
  jobStatusLabels,
  operationLabels,
  resultSpectra,
} from "@/lib/science";
import { SpectrumChart } from "./spectrum-chart";

function Metadata({ value }: { value: unknown }) {
  if (!value || typeof value !== "object")
    return <span>{String(value ?? "—")}</span>;
  return (
    <dl className="metadata-list">
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>
            {typeof item === "object" ? JSON.stringify(item) : String(item)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function JobResult({
  job,
  onMolecule,
  onUseSpectrum,
}: {
  job: Job;
  onMolecule: (smiles: string) => void;
  onUseSpectrum?: (reference: SpectrumReference) => void;
}) {
  const result = job.result;
  const spectra = result ? resultSpectra(result) : [];
  const candidates =
    result && Array.isArray(result.candidates)
      ? result.candidates.filter(
          (item): item is Record<string, unknown> =>
            !!item && typeof item === "object",
        )
      : [];
  const gap = typeof result?.gap_ev === "number" ? result.gap_ev : null;
  return (
    <section className="job-result">
      <div className="result-heading">
        <div>
          <span className="eyebrow">CALCULATION</span>
          <h3>{operationLabels[job.operation]}</h3>
        </div>
        <span className={`job-state state-${job.status}`}>
          {jobStatusLabels[job.status]}
        </span>
      </div>
      <p className="job-id">{job.id}</p>
      {(job.status === "queued" || job.status === "running") && (
        <div className="calculation-wait">
          <FlaskIcon size={32} className="pulse" />
          <p>
            {job.status === "queued"
              ? "任务已保存，等待计算资源"
              : "科学计算正在进行"}
          </p>
          <span>可关闭面板，稍后从这条回答继续查看结果。</span>
        </div>
      )}
      {job.error && (
        <div className="error-notice" role="alert">
          <strong>{job.error.code}</strong>
          <p>{job.error.message}</p>
        </div>
      )}
      {job.status === "cancelled" && (
        <div className="empty-state">
          <p>此任务已取消</p>
        </div>
      )}
      {result && (
        <>
          <div className="domain-note">
            <FlaskIcon size={15} />
            理论光谱域 · 请结合计算方式与来源解读结果
          </div>
          {gap !== null && (
            <div className="gap-result">
              <span>HOMO–LUMO gap</span>
              <p>
                {gap.toFixed(4)} <small>eV</small>
              </p>
              {typeof result.benchmark_mae_ev === "number" && (
                <span>
                  模型基准 MAE {result.benchmark_mae_ev} eV（非本次预测误差）
                </span>
              )}
            </div>
          )}
          {spectra.map((spectrum) => (
            <div key={spectrum.id}>
              <SpectrumChart spectrum={spectrum} />
              {onUseSpectrum &&
                job.status === "succeeded" &&
                typeof result[`${spectrum.modality}_id`] === "string" && (
                  <button
                    className="button"
                    onClick={() =>
                      onUseSpectrum({
                        id: result[`${spectrum.modality}_id`] as string,
                        name: spectrum.name,
                        modality: spectrum.modality,
                      })
                    }
                  >
                    将{spectrum.modality === "ir" ? " IR " : " Raman "}
                    光谱用于对话
                  </button>
                )}
            </div>
          ))}
          {candidates.length > 0 && (
            <div className="candidate-list">
              <h4>
                候选分子 <span>{candidates.length}</span>
              </h4>
              {candidates.map((item, i) => (
                <div className="candidate" key={i}>
                  <span className="candidate-rank">
                    {String(item.rank ?? i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <code>
                      {String(
                        item.smiles ?? item.canonical_smiles ?? "未提供结构",
                      )}
                    </code>
                    <span>
                      {typeof item.similarity === "number"
                        ? `相似度 ${item.similarity.toFixed(4)}`
                        : typeof item.score === "number"
                          ? `评分 ${item.score.toFixed(4)}`
                          : "未提供评分"}
                      {typeof item.backend === "string"
                        ? ` · ${item.backend}`
                        : ""}
                    </span>
                  </div>
                  {typeof item.smiles === "string" && (
                    <button
                      className="icon-button"
                      aria-label={`查看候选分子 ${i + 1}`}
                      onClick={() => onMolecule(item.smiles as string)}
                    >
                      <ArrowUpRightIcon size={18} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {(["nmr_h", "nmr_c"] as const).map(
            (key) =>
              Array.isArray(result[key]) && (
                <div className="nmr-result" key={key}>
                  <h4>
                    {key === "nmr_h" ? "¹H" : "¹³C"} NMR <span>ppm</span>
                  </h4>
                  <p>
                    {(result[key] as unknown[])
                      .map((value) =>
                        typeof value === "number"
                          ? value.toFixed(3)
                          : String(value),
                      )
                      .join(" · ")}
                  </p>
                </div>
              ),
          )}
          {result.mode != null && (
            <div className="result-method">
              <h4>计算方式</h4>
              <p>{String(result.mode)}</p>
            </div>
          )}
          <details className="result-details" open>
            <summary>来源与单位</summary>
            <Metadata value={result.provenance} />
            <Metadata value={result.units} />
          </details>
        </>
      )}
      <details className="result-details">
        <summary>提交时的输入快照</summary>
        <pre>{JSON.stringify(job.inputs, null, 2)}</pre>
      </details>
      {result && (
        <div className="result-download">
          <button
            className="text-button"
            onClick={() => downloadJson(job, `openmolspec-${job.id}.json`)}
          >
            <DownloadSimpleIcon size={17} />
            导出完整结果
          </button>
          <details className="raw-result">
            <summary>原始数据</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </div>
      )}
    </section>
  );
}

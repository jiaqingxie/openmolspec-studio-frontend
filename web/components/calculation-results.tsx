"use client";
import { useEffect, useState } from "react";
import { SpinnerGapIcon } from "@phosphor-icons/react";
import { api, errorMessage } from "@/lib/api";
import type { SpectrumReference } from "@/lib/composer";
import type { Job } from "@/lib/types";
import { operationLabels } from "@/lib/science";
import { Dialog } from "./dialog";
import { JobResult } from "./job-result";

/** Read only: tool selection and job submission belong to the Agent. */
export function CalculationResults({
  ids,
  onClose,
  onMolecule,
  onUseSpectrum,
}: {
  ids: string[];
  onClose: () => void;
  onMolecule: (smiles: string) => void;
  onUseSpectrum: (reference: SpectrumReference) => void;
}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState(ids[0]);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const loaded = await Promise.all(ids.map((id) => api.job(id)));
        if (!active) return;
        setJobs(loaded);
        setError(null);
        if (
          loaded.some(
            (job) => job.status === "queued" || job.status === "running",
          )
        )
          timer = setTimeout(() => void refresh(), 2000);
      } catch (problem) {
        if (active) setError(errorMessage(problem));
      }
    }
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [ids, reload]);
  const job = jobs.find((item) => item.id === selected);
  return (
    <Dialog
      title="计算结果"
      subtitle="molspec 在这次分析中使用的计算与数据"
      onClose={onClose}
      wide
    >
      <div className="calculation-results-body">
        {error && (
          <div className="error-text" role="alert">
            <p>{error}</p>
            <button
              className="button"
              onClick={() => setReload((previous) => previous + 1)}
            >
              重新读取结果
            </button>
          </div>
        )}
        {!jobs.length && !error && (
          <div className="preview-loading" role="status">
            <SpinnerGapIcon size={22} className="spin" />
            正在读取结果…
          </div>
        )}
        {jobs.length > 1 && (
          <div className="calculation-result-tabs">
            {jobs.map((item) => (
              <button
                key={item.id}
                aria-pressed={selected === item.id}
                onClick={() => setSelected(item.id)}
              >
                {operationLabels[item.operation]}
              </button>
            ))}
          </div>
        )}
        {job && (
          <JobResult
            job={job}
            onMolecule={onMolecule}
            onUseSpectrum={onUseSpectrum}
          />
        )}
        {job?.status === "queued" && (
          <button
            className="button"
            onClick={async () => {
              try {
                const cancelled = await api.cancelJob(job.id);
                setJobs((current) =>
                  current.map((item) =>
                    item.id === cancelled.id ? cancelled : item,
                  ),
                );
                setReload((previous) => previous + 1);
              } catch (problem) {
                setError(errorMessage(problem));
              }
            }}
          >
            取消排队计算
          </button>
        )}
        {job?.status === "running" && (
          <p className="spectrum-quality">
            计算已开始。停止对话分析不会结束此计算。
          </p>
        )}
      </div>
    </Dialog>
  );
}

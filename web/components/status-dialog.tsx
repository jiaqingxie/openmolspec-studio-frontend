"use client";
import {
  ArrowClockwiseIcon,
  CheckCircleIcon,
  CircleIcon,
  PlugIcon,
} from "@phosphor-icons/react";
import { agentReadiness } from "@/lib/composer";
import { Dialog } from "./dialog";
import type { Operation, ServiceStatus } from "@/lib/types";
import { operationLabels } from "@/lib/science";
export function StatusDialog({
  status,
  error,
  onClose,
  onRefresh,
}: {
  status: ServiceStatus | null;
  error: string | null;
  onClose: () => void;
  onRefresh: () => void;
}) {
  return (
    <Dialog
      title="服务与模型"
      subtitle="查看当前工作区的实际可用能力"
      onClose={onClose}
    >
      <div className="status-content">
        <section className="service-section">
          <h3>
            <PlugIcon size={19} /> 对话模型
          </h3>
          <div
            className={`service-state ${status?.agent.verified ? "available" : ""}`}
          >
            {status?.agent.verified ? (
              <CheckCircleIcon size={18} />
            ) : (
              <CircleIcon size={18} />
            )}
            <strong>
              {agentReadiness(status?.agent)}
              {status?.agent.model ? ` · ${status.agent.model}` : ""}
            </strong>
          </div>
          {status?.agent.configured === false && (
            <p>
              管理员在服务端设置 <code>OPENAI_BASE_URL</code>、
              <code>OPENAI_API_KEY</code> 与 <code>OPENMOLSPEC_LLM_MODEL</code>{" "}
              后，即可尝试对话。分子编辑与附件预览仍可使用。
            </p>
          )}
        </section>
        <section className="service-section">
          <h3>
            科学计算服务{" "}
            <span className="small-label">
              {status?.chemistry ? status.chemistry.device : "未连接"}
            </span>
          </h3>
          {error && <p className="error-text">{error}</p>}
          {status?.chemistry_error && (
            <p className="error-text">
              {typeof status.chemistry_error === "string"
                ? status.chemistry_error
                : status.chemistry_error.message}
            </p>
          )}
          {status?.chemistry ? (
            <ul className="capability-list">
              {(Object.keys(operationLabels) as Operation[]).map(
                (operation) => {
                  const capability = status.chemistry!.capabilities[operation];
                  return (
                    <li key={operation}>
                      <span
                        className={capability.available ? "available" : "muted"}
                      >
                        {capability.available ? (
                          <CheckCircleIcon size={18} />
                        ) : (
                          <CircleIcon size={18} />
                        )}
                      </span>
                      <div>
                        <strong>{operationLabels[operation]}</strong>
                        <p>{capability.detail}</p>
                      </div>
                      <span className="small-label">
                        {capability.available ? "可用" : "缺少资源"}
                      </span>
                    </li>
                  );
                },
              )}
            </ul>
          ) : (
            <p>
              暂时无法连接科学计算服务。连接恢复后，可继续解析分子、导入光谱和提交计算。
            </p>
          )}
        </section>
        <div className="status-footer">
          <span>OpenMolSpec {status?.version ?? "2.0.0"} · 理论光谱域</span>
          <button className="text-button" onClick={onRefresh}>
            <ArrowClockwiseIcon size={16} />
            刷新状态
          </button>
        </div>
      </div>
    </Dialog>
  );
}

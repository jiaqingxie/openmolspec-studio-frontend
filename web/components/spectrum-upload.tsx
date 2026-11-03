"use client";
import { useState } from "react";
import type { SpectrumMetadata } from "@/lib/types";
import { Dialog } from "./dialog";

export function SpectrumUpload({
  file,
  onClose,
  onSubmit,
}: {
  file: File;
  onClose: () => void;
  onSubmit: (metadata: SpectrumMetadata) => void;
}) {
  const [axisUnit, setAxisUnit] =
    useState<SpectrumMetadata["axis_unit"]>("unknown");
  const [axisMode, setAxisMode] =
    useState<SpectrumMetadata["axis_mode"]>("explicit");
  const [domain, setDomain] = useState<SpectrumMetadata["domain"]>("unknown");
  const [intensityUnit, setIntensityUnit] = useState("");
  return (
    <Dialog title="导入光谱" subtitle={file.name} onClose={onClose}>
      <form
        className="spectrum-upload-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({
            axis_unit: axisMode === "model_grid" ? "cm^-1" : axisUnit,
            axis_mode: axisMode,
            domain,
            intensity_unit: intensityUnit.trim() || "unknown",
          });
        }}
      >
        <label>
          横轴格式
          <select
            value={axisMode}
            onChange={(event) =>
              setAxisMode(event.target.value as SpectrumMetadata["axis_mode"])
            }
          >
            <option value="explicit">两列 · 横轴与强度</option>
            <option value="model_grid">一列 · 已对齐模型网格</option>
          </select>
        </label>
        {axisMode === "model_grid" ? (
          <p>
            模型网格为 400–4000 cm⁻¹，共 1024 个点。请确认文件已使用此网格。
          </p>
        ) : (
          <label>
            横轴单位
            <select
              value={axisUnit}
              onChange={(event) =>
                setAxisUnit(event.target.value as SpectrumMetadata["axis_unit"])
              }
            >
              <option value="unknown">未知</option>
              <option value="cm^-1">cm⁻¹</option>
              <option value="nm">nm</option>
            </select>
          </label>
        )}
        <label>
          强度单位
          <input
            value={intensityUnit}
            maxLength={80}
            placeholder="例如 a.u. 或 %T，未知可留空"
            onChange={(event) => setIntensityUnit(event.target.value)}
          />
        </label>
        <label>
          数据来源
          <select
            value={domain}
            onChange={(event) =>
              setDomain(event.target.value as SpectrumMetadata["domain"])
            }
          >
            <option value="unknown">未知</option>
            <option value="theoretical">理论计算</option>
            <option value="experimental">实验测量</option>
          </select>
        </label>
        <p>
          实验和来源未知的光谱可以预览。模型分析需要满足输入要求的理论光谱。
        </p>
        <div className="input-actions">
          <button type="button" className="button" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="button button-primary">
            导入并检查
          </button>
        </div>
      </form>
    </Dialog>
  );
}

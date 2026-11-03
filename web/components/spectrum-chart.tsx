"use client";
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Brush,
} from "recharts";
import type { Spectrum } from "@/lib/types";

export function SpectrumChart({ spectrum }: { spectrum: Spectrum }) {
  const [showRaw, setShowRaw] = useState(false);
  const raw = showRaw ? spectrum.raw : undefined;
  const axisUnit = raw
    ? raw.wavenumber
      ? raw.axis_unit
      : "index"
    : spectrum.axis_unit;
  const intensityUnit = raw?.intensity_unit ?? spectrum.intensity_unit;
  const axisLabel =
    axisUnit === "cm^-1"
      ? "波数 / cm⁻¹"
      : axisUnit === "nm"
        ? "波长 / nm"
        : axisUnit === "index"
          ? "采样序号"
          : "横轴 / 单位未知";
  const intensityLabel =
    !intensityUnit || intensityUnit === "unknown"
      ? "强度 / 单位未知"
      : `强度 / ${intensityUnit}`;
  const points = useMemo(() => {
    const intensity = raw?.intensity ?? spectrum.intensity;
    const axis = raw ? raw.wavenumber : spectrum.wavenumber;
    return intensity
      .map((value, i) => ({ x: axis?.[i] ?? i + 1, intensity: value }))
      .sort((a, b) => a.x - b.x);
  }, [raw, spectrum]);
  return (
    <div className="spectrum-chart">
      <div className="chart-caption">
        <strong>{spectrum.modality === "ir" ? "红外 IR" : "拉曼 Raman"}</strong>
        <span>{points.length} 个点 · 拖动底部范围缩放</span>
        {spectrum.raw && (
          <button
            type="button"
            className="button"
            aria-pressed={showRaw}
            onClick={() => setShowRaw(!showRaw)}
          >
            {showRaw ? "查看预览" : "查看原始数据"}
          </button>
        )}
      </div>
      <div
        className="chart-plot"
        role="group"
        aria-label={`${spectrum.name}，${points.length} 个光谱数据点，${axisLabel}，${intensityLabel}`}
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart
            data={points}
            margin={{ top: 14, right: 12, bottom: 8, left: -18 }}
            accessibilityLayer
          >
            <CartesianGrid
              stroke="#eae8e1"
              strokeDasharray="3 4"
              vertical={false}
            />
            <XAxis
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              reversed={spectrum.modality === "ir" && axisUnit === "cm^-1"}
              tick={{ fontSize: 10, fill: "#858993" }}
              axisLine={false}
              tickLine={false}
              tickCount={6}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#858993" }}
              axisLine={false}
              tickLine={false}
              width={55}
              tickFormatter={(value: number) =>
                Math.abs(value) < 0.01 && value !== 0
                  ? value.toExponential(1)
                  : Number(value.toPrecision(3)).toString()
              }
            />
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                border: "1px solid #e7e5df",
                fontSize: 12,
              }}
              labelFormatter={(label) =>
                `${axisLabel} · ${Number(label).toPrecision(6)}`
              }
              formatter={(value) => [
                typeof value === "number"
                  ? value.toPrecision(5)
                  : String(value),
                intensityLabel,
              ]}
            />
            <Line
              type="linear"
              dataKey="intensity"
              stroke="#5e8865"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Brush
              dataKey="x"
              height={18}
              stroke="#c5d5b8"
              fill="#fafcf5"
              travellerWidth={6}
              tickFormatter={(value: number) => Math.round(value).toString()}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-axis">
        {axisLabel} <span>{intensityLabel}</span>
      </div>
      <div className="spectrum-quality">
        <p>
          来源：
          {spectrum.domain === "theoretical"
            ? "理论计算"
            : spectrum.domain === "experimental"
              ? "实验测量"
              : "未知"}
          {spectrum.provenance?.job_id
            ? ` · 计算任务 ${spectrum.provenance.job_id}`
            : ""}
        </p>
        {spectrum.quality && (
          <p>
            {spectrum.quality.model_eligible
              ? "满足模型光谱输入要求"
              : "仅供预览，当前光谱不满足模型输入要求"}
          </p>
        )}
        {!!spectrum.quality?.reasons.length && (
          <ul>
            {spectrum.quality.reasons.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
        )}
        {!!spectrum.processing?.steps.length && (
          <details>
            <summary>数据处理</summary>
            <ul>
              {spectrum.processing.steps.map((step, index) => (
                <li key={index}>{step}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}

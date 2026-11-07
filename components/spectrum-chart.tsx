"use client";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface Series {
  name: string;
  color: string;
  points: { x: number; y: number }[];
}

const AXIS = {
  stroke: "#1a1a1a",
  tick: { fontSize: 11, fill: "#555555", fontFamily: "var(--font-plex-mono), monospace" },
};

export function SpectrumChart({
  series,
  xLabel,
  reversed = false,
  height = 280,
}: {
  series: Series[];
  xLabel: string;
  reversed?: boolean;
  height?: number;
}) {
  const merged: Record<string, number>[] = [];
  const lengths = series.map((item) => item.points.length);
  if (!lengths.length) return null;
  for (let i = 0; i < Math.max(...lengths); i += 1) {
    const row: Record<string, number> = {};
    for (const item of series) {
      const point = item.points[i];
      if (point) {
        row.x = point.x;
        row[item.name] = point.y;
      }
    }
    merged.push(row);
  }
  return (
    <div className="figure-box" style={{ height: height + 24 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={merged} margin={{ top: 8, right: 10, bottom: 18, left: 0 }}>
          <CartesianGrid stroke="#ececea" strokeDasharray="1 0" vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            domain={["dataMin", "dataMax"]}
            reversed={reversed}
            tick={AXIS.tick}
            axisLine={{ stroke: AXIS.stroke, strokeWidth: 1 }}
            tickLine={{ stroke: AXIS.stroke }}
            tickCount={7}
            label={{
              value: xLabel,
              position: "insideBottom",
              offset: -12,
              fill: "#1a1a1a",
              fontSize: 12,
            }}
          />
          <YAxis
            tick={AXIS.tick}
            axisLine={false}
            tickLine={false}
            width={52}
            domain={[0, 1.02]}
            tickFormatter={(value: number) => Number(value.toFixed(2)).toString()}
          />
          <Tooltip
            contentStyle={{
              background: "#ffffff",
              border: "1px solid #1a1a1a",
              borderRadius: 0,
              fontSize: 12,
              fontFamily: "var(--font-plex-mono), monospace",
              color: "#1a1a1a",
            }}
            labelFormatter={(label) => `${Number(label).toPrecision(6)}`}
            cursor={{ stroke: "#1a1a1a", strokeDasharray: "3 3" }}
          />
          {series.map((item) => (
            <Line
              key={item.name}
              type="linear"
              dataKey={item.name}
              stroke={item.color}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function NmrCurve({
  peaks,
  nucleus,
  color,
}: {
  peaks: number[];
  nucleus: "H" | "C";
  color: string;
}) {
  const axis =
    nucleus === "H"
      ? Array.from({ length: 700 }, (_, i) => 14 - i * (15 / 700))
      : Array.from({ length: 700 }, (_, i) => 240 - i * (260 / 700));
  const width = nucleus === "H" ? 0.04 : 0.4;
  const points = axis.map((x) => ({
    x,
    y: peaks.reduce((sum, peak) => sum + Math.exp(-0.5 * ((x - peak) / width) ** 2), 0),
  }));
  const max = Math.max(...points.map((point) => point.y), 1e-9);
  const data = points.map((point) => ({ x: point.x, y: point.y / max }));
  return (
    <SpectrumChart
      series={[{ name: `¹${nucleus}`, color, points: data }]}
      xLabel={`chemical shift (ppm)`}
      reversed
      height={240}
    />
  );
}

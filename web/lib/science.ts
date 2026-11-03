import type { Operation, Spectrum } from "./types.ts";
export const operationLabels: Record<Operation, string> = {
  predict_spectra: "结构 → 光谱",
  retrieve: "光谱 → 分子检索",
  predict_gap: "HOMO–LUMO 能隙",
  generate: "光谱 → 分子生成",
};
export const jobStatusLabels = {
  queued: "排队中",
  running: "计算中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};
export const toolLabels: Record<string, string> = {
  get_capabilities: "检查计算能力",
  inspect_molecule: "解析分子结构",
  predict_spectra: "预测理论光谱",
  retrieve_candidates: "检索候选分子",
  predict_gap: "计算 HOMO–LUMO 能隙",
  generate_candidates: "生成候选分子",
  get_calculation: "读取计算结果",
};
export function parseShifts(text: string): number[] {
  if (!text.trim()) return [];
  const tokens = text
    .trim()
    .split(/[\s,;，；]+/)
    .filter(Boolean);
  const decimal = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;
  const shifts = tokens.map(Number);
  if (
    !tokens.every((token) => decimal.test(token)) ||
    !shifts.every(Number.isFinite)
  )
    throw new Error("NMR 位移必须为有限数值，以逗号或空格分隔");
  return shifts;
}
export function buildJobInputs(
  operation: Operation,
  input: {
    moleculeId?: string;
    irId?: string;
    ramanId?: string;
    nmrH: string;
    nmrC: string;
    limit: number;
  },
): Record<string, unknown> {
  if (operation === "predict_spectra") {
    if (!input.moleculeId) throw new Error("请先解析一个有效分子");
    return { molecule_id: input.moleculeId };
  }
  if (!input.irId && !input.ramanId)
    throw new Error("请先导入 IR 或 Raman 光谱");
  const result: Record<string, unknown> = {};
  if (input.irId) result.ir_id = input.irId;
  if (input.ramanId) result.raman_id = input.ramanId;
  const h = parseShifts(input.nmrH),
    c = parseShifts(input.nmrC);
  if (h.length) result.nmr_h = h;
  if (c.length) result.nmr_c = c;
  if (operation === "retrieve" || operation === "generate") {
    if (!Number.isInteger(input.limit) || input.limit < 1 || input.limit > 20)
      throw new Error("候选数量应为 1–20 的整数");
    result.limit = input.limit;
  }
  return result;
}
function finiteArray(value: unknown): value is number[] {
  return (
    Array.isArray(value) &&
    value.length > 1 &&
    value.every((item) => typeof item === "number" && Number.isFinite(item))
  );
}
export function resultSpectra(result: Record<string, unknown>): Spectrum[] {
  if (!finiteArray(result.wavenumber)) return [];
  const x = result.wavenumber;
  return (["ir", "raman"] as const).flatMap((modality) => {
    const values = result[modality];
    if (!finiteArray(values) || values.length !== x.length) return [];
    return [
      {
        id: `result-${modality}`,
        name: `预测 ${modality === "ir" ? "IR" : "Raman"}`,
        modality,
        axis_unit: "cm^-1" as const,
        intensity_unit: "归一化 [0,1]",
        domain: "theoretical" as const,
        wavenumber: x,
        intensity: values,
      },
    ];
  });
}
export function downloadJson(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

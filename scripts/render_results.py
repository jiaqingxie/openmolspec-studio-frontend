"""Publish a completed local evaluation as a reproducible handbook page."""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("result", type=Path)
args = parser.parse_args()
payload = json.loads(args.result.read_text())
if not payload.get("completed_at"):
    raise SystemExit("Evaluation has not completed; refusing to publish partial results")
rows = payload["results"]
counts = dict(Counter(row["status"] for row in rows))
if counts != payload["counts"]:
    raise SystemExit("Result counts do not match per-task states")
assets = ROOT / "handbook/assets"
assets.mkdir(exist_ok=True)
shutil.copyfile(args.result, assets / args.result.name)
lines = ["# 评测结果", "", f"运行完成：`{payload['completed_at']}`。用途：流程小样本验证。",
         "", f"共 {len(rows)} 个任务/数据集组合：{counts.get('passed', 0)} 通过，{counts.get('failed', 0)} 失败，{counts.get('skipped', 0)} 跳过。",
         "", f"样本上限 {payload['limit']}，设备 `{payload['device']}`，beam size 以各生成任务记录为准。权重保持已有状态，没有训练。",
         "", f"[下载完整结果 JSON](assets/{args.result.name})，包含数据/权重哈希、样本 ID、选择规则、候选池和每项运行状态。",
         "", "这些结果检验代码与资产能否配合运行。小候选池、给定分子式、跨域输入等条件必须与分数一起解读；本次未重新审核数据来源及训练集泄漏。",
         "", "## H/C 检索与生成", "", "检索 R@1 使用本次选中的候选池，生成 exact 为给定分子式并重排后的 top-1。",
         "", "| 数据集 | H+C 谱→结构 R@1 | H+C 结构→谱 R@1 | H+C 生成 exact | 生成有效率 |", "| --- | --- | --- | --- | --- |"]
datasets = list(dict.fromkeys(row.get("dataset_name") for row in rows if row["task"] == "nmr.retrieval.hc.s2m"))
lookup = {(row["task"], row.get("dataset_name")): row for row in rows}


def metric(task, dataset, name):
    value = lookup[(task, dataset)].get("metrics", {}).get(name)
    return f"{value:.4f}" if value is not None else "未评分"


for dataset in datasets:
    values = [metric("nmr.retrieval.hc.s2m", dataset, "recall_at_1"),
              metric("nmr.retrieval.hc.m2s", dataset, "recall_at_1"),
              metric("nmr.generation.hc", dataset, "exact_rate"),
              metric("nmr.generation.hc", dataset, "valid_rate")]
    lines.append(f"| {dataset} | " + " | ".join(values) + " |")
lines.extend(["", "## 已有正向预测评分", "", "| 任务 | 数据集 | 模型 | MAE (ppm) | 评分分子数 | 匹配覆盖率 |",
              "| --- | --- | --- | --- | --- | --- |"])
for row in rows:
    for model in row.get("models", []):
        m = model["metrics"]
        lines.append(f"| {row['task']} | {row.get('dataset_name')} | {model['model']} | {m['matched_peak_mae_ppm']:.4f} | {m['scored_examples']} | {m['matched_fraction']:.4f} |")
lines.extend(["", "H/C 使用未指认峰的最小误差匹配，同时记录峰数误差和覆盖率，不作为逐原子指认精度。",
              "", "## 其他已运行任务", "", "| 任务 | 条件 | 指标 |", "| --- | --- | --- |"])
for row in rows:
    if row["status"] != "passed" or row["backend"] in ("spec2struct_alignment", "spec2struct_generation", "nmrnet_predictions"):
        continue
    m = row.get("metrics", {})
    metrics = "; ".join(f"{name}={value:.4f}" for name, value in m.items()
                        if isinstance(value, float) and name not in ("recall_at_5", "recall_at_10"))
    condition = "固相→溶液域诊断" if row.get("model_domain") == "solid_state" else "计算 IR/Raman，未提供 H/C"
    lines.append(f"| {row['task']} | {condition} | {metrics} |")
lines.extend(["", "F/P 的固相到实验溶液域误差很大，仅证明已有预测评分路径可运行。Vib2Mol 生成使用原始 beam top-1，不使用测试集缓存。Gap 参考值先按元数据转换成 eV。",
              "", "## 跳过项", "", "以下条目没有生成占位分数：", ""])
for row in rows:
    if row["status"] != "passed":
        lines.append(f"- `{row['task']}`（{row['status']}）：{row.get('reason', '')}")
lines.extend(["", "## 本地验证与发布状态", "",
              "指标、输入规范化和预测解包的 12 项检查通过。Streamlit AppTest 验证了无模型资产时的默认页和 NMR 页面，H/C 交互检索与生成服务也实际运行通过。",
              "", "手册采用 MkDocs Material，已配置 GitHub Actions 构建和 Pages 发布。当前环境无法解析网络代理域名，因此严格 MkDocs 依赖安装、GitHub 推送和远端 Pages 部署尚未验证；本页不代表站点已上线。", ""])
(ROOT / "handbook/results.md").write_text("\n".join(lines))
print(f"Rendered {len(rows)} task results: {counts}")

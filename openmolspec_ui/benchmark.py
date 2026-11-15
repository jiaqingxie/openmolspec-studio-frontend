"""Studio pages for the unified task catalog, results, and H/C NMR."""

import json
from pathlib import Path


def benchmark_page(st):
    from openmolspec_bench.catalog import records

    st.title("OpenMolSpec v1.0 · 谱学任务与评测")
    st.write("查看任务覆盖、现有模型适配状态和可复现的小样本结果。")
    tasks = records()
    families = sorted({task["family"] for task in tasks})
    family = st.selectbox("任务类型", ["全部", *families])
    rows = []
    for task in tasks:
        if family != "全部" and task["family"] != family:
            continue
        rows.append({"任务": task["title"], "ID": task["id"], "谱型": ", ".join(task["modalities"]),
                     "数据域": task["domain"], "评测适配器": "待接入" if task["backend"] == "unavailable" else task["backend"],
                     "指标": ", ".join(task["metrics"]), "说明": task["note"]})
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("适配器已接入表示有运行入口；通过状态以实际结果为准。NMR 实验域与计算 IR/Raman 分开报告。")
    result_files = []
    for path in (Path(__file__).resolve().parents[1] / "results").glob("*.json"):
        try:
            payload = json.loads(path.read_text())
            rows = payload.get("results", [payload] if payload.get("task") else [])
            if rows and all(isinstance(row, dict) and row.get("task") for row in rows):
                result_files.append(path)
        except (ValueError, OSError):
            continue
    result_files.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if result_files:
        selected = st.selectbox("评测记录", result_files, format_func=lambda path: path.name)
        payload = json.loads(selected.read_text())
        if selected.name in ("smoke_hetero_20261115.json", "v1_pipeline_20261115.json"):
            st.warning("该历史记录中的 F/P 分数已因输入与预测错配撤回。请查看后续 alignment/protocol audit；其他任务保留其原始运行条件。")
        st.write({"用途": payload.get("purpose"), "样本上限": payload.get("limit"),
                  "设备": payload.get("device"), "状态统计": payload.get("counts")})
        summaries = []
        for result in payload.get("results", [payload] if payload.get("task") else []):
            entries = result.get("models") or [{"model": result.get("backend", result.get("model", result["task"])), "metrics": result.get("metrics", {})}]
            for entry in entries:
                summaries.append({"任务": result["task"], "数据集": result.get("dataset_name"),
                                  "模型": entry["model"], "状态": result.get("status", str(result.get("counts", {}))),
                                  "指标": json.dumps(entry["metrics"], ensure_ascii=False),
                                  "说明": result.get("reason", "")})
        st.dataframe(summaries, hide_index=True, width="stretch")
        st.download_button("下载完整评测 JSON", selected.read_bytes(), selected.name, "application/json")
    else:
        st.info("尚无评测结果。请按使用手册运行 python -m openmolspec_bench run。")
    import os
    if os.environ.get("OPENMOLSPEC_DOCS_URL"):
        st.link_button("Full documentation · Read the Docs", os.environ["OPENMOLSPEC_DOCS_URL"])
    else:
        st.caption("Full documentation 栏目提供中英文任务说明与 notebook；Read the Docs 托管地址待确认。")


def nmr_page(st, device):
    from .nmr import NMRService

    st.title("实验 H/C NMR → 结构")
    st.write("输入 ¹H、¹³C 或两者组合的峰列表，使用现有对齐和生成模型。")

    @st.cache_resource(show_spinner=False)
    def service(selected_device):
        return NMRService(selected_device)

    h = st.text_area("¹H NMR（ppm，可含多重性、J、积分）", "1.20 (t, J=7.0 Hz, 3H), 3.65 (q, J=7.0 Hz, 2H)")
    c = st.text_area("¹³C NMR（ppm）", "18.2, 58.3")
    mode = st.radio("任务", ["候选结构检索", "SMILES 生成"], horizontal=True)
    if mode == "候选结构检索":
        candidates = st.text_area("候选 SMILES（每行一个）", "CCO\nCOC\nCC=O")
        st.caption("分数是谱图与候选的余弦相似度；结果受候选集合影响。")
        if st.button("检索候选", type="primary"):
            try:
                with st.spinner("正在编码谱图与候选结构"):
                    result = service(device).retrieve(h, c, [line for line in candidates.splitlines() if line.strip()])
                st.dataframe(result, hide_index=True, width="stretch")
                st.download_button("下载检索结果", json.dumps(result, ensure_ascii=False, indent=2), "nmr_retrieval.json", "application/json")
            except Exception as error:
                st.error(str(error))
    else:
        formula = st.text_input("已知分子式", "C2H6O")
        beam = st.slider("Beam size", 1, 10, 5)
        st.caption("分子式是给定输入；生成候选会按有效性、分子式一致性和模型分数排序。")
        if st.button("生成结构", type="primary"):
            try:
                with st.spinner("正在运行已有生成模型"):
                    result = service(device).generate(h, c, formula, beam)
                st.dataframe(result, hide_index=True, width="stretch")
                st.download_button("下载生成结果", json.dumps(result, ensure_ascii=False, indent=2), "nmr_generation.json", "application/json")
            except Exception as error:
                st.error(str(error))

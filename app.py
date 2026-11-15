from __future__ import annotations

import html
import json
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from streamlit_ketcher import st_ketcher

from openmolspec_ui.chemistry import (
    molecule_3d_html,
    molecule_from_smiles,
    molecule_from_xyz,
    smiles_png,
)
from openmolspec_ui.config import discover_assets
from openmolspec_ui.inference import OpenMolSpecService, resolve_device
from openmolspec_ui.spectra import (
    SPECTRUM_AXIS,
    SpectralInput,
    parse_peaks,
    parse_spectrum,
    spectrum_template,
)
from openmolspec_ui.ui import APP_CSS, metric_card, page_hero
from openmolspec_ui.portal import (OnlinePredictionService, primary_navigation, dataset_page,
                                  documentation_page, ms_prediction_page)


st.set_page_config(
    page_title="OpenMolSpec Studio",
    page_icon="◌",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)
navigation = primary_navigation(st)


@st.cache_resource(show_spinner=False)
def get_service(online: bool = False) -> OpenMolSpecService:
    service_type = OnlinePredictionService if online else OpenMolSpecService
    return service_type(discover_assets())


service = get_service(navigation == "prediction")


def sidebar(workflows: bool = True) -> str:
    with st.sidebar:
        st.markdown('<div class="brand">OpenMolSpec</div>', unsafe_allow_html=True)
        st.markdown('<div class="brand-title">Spectrum–Structure<br>Workbench</div>', unsafe_allow_html=True)
        page = st.radio(
            "工作区",
            (
                "实验 NMR → 结构",
                "分子 → MS/MS",
                "构象 → 谱图",
                "谱图 → 结构检索",
                "谱图 → HOMO–LUMO gap",
                "谱图 → 结构生成",
            ),
            label_visibility="collapsed",
        ) if workflows else "任务与评测"
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("LOCAL MODEL STATUS")
        st.caption(f"推理设备 · {service.device}")
        st.caption("v1.0 · Experimental NMR / Computed IR–Raman")
        for label, (available, detail) in service.assets.capability_status(online=navigation == "prediction").items():
            css = "status-ok" if available else "status-bad"
            state = "READY" if available else "MISSING"
            st.markdown(
                f'<div class="status-row"><span>{label}</span>'
                f'<span class="{css}">{state}</span></div>',
                unsafe_allow_html=True,
            )
            st.caption(detail)
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption(f"Data root\n{service.assets.root}")
    return page


def section_header(step: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="step">{step}</div><div class="panel-title">{title}</div>'
        f'<div class="panel-sub">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def _chart_spectra(inputs: SpectralInput) -> None:
    frame = pd.DataFrame({"Wavenumber (cm⁻¹)": SPECTRUM_AXIS})
    if inputs.ir is not None:
        frame["IR"] = inputs.ir
    if inputs.raman is not None:
        frame["Raman"] = inputs.raman
    if len(frame.columns) > 1:
        st.line_chart(frame, x="Wavenumber (cm⁻¹)", height=270)


def spectrum_input(prefix: str, include_nmr: bool = True) -> SpectralInput | None:
    sample_key = f"{prefix}_sample"
    meta_key = f"{prefix}_sample_meta"
    top_left, top_right = st.columns([1, 1])
    if top_left.button("载入理论 test set 示例", key=f"{prefix}_load_sample", width="stretch"):
        try:
            sample, metadata = service.sample_spectrum()
            st.session_state[sample_key] = sample
            st.session_state[meta_key] = metadata
            st.session_state[f"{prefix}_h"] = ", ".join(
                f"{value:.4g}" for value in sample.nmr_h
            )
            st.session_state[f"{prefix}_c"] = ", ".join(
                f"{value:.4g}" for value in sample.nmr_c
            )
        except Exception as error:
            st.error(str(error))
    top_right.download_button(
        "下载两列文件模板",
        data=spectrum_template(),
        file_name="spectrum_template.csv",
        mime="text/csv",
        key=f"{prefix}_template",
        width="stretch",
    )
    ir_column, raman_column = st.columns(2)
    ir_file = ir_column.file_uploader(
        "Theoretical IR spectrum",
        type=("csv", "txt", "tsv", "dat"),
        key=f"{prefix}_ir",
        help="一列强度，或两列 wave number / intensity。",
    )
    raman_file = raman_column.file_uploader(
        "Theoretical Raman spectrum",
        type=("csv", "txt", "tsv", "dat"),
        key=f"{prefix}_raman",
        help="一列强度，或两列 wave number / intensity。",
    )
    sample = st.session_state.get(sample_key)
    use_sample_spectra = sample is not None and ir_file is None and raman_file is None
    ir = sample.ir if use_sample_spectra else None
    raman = sample.raman if use_sample_spectra else None
    try:
        if ir_file is not None:
            ir = parse_spectrum(ir_file.getvalue(), ir_file.name).intensity
        if raman_file is not None:
            raman = parse_spectrum(raman_file.getvalue(), raman_file.name).intensity
    except ValueError as error:
        st.error(str(error))
        return None
    nmr_h = nmr_c = None
    if include_nmr:
        with st.expander("计算 H/C NMR 化学位移", expanded=False):
            h_column, c_column = st.columns(2)
            h_text = h_column.text_area(
                "Computed ¹H shifts (ppm)",
                placeholder="1.24, 2.38, 7.10",
                key=f"{prefix}_h",
            )
            c_text = c_column.text_area(
                "Computed ¹³C shifts (ppm)",
                placeholder="18.2, 42.8, 128.4",
                key=f"{prefix}_c",
            )
            try:
                nmr_h, nmr_c = parse_peaks(h_text), parse_peaks(c_text)
            except ValueError as error:
                st.error(str(error))
                return None
    inputs = SpectralInput(ir=ir, raman=raman, nmr_h=nmr_h, nmr_c=nmr_c)
    if ir is None and raman is None:
        st.info("上传理论计算得到的 IR 或 Raman 文件，或先载入理论 test set 示例。")
        return None
    metadata = st.session_state.get(meta_key)
    if metadata and ir_file is None and raman_file is None:
        st.caption(
            f"理论 test set 示例：{metadata['sample_id']} · 分子来源 {metadata['source']} · {metadata['smiles']}"
        )
    _chart_spectra(inputs)
    return inputs


def molecule_summary(smiles: str) -> tuple[str, str, str]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "—", "—", "invalid"
    return (
        rdMolDescriptors.CalcMolFormula(mol),
        f"{Descriptors.MolWt(mol):.2f}",
        Chem.MolToInchiKey(mol),
    )


def nmr_profile(peaks, nucleus: str) -> pd.DataFrame:
    if nucleus == "H":
        axis = np.linspace(14.0, -1.0, 1024)
        width = 0.04
    else:
        axis = np.linspace(240.0, -20.0, 1024)
        width = 0.4
    intensity = np.zeros_like(axis)
    for peak in peaks:
        intensity += np.exp(-0.5 * ((axis - peak) / width) ** 2)
    if intensity.max() > 0:
        intensity /= intensity.max()
    return pd.DataFrame({"Chemical shift (ppm)": axis, f"¹{nucleus} NMR": intensity})


def render_candidates(records: list[dict], score_label: str = "Similarity") -> None:
    for rank, record in enumerate(records, start=1):
        smiles = str(record["smiles"])
        formula, mass, inchikey = molecule_summary(smiles)
        score = record.get("similarity", record.get("score"))
        score_text = "—" if score is None else f"{float(score):.4f}"
        drawing = smiles_png(smiles)
        with st.container(border=True):
            image_column, detail_column = st.columns(
                [0.38, 0.62], gap="large", vertical_alignment="center"
            )
            with image_column:
                if drawing is None:
                    st.warning("RDKit 无法解析该候选结构。")
                else:
                    st.image(
                        drawing,
                        caption=f"Candidate {rank:02d}",
                        width="stretch",
                        output_format="PNG",
                    )
            with detail_column:
                st.markdown(
                    f'<div class="eyebrow">RANK {rank:02d} · '
                    f'{html.escape(score_label.upper())} {score_text}</div>'
                    f'<div class="candidate-smiles"><code>{html.escape(smiles)}</code></div>'
                    f'<div class="candidate-meta">{html.escape(formula)} · '
                    f'{html.escape(mass)} g/mol · {html.escape(inchikey)}</div>',
                    unsafe_allow_html=True,
                )


def structure_to_spectrum_page() -> None:
    st.markdown(
        page_hero(
            "01 / STRUCTURE TO SPECTRUM",
            "输入分子结构，预测理论多模态光谱",
            "绘制分子或输入 SMILES 构建 3D 构象，也可上传 XYZ；预测理论 IR、Raman 与 H/C NMR。",
        ),
        unsafe_allow_html=True,
    )
    st.write("")
    input_panel, preview_panel = st.columns([1.05, 0.95], gap="large")
    molecule = None
    with input_panel.container(border=True):
        section_header(
            "STEP 01",
            "输入分子构象",
            "直接绘制二维结构、输入 SMILES，或上传已有 XYZ 坐标。",
        )
        method = st.segmented_control(
            "Input type",
            ("绘制结构", "SMILES", "XYZ"),
            default="绘制结构",
            label_visibility="collapsed",
        )
        try:
            if method == "绘制结构":
                drawn_smiles = st_ketcher(
                    "CC(=O)OC1=CC=CC=C1C(=O)O",
                    height=460,
                    molecule_format="SMILES",
                    key="structure_ketcher",
                )
                if drawn_smiles and drawn_smiles.strip():
                    st.caption(f"当前结构 · `{drawn_smiles}`")
                    molecule = molecule_from_smiles(drawn_smiles)
                else:
                    st.info("请在画布中绘制分子结构。")
            elif method == "SMILES":
                smiles = st.text_area(
                    "SMILES",
                    value="CC(=O)OC1=CC=CC=C1C(=O)O",
                    height=100,
                )
                molecule = molecule_from_smiles(smiles) if smiles.strip() else None
            else:
                xyz = st.file_uploader("XYZ file", type=("xyz",))
                molecule = molecule_from_xyz(xyz.getvalue()) if xyz else None
        except ValueError as error:
            st.error(str(error))
    with preview_panel.container(border=True):
        section_header("STEP 02", "三维构象", "拖动旋转、滚轮缩放；显示的是模型实际读取的坐标。")
        if molecule is None:
            st.info("等待有效的分子输入。")
        else:
            st.iframe(
                molecule_3d_html(molecule),
                width="stretch",
                height=430,
            )
            col1, col2, col3 = st.columns(3)
            col1.metric("Formula", molecule.formula)
            col2.metric("Atoms", molecule.atoms)
            col3.metric("Conformer", "3D")
            st.caption(molecule.source)
    run = st.button(
        "预测 IR、Raman 与 H/C NMR",
        type="primary",
        width="stretch",
        disabled=molecule is None,
    )
    if run and molecule is not None:
        with st.spinner("正在预测 Hessian 与响应张量并重建理论谱图…"):
            try:
                result = service.predict_spectra(molecule)
            except Exception as error:
                st.error(f"推理失败：{error}")
                return
        section_header("STEP 03", "预测结果", "振动谱为 400–4000 cm⁻¹；NMR 输出为逐原子未指认化学位移。")
        frame = pd.DataFrame(
            {
                "Wavenumber (cm⁻¹)": result["wavenumber"],
                "IR": result["ir"],
                "Raman": result["raman"],
            }
        )
        nmr_frame = pd.DataFrame(
            {
                "¹H shift (ppm)": pd.Series(result["nmr_h"]),
                "¹³C shift (ppm)": pd.Series(result["nmr_c"]),
            }
        )
        mode_frame = pd.DataFrame(
            {
                "Frequency (cm⁻¹)": result["mode_frequencies"],
                "IR activity": result["ir_activities"],
                "Raman activity": result["raman_activities"],
            }
        )
        tab_ir, tab_raman, tab_h, tab_c, tab_data = st.tabs(
            ("IR", "Raman", "¹H NMR", "¹³C NMR", "Data")
        )
        tab_ir.line_chart(frame, x="Wavenumber (cm⁻¹)", y="IR", height=360)
        tab_raman.line_chart(frame, x="Wavenumber (cm⁻¹)", y="Raman", height=360)
        tab_h.line_chart(nmr_profile(result["nmr_h"], "H"), x="Chemical shift (ppm)", height=360)
        tab_h.dataframe(nmr_frame[["¹H shift (ppm)"]].dropna(), width="stretch")
        tab_c.line_chart(nmr_profile(result["nmr_c"], "C"), x="Chemical shift (ppm)", height=360)
        tab_c.dataframe(nmr_frame[["¹³C shift (ppm)"]].dropna(), width="stretch")
        with tab_data:
            st.caption("Reconstructed theoretical spectra · per-record min–max intensity")
            st.dataframe(frame, width="stretch", height=260)
            st.caption("Predicted positive harmonic modes and response activities")
            st.dataframe(mode_frame, width="stretch", height=240)
            st.caption("Unassigned atom-level NMR shifts")
            st.dataframe(nmr_frame, width="stretch", height=220)
        export = frame.copy()
        export["¹H shift (ppm)"] = pd.Series(result["nmr_h"])
        export["¹³C shift (ppm)"] = pd.Series(result["nmr_c"])
        st.download_button(
            "下载 IR / Raman / NMR 结果 CSV",
            export.to_csv(index=False).encode(),
            "openmolspec_predicted_spectra.csv",
            "text/csv",
            width="stretch",
        )
        st.markdown(
            '<div class="model-note">所有输出均对应 OpenMolSpec 理论计算域，不使用实验光谱。'
            "IR/Raman 由四个 1M EquiformerV3 模型依次预测 Hi、Hij、∂μ/∂R、∂α/∂R，"
            "再通过质量加权正则模、0.965 频率缩放和 Lorentz 展宽重建；H/C NMR 使用 1M 原子级模型。"
            "NMR 峰位尚未分配给实验峰，也不包含 J coupling。</div>",
            unsafe_allow_html=True,
        )


def retrieval_page() -> None:
    st.markdown(
        page_hero(
            "02 / SPECTRAL RETRIEVAL",
            "输入理论谱图，发现候选分子",
            "输入应来自 OpenMolSpec 同域理论计算；IR/Raman 与计算 H/C 位移共同用于 test set 分子库检索。",
        ),
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        section_header("STEP 01", "导入多模态理论谱图", "理论 IR、Raman 与计算 H/C 位移的可用模态共同参与排序。")
        inputs = spectrum_input("retrieval", include_nmr=True)
    limit = st.slider("返回候选数", 3, 15, 8)
    if st.button(
        "检索分子结构",
        type="primary",
        width="stretch",
        disabled=inputs is None,
    ):
        with st.spinner("正在建立候选库索引并检索…"):
            try:
                records = service.retrieve(inputs, limit)  # type: ignore[arg-type]
            except Exception as error:
                st.error(f"检索失败：{error}")
                return
        section_header("STEP 02", "候选结构", "分数综合可用的振动谱余弦相似度与 H/C NMR 峰集合匹配。")
        render_candidates(records)
        export = pd.DataFrame(records)
        st.download_button(
            "下载检索结果 CSV",
            export.to_csv(index=False).encode(),
            "openmolspec_retrieval.csv",
            "text/csv",
            width="stretch",
        )
        backend = records[0].get("backend") if records else "spectral-cosine"
        message = (
            "当前查询使用 Vib2Mol learned embeddings，并在整个 test set 分子候选库中排序。"
            if backend == "vib2mol-embedding"
            else "当前运行环境没有可用 CUDA，查询已回退到 test set 谱库的可解释余弦基线。"
        )
        st.markdown(f'<div class="model-note">{message}</div>', unsafe_allow_html=True)


def gap_page() -> None:
    st.markdown(
        page_hero(
            "03 / SPECTRUM TO PROPERTY",
            "融合理论光谱，预测分子能隙",
            "使用 1M 理论计算数据训练的 Shared Spectroscopy Transformer；IR、Raman 与计算 H/C 位移共用一个编码器。",
        ),
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        section_header("STEP 01", "输入多模态理论光谱", "缺失模态会以空输入处理；加入计算 NMR 位移通常能提供额外结构约束。")
        inputs = spectrum_input("gap", include_nmr=True)
    if st.button(
        "预测 HOMO–LUMO gap",
        type="primary",
        width="stretch",
        disabled=inputs is None,
    ):
        with st.spinner("正在运行 1M gap checkpoint…"):
            try:
                result = service.predict_gap(inputs)  # type: ignore[arg-type]
            except Exception as error:
                st.error(f"推理失败：{error}")
                return
        section_header(
            "STEP 02",
            "性质预测与输入条件",
            "预测能隙对应当前输入；完整输入配置为 IR + Raman + H/C NMR。",
        )
        col1, col2, col3 = st.columns(3)
        col1.markdown(
            metric_card(
                "Predicted gap",
                f"{result['gap_ev']:.3f} eV",
                "当前输入 · HOMO–LUMO",
            ),
            unsafe_allow_html=True,
        )
        col2.markdown(
            metric_card(
                "Input coverage",
                f"{len(result['input_modalities'])} / 4",
                " · ".join(result["input_modalities"]),
            ),
            unsafe_allow_html=True,
        )
        col3.markdown(
            metric_card(
                "Checkpoint modality",
                "IR + Raman + H/C",
                "Shared spectroscopy Transformer",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="model-note">预测结果已从训练时的标准化空间还原为 eV。'
            "离线评测不代表当前样本的预测区间或单样本误差；"
            "输入谱图仍应与训练域的 400–4000 cm⁻¹ 范围一致。</div>",
            unsafe_allow_html=True,
        )
        if len(result["input_modalities"]) < 4:
            st.warning("当前输入缺少训练时使用的部分谱型，属于缺通道推理；请与完整输入结果分开解读。")
        audit = Path(__file__).resolve().parent / "results/gap_protocol_random128_20261116.json"
        if audit.is_file():
            rows = json.loads(audit.read_text()).get("results", [])
            selected = next((row for row in rows if row["task"] == "vibrational.gap.ir_raman_hc" and row["status"] == "passed"), None)
            if selected:
                st.caption(f"离线完整输入检查 · {selected['metrics']['examples']} 个随机样本 · MAE {selected['metrics']['mae_ev']:.3f} eV；不代表单样本误差。")


def generation_page() -> None:
    st.markdown(
        page_hero(
            "04 / SPECTRUM TO GENERATION",
            "从理论光谱出发，生成分子结构",
            "Vib2Mol 从 OpenMolSpec 理论 IR、Raman 与计算 H/C 位移生成结构，并由 matching head 重新排序。",
        ),
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        section_header("STEP 01", "输入多模态理论光谱", "理论 IR、Raman 与计算 H/C 位移都会用于模型；缓存回退也使用四模态定位锚点。")
        inputs = spectrum_input("generation", include_nmr=True)
    limit = st.slider("生成候选数", 3, 12, 8)
    if st.button(
        "生成结构候选",
        type="primary",
        width="stretch",
        disabled=inputs is None,
    ):
        with st.spinner("正在匹配查询并读取 Vib2Mol beam 结果…"):
            try:
                result = service.generate(inputs, limit)  # type: ignore[arg-type]
            except Exception as error:
                st.error(f"生成失败：{error}")
                return
        section_header(
            "STEP 02",
            "生成候选",
            "展示多个有效且互不重复的结构可能性，并按光谱–结构匹配置信度排序。",
        )
        anchor = result["anchor"]
        if anchor is None:
            note = (
                f'当前结果由 Vib2Mol 对上传谱图执行 {result.get("beam_size", "多路径")} 条 beam search，'
                "规范化并去除重复结构后，再由 matching head 重新排序。"
            )
        else:
            note = (
                f'缓存回退汇总了 {result.get("anchors_used", 1)} 个相近理论谱锚点的已验证 beam 候选并去重；'
                f'最高相似锚点：<code>{anchor["sample_id"]}</code> · '
                f'谱图相似度 {result["anchor_similarity"]:.4f}。这些候选不标作对上传谱图的直接生成。'
            )
        st.markdown(f'<div class="model-note">{note}</div>', unsafe_allow_html=True)
        candidates = result["candidates"]
        if len(candidates) < limit:
            st.info(f"模型得到 {len(candidates)} 个有效且不重复的结构候选。")
        render_candidates(candidates, score_label="candidate confidence")
        st.caption("生成结果来自当前输入。离线准确率取决于输入模态、候选去重、beam 和重排设置，详见任务文档。")
        export = pd.DataFrame(result["candidates"])
        st.download_button(
            "下载生成结果 CSV",
            export.to_csv(index=False).encode(),
            "openmolspec_generation.csv",
            "text/csv",
            width="stretch",
        )


page = sidebar(navigation == "prediction")
if navigation == "dataset":
    dataset_page(st)
elif navigation == "documentation":
    documentation_page(st)
elif page == "任务与评测":
    from openmolspec_ui.benchmark import benchmark_page
    benchmark_page(st)
elif page == "实验 NMR → 结构":
    from openmolspec_ui.benchmark import nmr_page
    nmr_page(st, service.device)
elif page == "分子 → MS/MS":
    ms_prediction_page(st)
elif page == "构象 → 谱图":
    structure_to_spectrum_page()
elif page == "谱图 → 结构检索":
    retrieval_page()
elif page == "谱图 → HOMO–LUMO gap":
    gap_page()
else:
    generation_page()

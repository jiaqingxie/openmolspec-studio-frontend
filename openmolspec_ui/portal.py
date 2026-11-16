"""Primary navigation, data downloads, and direct prediction entry points."""

import html
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .inference import OpenMolSpecService
from .config import documentation_url


class OnlinePredictionService(OpenMolSpecService):
    """Online results always come from the query's checkpoint inference."""

    def retrieve(self, inputs, limit=8):
        return self._retrieve_vib2mol(inputs, limit)

    def generate(self, inputs, limit=5):
        return self._generate_vib2mol(inputs, limit)


def primary_navigation(st):
    view = st.query_params.get("view", "tool")
    if view not in ("tool", "dataset", "prediction", "documentation"):
        view = "tool"
    documentation = documentation_url()
    links = [("Tool", "?view=tool", "tool"), ("Dataset Download", "?view=dataset", "dataset"),
             ("Prediction (Online)", "?view=prediction", "prediction"), ("Full documentation", documentation, "documentation")]
    st.markdown('''<style>.oms-nav{display:flex;flex-wrap:wrap;gap:8px;padding:12px 0 22px;border-bottom:1px solid #dfe5dc;margin-bottom:24px}.oms-nav a{padding:10px 18px;border-radius:7px;color:#293c35;text-decoration:none;font-weight:600}.oms-nav a.active{background:#244d3d;color:white}.oms-nav a:hover{background:#e7eee7;color:#173c2d}</style>''', unsafe_allow_html=True)
    anchors = "".join(f'<a class="{"active" if key == view else ""}" href="{html.escape(url, quote=True)}" target="_self">{title}</a>' for title, url, key in links)
    st.markdown(f'<nav class="oms-nav" aria-label="Primary navigation">{anchors}</nav>', unsafe_allow_html=True)
    return view


def dataset_page(st):
    st.title("Dataset Download")
    st.write("获取原始数据与输入模板；下载后请保留来源、划分、单位和许可信息。")
    distribution = os.environ.get("OPENMOLSPEC_DATASET_URL")
    if distribution:
        st.link_button("Download OpenMolSpec dataset", distribution)
    else:
        st.info("OpenMolSpec 完整数据的公共下载地址尚未配置。以下为已知原始分发入口。")
    for label, url in [("MassSpecGym · experimental MS/MS", "https://huggingface.co/datasets/roman-bushuiev/MassSpecGym"),
                       ("NMRNet · datasets and frozen weights", "https://zenodo.org/records/19142375"),
                       ("GLACIER / ICEBERG · pretrained model releases", "https://github.com/coleygroup/ms-pred"),
                       ("NMRNet++ · datasets and frozen weights", "https://github.com/YongqiJin/NMRNetplusplus")]:
        st.link_button(label, url)
    from openmolspec_bench.catalog import records
    st.download_button("Download task catalog JSON", json.dumps(records(), ensure_ascii=False, indent=2), "openmolspec_tasks.json", "application/json")
    from .spectra import spectrum_template
    st.download_button("Download IR/Raman CSV template", spectrum_template(), "vibrational_input_template.csv", "text/csv")
    sample = {"h_nmr": "1.20 (t, J=7 Hz, 3H), 3.65 (q, J=7 Hz, 2H)", "c_nmr": "18.2, 58.3", "formula": "C2H6O"}
    st.download_button("Download NMR input example", json.dumps(sample, indent=2), "nmr_input_example.json", "application/json")


def documentation_page(st):
    st.title("Full documentation")
    st.link_button("Open full documentation · 中英文完整手册", documentation_url())
    st.caption("Read the Docs 已上线。下方也可浏览本地任务说明并下载 notebook。")
    root = Path(__file__).resolve().parents[1]
    language = st.selectbox("Language / 语言", ["English", "简体中文"])
    suffix = "" if language == "English" else ".zh"
    pages = sorted((root / "documentation/tasks").glob(f"*{suffix}.md"))
    if not suffix:
        pages = [path for path in pages if not path.name.endswith(".zh.md")]
    if pages:
        selected = st.selectbox("Task documentation", pages, format_func=lambda path: path.stem)
        st.markdown(selected.read_text())
        st.download_button("Download Markdown", selected.read_bytes(), selected.name, "text/markdown")
        notebook = root / "documentation/notebooks" / (selected.name[:-3] + ".ipynb")
        if notebook.is_file():
            st.download_button("Download notebook", notebook.read_bytes(), notebook.name, "application/x-ipynb+json")


def ms_prediction_page(st):
    import numpy as np
    import pandas as pd

    st.title("Molecule → MS/MS")
    st.write("使用已有 GLACIER / ICEBERG 权重，按输入分子与采集条件直接预测谱图。")
    model = st.selectbox("Model", ["GLACIER", "ICEBERG"])
    smiles = st.text_input("SMILES", "CCO")
    adduct = st.selectbox("Adduct", ["[M+H]+", "[M-H]-", "[M+Na]+", "[M+NH4]+", "[M+K]+"])
    energy = st.number_input("Collision energy · 使用对应模型与仪器的数值约定", min_value=0., max_value=200., value=20.)
    instrument = st.selectbox("Instrument", ["Orbitrap", "QTOF"])
    if st.button("Predict MS/MS", type="primary"):
        runtime = os.environ.get("OPENMOLSPEC_MS_PYTHON", sys.executable)
        root = Path(__file__).resolve().parents[1]
        try:
            with tempfile.TemporaryDirectory(prefix="openmolspec-ms-online-") as directory:
                request, result = Path(directory) / "request.json", Path(directory) / "prediction.json"
                request.write_text(json.dumps({"smiles": smiles, "adduct": adduct, "collision_energy": energy, "instrument": instrument}))
                command = [runtime, "-m", "openmolspec_bench.ms", "--model", model.lower(), "--predict-request", str(request), "--output", str(result)]
                for flag, variable in (("--source", "OPENMOLSPEC_MS_SOURCE"), ("--weights", "OPENMOLSPEC_MS_WEIGHTS")):
                    if os.environ.get(variable):
                        command.extend([flag, os.environ[variable]])
                with st.spinner("正在运行冻结模型"):
                    completed = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                               env=dict(os.environ, MPLCONFIGDIR="/tmp/openmolspec-mpl", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="2"))
                if completed.returncode or not result.is_file():
                    print(completed.stderr, file=sys.stderr)
                    raise RuntimeError("当前 MS 服务未完成推理；请检查已配置的模型环境和权重。")
                payload = json.loads(result.read_text())
            values = np.asarray(payload["predicted_peaks"])
            frame = pd.DataFrame(values, columns=["m/z", "intensity"])
            st.scatter_chart(frame, x="m/z", y="intensity")
            st.dataframe(frame.sort_values("intensity", ascending=False).head(100), hide_index=True, width="stretch")
            st.caption("Direct frozen-checkpoint inference · no cache replay")
            st.download_button("Download prediction JSON", json.dumps(payload, ensure_ascii=False, indent=2), "ms_prediction.json", "application/json")
        except Exception as error:
            st.error(str(error))


def assignment_page(st):
    import pandas as pd
    from rdkit import Chem
    from rdkit.Chem import Draw

    st.title("NMR 峰 → 原子指认")
    st.write("输入已知分子和实测峰，预测逐原子位移后进行匹配。结果给出候选指认及未匹配项。")
    smiles = st.text_input("分子 SMILES", "CCO")
    nucleus = st.selectbox("Nucleus", ["13C", "1H"])
    text = st.text_area("化学位移列表 · ppm，用逗号分隔", "18.2, 58.3" if nucleus == "13C" else "1.2, 3.65, 2.1")
    tolerance = st.number_input("匹配容差 · ppm", min_value=0.01, value=5.0 if nucleus == "13C" else 0.5)
    st.caption("对称等价位点合并；超过容差的峰保留为未匹配。匹配残差不是原子指认准确率。")
    if st.button("预测并指认", type="primary"):
        try:
            peaks = [float(v.strip()) for v in text.replace("，", ",").replace("\n", ",").split(",") if v.strip()]
            root = Path(__file__).resolve().parents[1]
            models = os.environ.get("OPENMOLSPEC_MODELS_ROOT", str(root.parent.parent/"models"))
            with tempfile.TemporaryDirectory(prefix="openmolspec-assignment-ui-") as temporary:
                request, result = Path(temporary)/"request.json", Path(temporary)/"result.json"
                request.write_text(json.dumps({"smiles": smiles, "nucleus": nucleus, "peaks_ppm": peaks, "tolerance_ppm": tolerance}))
                command = [os.environ.get("OPENMOLSPEC_NMR_PYTHON", sys.executable), "-m", "openmolspec_bench.assignment",
                           "--models-root", models, "--request", str(request), "--output", str(result)]
                with st.spinner("正在预测逐原子位移并匹配谱峰"):
                    done = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                          env=dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="1"))
                if done.returncode or not result.is_file():
                    print(done.stderr, file=sys.stderr)
                    raise RuntimeError("原子指认推理失败，请检查 NMR 模型环境与权重配置。")
                payload = json.loads(result.read_text())
            molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
            for atom in molecule.GetAtoms():
                atom.SetAtomMapNum(0)
                atom.SetProp("atomNote", str(atom.GetIdx()))
            st.image(Draw.MolToImage(molecule, size=(850, 450)), caption="图中标注与结果表均使用从 0 开始的原子编号。")
            st.dataframe(pd.DataFrame(payload["assignments"]), hide_index=True, width="stretch")
            st.write({"匹配峰比例": payload["matched_fraction"], "未匹配峰序号": payload["unmatched_peak_indices"],
                      "未匹配原子位点": payload["unmatched_sites"]})
            st.caption("这些是模型提出的指认；需结合实验相关谱确认。当前模型未输入溶剂条件。")
            st.download_button("下载指认 JSON", json.dumps(payload, ensure_ascii=False, indent=2), "nmr_assignment.json", "application/json")
        except (ValueError, RuntimeError) as error:
            st.error(str(error))


def solvent_transfer_page(st):
    import pandas as pd

    st.title("跨溶剂化学位移 · 实验参考检索基线")
    st.write("输入源溶剂中的实测位移，检索其他分子的跨溶剂位移差，估计目标溶剂中的峰位置。")
    st.info("当前是无需训练的参考检索基线；专用神经网络模型尚未接入。参考相似度和原始测量来源随结果给出。")
    smiles = st.text_input("分子 SMILES", "CCO")
    nucleus = st.selectbox("Nucleus", ["13C", "1H"])
    choices = ["CDCl3", "DMSO-d6", "CD3OD", "acetone-d6", "C6D6", "D2O", "CD3CN", "pyridine-d5", "CCl4"]
    source = st.selectbox("源溶剂", choices, index=0)
    target = st.selectbox("目标溶剂", choices, index=1)
    text = st.text_area("源溶剂峰列表 · ppm", "18.2, 58.3" if nucleus == "13C" else "1.2, 3.65")
    if st.button("估计跨溶剂位移", type="primary"):
        try:
            from openmolspec_bench.solvent_transfer import ReferenceTransfer
            from openmolspec_bench.data import sha256
            root = Path(__file__).resolve().parents[1]
            library_path = Path(os.environ.get("OPENMOLSPEC_SOLVENT_REFERENCE", str(root/".runtime/solvent_reference_library.json")))
            if not library_path.is_file():
                raise ValueError("跨溶剂参考库尚未配置，请设置 OPENMOLSPEC_SOLVENT_REFERENCE。")
            model = ReferenceTransfer(json.loads(library_path.read_text()))
            peaks = [float(v.strip()) for v in text.replace("，", ",").replace("\n", ",").split(",") if v.strip()]
            if not peaks:
                raise ValueError("请输入至少一个源溶剂峰。")
            predictions = [model.predict(smiles,nucleus,source,target,value) for value in peaks]
            frame = [{"源位移 ppm": p["source_ppm"], "目标估计 ppm": p["predicted_target_ppm"],
                      "位移变化 ppm": p["predicted_delta_ppm"], "参考相似度": p["tanimoto_similarity"],
                      "参考分子": p["reference"]["identity"], "参考原子 ID": p["reference"]["atom_id"]} for p in predictions]
            st.dataframe(pd.DataFrame(frame),hide_index=True,width="stretch")
            st.caption("已排除与查询分子连接关系相同的参考记录。相似度不是正确概率；温度、浓度和实验参考差异可能影响结果。")
            payload = {"completed":True,"task":"nmr.solvent_transfer","model_kind":"retrieval_baseline_not_neural_model",
                       "training_performed":False,"library_sha256":sha256(library_path),"predictions":predictions}
            st.download_button("下载迁移结果 JSON",json.dumps(payload,ensure_ascii=False,indent=2),"solvent_transfer.json","application/json")
        except ValueError as error:
            st.error(str(error))

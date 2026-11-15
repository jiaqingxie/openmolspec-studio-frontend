"""Primary navigation, data downloads, and direct prediction entry points."""

import html
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .inference import OpenMolSpecService


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
    documentation = os.environ.get("OPENMOLSPEC_DOCS_URL", "?view=documentation")
    if not documentation.startswith(("https://", "http://", "?")):
        documentation = "?view=documentation"
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
                       ("SpectraLLM · released models and data preparation", "https://github.com/OPilgrim/SpectraLLM")]:
        st.link_button(label, url)
    from openmolspec_bench.catalog import records
    st.download_button("Download task catalog JSON", json.dumps(records(), ensure_ascii=False, indent=2), "openmolspec_tasks.json", "application/json")
    from .spectra import spectrum_template
    st.download_button("Download IR/Raman CSV template", spectrum_template(), "vibrational_input_template.csv", "text/csv")
    sample = {"h_nmr": "1.20 (t, J=7 Hz, 3H), 3.65 (q, J=7 Hz, 2H)", "c_nmr": "18.2, 58.3", "formula": "C2H6O"}
    st.download_button("Download NMR input example", json.dumps(sample, indent=2), "nmr_input_example.json", "application/json")


def documentation_page(st):
    st.title("Full documentation")
    st.info("中英文文档和 notebook 已随代码准备。Read the Docs 尚待成功构建；发布后此栏目将跳转到实际网址。")
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

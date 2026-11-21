"""Render the bilingual fitted-model record from the locked benchmark comparison."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = {"11B": "OB(O)c1ccccc1", "29Si": "C[Si](C)(C)C", "19F": "Fc1ccccc1"}


def model_card(nucleus, en):
    r = json.loads((ROOT / "results" / f"forward_selection_{nucleus}.json").read_text())
    test = r["test"]["selected"]
    val = r["validation"][0]["macro_mae_ppm"]
    mix = ", ".join(f"{v:.0%} {name}" for name, v in r["selected"].items())
    tool = "https://jiaqingxie.github.io/openmolspec.github.io/#tool-" + nucleus.lower()
    archive = f"https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/solution-nmr-v2/openmolspec-{nucleus}.zip"
    if en:
        title = f"{nucleus} solution chemical shifts"
        text = (
            f"The validation-selected model predicts chemical shifts in ppm from a SMILES string and an optional solvent. "
            f"The training partition contains {r['training_identities']:,} molecular connectivities. "
            f"Models were selected by giving each of {r['validation_identities']:,} validation connectivities equal weight. "
            f"The selected combination ({mix}) achieved {val:.2f} ppm validation MAE.\n\n"
            f"The independent test contains {test['identities']:,} connectivities and {test['observations']:,} measured single-environment observations. "
            f"Observation MAE is **{test['mae_ppm']:.2f} ppm**, molecule-weighted MAE is **{test['molecule_macro_mae_ppm']:.2f} ppm**, "
            f"and the 90th percentile absolute error is {test['p90_absolute_ppm']:.2f} ppm. "
            "Each prediction lists the input atom indices belonging to that symmetry class. "
            "Multi-environment site assignments require separate validation.\n\n"
            f"[Run a structure online]({tool}) · [Download the model and SDK]({archive})"
        )
    else:
        title = f"{nucleus} 溶液化学位移预测"
        text = (
            f"输入 SMILES 和可选溶剂，预测各等价原子组的位移（ppm）。训练集含 {r['training_identities']:,} 种分子连通结构。"
            f"在 {r['validation_identities']:,} 种验证分子上按分子等权选型。最终组合（{mix}）的验证 MAE 为 {val:.2f} ppm。\n\n"
            f"独立测试集含 {test['identities']:,} 种分子和 {test['observations']:,} 条单环境实测记录。"
            f"逐观测 MAE 为 **{test['mae_ppm']:.2f} ppm**，分子等权 MAE 为 **{test['molecule_macro_mae_ppm']:.2f} ppm**，"
            f"绝对误差的第 90 百分位为 {test['p90_absolute_ppm']:.2f} ppm。"
            "输出保留输入 SMILES 中从零起算的原子编号。多环境的逐峰归属需另行评测。\n\n"
            f"[在线预测]({tool}) · [下载模型与 SDK]({archive})"
        )
    install = (
        "Extract the ZIP and run the following commands in its directory."
        if en else "解压 ZIP，在解压目录中安装 SDK 并运行预测。"
    )
    example = (
        "from openmolspec.model import SolutionShiftPredictor\n\n"
        'model = SolutionShiftPredictor("model")\n'
        f'print(model.predict("{SAMPLES[nucleus]}", "CDCl3"))'
    )
    return f"# {title}\n\n{text}\n\n{install}\n\n```bash\npython -m pip install \"./openmolspec-1.0.0-py3-none-any.whl[phosphorus-gnn,solution-nmr]\"\n```\n\n```python\n{example}\n```\n"

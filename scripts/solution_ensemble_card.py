"""Render the bilingual fitted-model record from the locked benchmark comparison."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = {"31P": "CCOP(=O)(OCC)OCC", "11B": "OB(O)c1ccccc1", "29Si": "C[Si](C)(C)C", "19F": "Fc1ccccc1"}


def model_card(nucleus, en):
    r = json.loads((ROOT / "results" / f"forward_selection_{nucleus}.json").read_text())
    test = r["test"]["selected"]
    val = r["validation"][0]["macro_mae_ppm"]
    mix = ", ".join(f"{v:.0%} {name}" for name, v in r["selected"].items())
    tool = "https://jiaqingxie.github.io/openmolspec.github.io/#tool-" + nucleus.lower()
    tag = r.get("release_tag", "solution-nmr-v2")
    archive = f"https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/{tag}/openmolspec-{nucleus}.zip"
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
    if "previous_default" in r["test"] and r.get("deployment_approved"):
        prior = r["test"]["previous_default"]
        lo, hi = r["paired_test_differences"]["previous_default"]["molecule_bootstrap_ci95"]
        previous_url = f"https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/tag/{r.get('previous_release_tag', 'solution-nmr-v2')}"
        text += (
            f"\n\nOn the same molecules, the previous release scored {prior['mae_ppm']:.2f} ppm per observation and "
            f"{prior['molecule_macro_mae_ppm']:.2f} ppm per molecule. The paired 95% bootstrap interval for the change in molecule-weighted MAE "
            f"is [{lo:.3f}, {hi:.3f}] ppm. [Previous release]({previous_url})"
            if en else
            f"\n\n在同一批测试分子上，上一版的逐观测 MAE 为 {prior['mae_ppm']:.2f} ppm，分子等权 MAE 为 {prior['molecule_macro_mae_ppm']:.2f} ppm。"
            f"按分子配对重采样，新版相对上一版的分子等权 MAE 差值的 95% 区间为 [{lo:.3f}, {hi:.3f}] ppm。[上一版模型]({previous_url})"
        )
    elif nucleus == "31P" and r.get("deployment_approved"):
        first = r["test"]["31P-gnn-r1"]["molecule_macro_mae_ppm"]
        lo, hi = r["paired_test_differences"]["31P-gnn-r1"]["molecule_bootstrap_ci95"]
        old = "https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/tag/phosphorus31-v2"
        text += (
            f"\n\nAn independently initialized four-layer bond-message network was trained with the same 35,696 structures. "
            f"The previous deployed GNN scored {first:.2f} ppm per connectivity on the same test. "
            f"The paired 95% interval for the change is [{lo:.2f}, {hi:.2f}] ppm. [First release]({old})"
            if en else
            f"\n\n在同一批 35,696 种训练分子上，对四层图网络独立初始化并再次训练。上一版 GNN 在同一测试集上按分子等权的 MAE 为 {first:.2f} ppm。"
            f"新旧模型误差差值的配对 95% 区间为 [{lo:.2f}, {hi:.2f}] ppm。[首次发布的模型与对照]({old})"
        )
    record = ROOT / "results" / "phosphorus_gnn_training_runs.json"
    if nucleus == "31P" and record.is_file():
        training = json.loads(record.read_text())
        if training["model_config_sha256"] == r["model_config_sha256"]:
            widest = max(training["runs"], key=lambda item: item["hidden_width"])
            minutes, seconds = divmod(round(widest["optimizer_and_validation_seconds"]), 60)
            log = "https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/phosphorus_gnn_training_runs.json"
            text += (
                f"\n\nSMILES is converted to a 2D graph of atoms and bonds. Four message-passing layers build the phosphorus-site representation, with molecular descriptors and a solvent embedding at readout. Equivalent local environments share computations. "
                f"The widest network has {widest['parameters']:,} parameters. It reached its lowest validation error at epoch {widest['best_validation_epoch']} and stopped at epoch {widest['stopped_epoch']}. "
                f"Training and validation took {minutes} min {seconds} s after graph preparation. [Training records for all components]({log})"
                if en else
                f"\n\nSMILES 先转成以原子为节点、化学键为边的二维图。模型沿化学键传递四轮信息，再结合分子描述符和溶剂特征预测磷位移。相同的局部原子环境共享计算。"
                f"最宽的网络有 {widest['parameters']:,} 个参数，在第 {widest['best_validation_epoch']} 轮取得最低验证误差，第 {widest['stopped_epoch']} 轮早停。"
                f"从图数据准备完毕算起，训练和验证共 {minutes} 分 {seconds} 秒。[三套模型的训练记录]({log})"
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

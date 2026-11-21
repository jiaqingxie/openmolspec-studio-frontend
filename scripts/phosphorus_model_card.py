"""Generate the bilingual model card from the locked paired comparison."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/phosphorus31-v2/openmolspec-31P.zip"
TOOL = "https://jiaqingxie.github.io/openmolspec.github.io/#tool-31p"


def model_card(en):
    data = json.loads((ROOT / "results/phosphorus_gnn_selection.json").read_text())
    winner = data["winner"]
    arch = "GNN" if winner == "gnn" else "LightGBM"
    alpha = data["gnn_environment_weight"]
    title = "31P chemical shift prediction" if en else "31P 化学位移预测"
    opening = (
        f"Predict solution-state phosphorus chemical shifts in ppm from a SMILES and an optional NMR solvent. "
        f"The online tool runs the validation-selected {arch} checkpoint. Equivalent sites share a shift. Atom indices follow the input SMILES and start at zero."
        if en
        else f"输入含磷分子的 SMILES 和可选溶剂，在线工具使用通过验证集选出的 {arch} 权重预测溶液化学位移。等价磷位点共享一个峰位，原子编号按输入 SMILES 从零开始。"
    )
    links = (
        f"[Run a ³¹P prediction]({TOOL}) · [Download model and Python wheel]({ARCHIVE})"
        if en
        else f"[在线预测 ³¹P]({TOOL}) · [下载模型和 Python 安装包]({ARCHIVE})"
    )
    text = [
        f"# {title}",
        opening,
        links,
        "## " + ("Model selection" if en else "模型选择"),
    ]
    e = data["gnn_best_epoch"]
    explanation = (
        f"The four-layer graph neural network passes bond-conditioned messages between connected atoms and reads out the target phosphorus site. "
        f"Training used {data['train_identities']:,} molecular connectivities. We selected epoch {e} and a local-environment median weight of {alpha:g} on validation. "
        "The tree baseline uses 5,960 boosting rounds. Both candidates have access to the same training-only local shift medians. "
        "The criterion was validation MAE with equal weight per molecular connectivity. Test records were scored after freezing the choice."
        if en
        else f"四层图神经网络沿化学键在相邻原子间传递信息，并预测目标磷位点的化学位移。共用 {data['train_identities']:,} 种分子连通结构训练。验证集选出的 GNN 轮次为 {e}，局部环境中位数权重为 {alpha:g}。"
        "对照模型使用 5,960 轮 LightGBM。两个模型均可利用相同的训练集局部环境中位数。选型依据是验证集按分子等权计算的 MAE。模型选定后再对留出测试集评分。"
    )
    text.append(explanation)
    table = [
        (
            "| Split / model | Molecules | Observations | MAE / ppm | MAE per molecule / ppm |"
            if en
            else "| 划分及模型 | 分子数 | 观测数 | 观测 MAE / ppm | 分子等权 MAE / ppm |"
        ),
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for role in ("validation", "test"):
        for name, label in [
            ("tree", "LightGBM"),
            ("gnn_raw", "GNN alone" if en else "纯 GNN"),
            ("gnn", "GNN + local median" if en else "GNN + 局部中位数"),
        ]:
            m = data[role]["all"][name]
            desc = role if en else {"validation": "验证", "test": "测试"}[role]
            table.append(
                f"| {desc} · {label} | {m['identities']:,} | {m['observations']:,} | {m['mae_ppm']:.2f} | {m['molecule_macro_mae_ppm']:.2f} |"
            )
    text.extend(["\n".join(table), "## " + ("Test groups" if en else "测试子集")])
    table = [
        (
            "| Subset | Molecules | LightGBM MAE / ppm | GNN with local median MAE / ppm |"
            if en
            else "| 子集 | 分子数 | LightGBM 分子等权 MAE / ppm | GNN + 局部中位数分子等权 MAE / ppm |"
        ),
        "| --- | ---: | ---: | ---: |",
    ]
    for group, zh in [
        ("unseen_scaffold", "训练未见的非空 Murcko 骨架"),
        ("P=O", "P=O"),
        ("P=S", "P=S"),
        (
            "neutral P, three neighbours including a heteroatom",
            "中性三配位 P，邻位含杂原子",
        ),
        ("other P environments", "其他磷环境"),
    ]:
        a = data["test"][group]
        table.append(
            f"| {group.replace('_', ' ') if en else zh} | {a['tree']['identities']:,} | {a['tree']['molecule_macro_mae_ppm']:.2f} | {a['gnn']['molecule_macro_mae_ppm']:.2f} |"
        )
    text.append("\n".join(table))
    text.append(
        (
            "Subset MAEs weight each molecular connectivity equally. Evaluation uses one observed shift and one graph-equivalence class per spectrum. Site assignments in multisite spectra, intensities, couplings and line shapes need separate validation. This comparison uses one GNN training seed."
            if en
            else "子集 MAE 对每种分子连通性等权。正式比较使用具有一个实测峰和一个图对称环境的谱。此次 GNN 对照使用一个训练随机种子。多环境分子的峰归属、强度、耦合和线形仍需单独评测。"
        )
    )
    text.append("## " + ("Local inference" if en else "本地调用"))
    extra = "phosphorus-gnn" if winner == "gnn" else "solution-nmr"
    text.append(
        (
            "Unzip the download and run these commands inside the extracted directory."
            if en
            else "解压下载包，在解压后的目录中运行以下命令。"
        )
    )
    text.append(
        f'```bash\npython -m pip install "./openmolspec-1.0.0-py3-none-any.whl[{extra}]"\nopenmolspec-solution-shift --model-dir model --smiles "CCOP(=O)(OCC)OCC" --solvent CDCl3\n```'
    )
    text.append(
        '```python\nfrom openmolspec.model import SolutionShiftPredictor\n\npredictor = SolutionShiftPredictor("model")\nprint(predictor.predict("CCOP(=O)(OCC)OCC", "CDCl3")["environments"])\n```'
    )
    return "\n\n".join(text) + "\n"

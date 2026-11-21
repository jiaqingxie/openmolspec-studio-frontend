"""Render the H/C peak prediction comparison from its held-out audit."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def model_card(nucleus, english):
    r = json.loads(
        (ROOT / "results" / f"forward_peak_model_{nucleus}.json").read_text()
    )
    name = r["deployed_model"]
    title = (
        f"{nucleus} experimental peak-list prediction"
        if english
        else f"{nucleus} 实验峰列表预测"
    )
    if english:
        intro = f"Input a SMILES to predict peak positions in ppm. Each peak lists the contributing heavy-atom indices in input order, starting at zero. For ¹H these are the atoms to which the hydrogens are attached. Closely spaced predictions within {r['model']['merge_gap_ppm']} ppm are reported together. Hydrogen shifts at a single heavy-atom site are pooled."
        lines = [
            "| Independent corpus | Paired structures | NMRNet++ | Selected predictor | Matched fraction |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        descr = f"The two error columns give equal weight to each connectivity and include a {r['unmatched_peak_penalty_ppm']:g} ppm penalty per missing or extra peak. Model and peak-merging settings were selected on {r['selection_corpus']}, then held fixed across the following corpora. Each connectivity appears in one corpus."
    else:
        intro = f"输入 SMILES，输出各个峰的化学位移（ppm），并列出输入结构中从零起算的重原子编号。¹H 返回氢所连接的重原子。同一重原子上的多个氢取代表值；预测位移相差不超过 {r['model']['merge_gap_ppm']} ppm 的位点可合并报峰。"
        lines = [
            "| 独立谱库 | 配对分子数 | NMRNet++ | 入选模型 | 匹配峰比例 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        descr = f"两列误差均按分子连通性等权计算，每个多报或漏报的峰计 {r['unmatched_peak_penalty_ppm']:g} ppm 罚分。模型与合峰参数选自在先的 {r['selection_corpus']} 开发集。下表使用独立的分子，每种连通结构仅计入一个谱库。"
    for dataset in r["evaluation_corpora"]:
        d = r["datasets"][dataset]
        models = d["models"]
        m = models[name]
        lines.append(
            f"| {dataset} | {d['distinct_eligible_paired_connectivities']:,} | {models['nmrnetpp']['count_penalized_error_ppm']:.3f} ppm | {m['count_penalized_error_ppm']:.3f} ppm | {m['matched_fraction']:.1%} |"
        )
    site = "https://jiaqingxie.github.io/openmolspec.github.io/#tool-" + nucleus.lower()
    kit = f"https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/peak-nmr-v2/openmolspec-{nucleus}.zip"
    links = (
        f"[Run online]({site}) · [Download model and SDK]({kit})"
        if english
        else f"[在线预测]({site}) · [下载模型与 SDK]({kit})"
    )
    local = (
        "After extracting the ZIP, install the SDK and run the example in the extracted directory."
        if english
        else "解压 ZIP，在解压目录中安装 SDK 并运行示例。"
    )
    return (
        f"# {title}\n\n{intro}\n\n{descr}\n\n"
        + "\n".join(lines)
        + f"\n\n{links}\n\n{local}\n\n```bash\npython -m pip install \"./openmolspec-1.0.0-py3-none-any.whl[solution-nmr]\"\n```\n\n```python\nfrom openmolspec.model import PeakSpectrumPredictor\n\nmodel = PeakSpectrumPredictor('model')\nprint(model.predict('CCO')['peaks'])\n```\n"
    )

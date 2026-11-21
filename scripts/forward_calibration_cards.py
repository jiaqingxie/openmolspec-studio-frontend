"""Add measured HSQC and MS model comparisons to their existing bilingual task pages."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = {"nmr.hsqc.transpeaknet": "hsqc", "ms.forward.glacier": "glacier", "ms.forward.iceberg": "iceberg"}


def updated_page(page, task_id, en):
    model = PREFIXES.get(task_id)
    if not model:
        return page
    path = ROOT / "results" / f"forward_selection_{model}.json"
    if not path.is_file():
        return page
    r = json.loads(path.read_text())
    title = "## Validation and held-out comparison" if en else "## 验证与独立测试"
    if title in page:
        return page
    if model == "hsqc":
        c0, h0 = r["baseline_expert_test"]
        c1, h1 = r["selected_expert_test"]
        study = "[TransPeakNet](https://www.nature.com/articles/s42004-025-01455-9)"
        dataset = "[2DNMRGym (CC BY-NC 4.0)](https://huggingface.co/datasets/siriusxiao/2DNMRGym)"
        content = (
            f"The fitted correction uses 16,311 silver training structures and 3,968 separate validation structures. All expert test connectivities were excluded from both. On 479 expert spectra, carbon MAE moved from {c0:.3f} to **{c1:.3f} ppm** and proton MAE from {h0:.4f} to **{h1:.4f} ppm**. Correct website assignments rose from 5,141 to 5,214 of the same 7,926 observed cross-peaks. The example below records the original author checkpoint. Pass `--hsqc-author-baseline` to reproduce it."
            if en else
            f"使用 16,311 种分子的银标准谱拟合校正量，再在 3,968 种独立验证分子上选定参数。两个集合均已排除专家测试分子的连通结构。在 479 张专家指认谱上，碳 MAE 从 {c0:.3f} 降至 **{c1:.3f} ppm**，氢 MAE 从 {h0:.4f} 降至 **{h1:.4f} ppm**。同一批 7,926 个实测交叉峰中，网页正确指认的峰从 5,141 个增至 5,214 个。下方的示例来自原作者权重，可通过 `--hsqc-author-baseline` 复现。"
        )
        content += f" {study} · {dataset}"
    else:
        old, new = (r[k]["cosine_similarity"] for k in ("baseline_test", "selected_test"))
        lo, hi = r["test_cosine_difference_ci95"]
        content = (
            f"{model.upper()} was evaluated with 189 combinations of intensity scaling, precursor weighting and retained peak count. Of 384 sampled structures per MassSpecGym split, 280 validation and 327 test structures produced a scored prediction. On those same 327 test structures, mean cosine was {old:.4f} for the default and {new:.4f} for the validation-selected setting. The paired 95% interval for the difference was [{lo:.4f}, {hi:.4f}]. The website therefore uses the original model output."
            if en else
            f"在 MassSpecGym 上给 {model.upper()} 比较了 189 组峰强变换、前体峰权重与保留峰数设置。验证集和测试集各抽取 384 种结构，分别有 280 和 327 种结构获得可评分预测。在同一批 327 种测试结构上，默认模型的平均余弦相似度为 {old:.4f}，验证集选中的设置为 {new:.4f}。差值的配对 95% 区间为 [{lo:.4f}, {hi:.4f}]，网页继续使用原模型输出。"
        )
    head, body = page.split("\n\n", 1)
    summary, rest = body.split("\n\n", 1)
    return f"{head}\n\n{summary}\n\n{title}\n\n{content}\n\n{rest}"

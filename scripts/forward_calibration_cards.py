"""Add measured HSQC and MS model comparisons to their existing bilingual task pages."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = {"nmr.hsqc.transpeaknet": "hsqc", "ms.forward.glacier": "glacier", "ms.forward.iceberg": "iceberg"}


def updated_page(page, task_id, en):
    if task_id in ("nmr.forward.13C", "vibrational.forward"):
        suffix = "" if en else ".zh"
        fragment = ROOT / "scripts/doc_templates" / (task_id.replace(".", "-") + suffix + ".md")
        if task_id == "nmr.forward.13C":
            page = (page.replace("## A real recorded example", "## Recorded atomwise baseline example")
                    .replace("## Actual evaluation results", "## Earlier atomwise benchmark results")
                    .replace("## 真实运行案例", "## 先前逐原子模型的运行案例")
                    .replace("## 实际评测结果", "## 先前逐原子模型的评测结果"))
        start = page.index("## ")
        return page[:start] + fragment.read_text() + "\n" + page[start:]
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
        panels = json.loads((ROOT / "results/hsqc_benchmarks/metrics.json").read_text())["panels"]
        gym = panels["2dnmrgym"]["all_records"]
        carbon, proton, cosine = gym["carbon_mae_ppm"], gym["proton_mae_ppm"], gym["cosine"]
        spectra = gym["spectra"]
        primary = (
            f"The primary HSQC benchmark uses the official 2DNMRGym solvents and site labels. On {spectra} spectra the carbon and proton site MAEs are {carbon:.3f} and {proton:.3f} ppm, with peak-position cosine of {cosine:.4f}. WanJuan provides a second panel of partially reported experimental peaks. Run both from the project root."
            if en else
            f"主基准使用 2DNMRGym 官方的溶剂和逐位点标签。{spectra} 张谱上的 ¹³C / ¹H 位点 MAE 为 {carbon:.3f} / {proton:.3f} ppm，峰位 cosine 为 {cosine:.4f}。万卷是单独的局部报告峰基准。用项目根目录下的命令可重跑两组。"
        )
        command = "python scripts/evaluate_hsqc_panels.py --panels results/hsqc_benchmarks --source /path/to/2dNMR"
        provenance = ("The following calibration comparison uses the TransPeakNet annotation version of the same spectra. "
                      if en else "以下校准对照使用同一批谱的 TransPeakNet 作者标注版本。")
        content = f"{primary}\n\n```sh\n{command}\n```\n\n{provenance}{content}"
        content += f" {study} · {dataset}"
    else:
        old, new = (r[k]["cosine_similarity"] for k in ("baseline_test", "selected_test"))
        lo, hi = r["test_cosine_difference_ci95"]
        content = (
            f"{model.upper()} was evaluated with 189 combinations of intensity scaling, precursor weighting and retained peak count. Of 384 sampled structures per MassSpecGym split, 280 validation and 327 test structures produced a scored prediction. On those same 327 test structures, mean cosine was {old:.4f} for the default and {new:.4f} for the validation-selected setting. The paired 95% interval for the difference was [{lo:.4f}, {hi:.4f}]. The original model was retained after this first comparison."
            if en else
            f"在 MassSpecGym 上给 {model.upper()} 比较了 189 组峰强变换、前体峰权重与保留峰数设置。验证集和测试集各抽取 384 种结构，分别有 280 和 327 种结构获得可评分预测。在同一批 327 种测试结构上，默认模型的平均余弦相似度为 {old:.4f}，验证集选中的设置为 {new:.4f}。差值的配对 95% 区间为 [{lo:.4f}, {hi:.4f}]，首轮比较后保留了原模型输出。"
        )
        confirmed = json.loads((ROOT / "results" / f"forward_confirmation_{model}.json").read_text())
        old, new = (confirmed[k]["cosine_similarity"] for k in ("baseline", "candidate"))
        lo, hi = confirmed["cosine_difference_ci95"]
        n = confirmed["confirmed_identities"]
        skipped = confirmed["skipped"]
        sampled = confirmed["confirmation_sample_size"]
        valid = confirmed["validation"]["passed"]
        excluded = confirmed["original_test_removed"]
        comparison = (
            f"Settings were fixed by five-fold validation on {valid} scored structures. All {excluded} original test structures were excluded from the confirmation sample. On the same {n} scored molecules out of {sampled:,} additional MassSpecGym structures, mean cosine was {old:.4f} before calibration and {new:.4f} after calibration. The paired 95% interval for the change was [{lo:+.4f}, {hi:+.4f}]. The {skipped} remaining structures were skipped. The released predictor applies the selected calibration for the tested acquisition conditions and structures with up to 40 heavy atoms. Use one CPU thread for confirmation and set `author_baseline=True` in the SDK to reproduce the original output."
            if en else
            f"先在 {valid} 个可评分的验证结构上做五折验证并锁定设置，复核样本排除了首轮测试的全部 {excluded} 种结构。在另抽的 {sampled:,} 种 MassSpecGym 结构中，{n} 种得到配对分数，其余 {skipped} 种未计分。校准前后的平均余弦为 {old:.4f} 和 {new:.4f}，差值的配对 95% 区间为 [{lo:+.4f}, {hi:+.4f}]。发布模型在经过评测的采集条件及至多 40 个重原子的分子上采用所选校准。复核时使用一个 CPU 线程，SDK 可通过 `author_baseline=True` 复算原始输出。"
        )
        provenance = f"https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/forward_confirmation_{model}.json"
        link = "Paired comparison" if en else "配对评测记录"
        heading = "## Independent confirmation" if en else "## 新增结构复核"
        content = f"{comparison} [{link}]({provenance})\n\n{title}\n\n{content}"
        title = heading
    head, body = page.split("\n\n", 1)
    summary, rest = body.split("\n\n", 1)
    return f"{head}\n\n{summary}\n\n{title}\n\n{content}\n\n{rest}"

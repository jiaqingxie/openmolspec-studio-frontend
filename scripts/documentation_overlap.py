"""Render the checkpoint/data-history audit without changing recorded results."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def overlap_notice(en, prefix=''):
    return (
        '**Evaluation limitation:** molecular overlap with checkpoint-recorded training data is confirmed for several NMR views. The final generator also has a training-file fingerprint discrepancy. These runs do not establish independent generalization. '
        if en else
        '**评测限制：**多个 NMR 视图已确认与 checkpoint 记录的训练数据存在分子重叠，最终生成模型还存在训练文件哈希不一致。现有运行不能证明独立泛化能力。'
    ) + f' [Training-history audit / 训练历史审计]({prefix}training-overlap.md)\n\n'


def overlap_page(en):
    report = json.loads((ROOT / 'results/nmr_checkpoint_overlap_20261117.json').read_text())
    assert report['completed']
    page = '# ' + ('NMR training-history and evaluation overlap' if en else 'NMR 训练历史与评测重叠') + '\n\n'
    page += (
        'The 2026-11-17 audit compared all 39,183 records in four prepared evaluation views against the available training/validation files associated with three NMR Transformer checkpoints. It found confirmed molecular overlap and one provenance discrepancy. Saved results remain available as functional and diagnostic evidence, not independent unseen-molecule benchmarks. This audit does not cover the separate NMRNet H/C or MS weights.\n\n'
        if en else
        '2026-11-17 的审计对四份评测视图的全部 39,183 条记录，以及三个 NMR Transformer checkpoint 对应的现有训练/验证文件进行了比对，确认了分子重叠，并发现一项数据溯源差异。历史结果继续作为功能与诊断证据展示，不能作为未见分子上的独立基准。本审计不覆盖另一套 NMRNet H/C 或 MS 权重。\n\n'
    )
    page += '## ' + ('Confirmed overlap' if en else '已确认的重叠') + '\n\n'
    page += (
        'Both files in `mix_align_v2` match the hashes recorded by the retrieval checkpoint `f90bd7…` and the intermediate generator `aa2fea…`. The scan covers 3,608,853 training and 50,000 validation records. Counts below are unique evaluation identities present in each file; columns must not be added without checking their intersection.\n\n'
        if en else
        '`mix_align_v2` 的两个文件与检索权重 `f90bd7…` 和中间生成权重 `aa2fea…` 记录的哈希均一致。全文件扫描覆盖 3,608,853 条训练记录、50,000 条验证记录。下表统计各文件中出现的评测结构身份数；未检查两列交集前，不可直接相加。\n\n'
    )
    page += '| ' + ('Evaluation view | Identities | In training | In validation |' if en else '评测视图 | 结构身份数 | 与训练集重叠 | 与验证集重叠 |') + '\n| --- | ---: | ---: | ---: |\n'
    for name, target in report['evaluation_views'].items():
        a = report['models']['align']['splits']['train']['overlap'][name]
        b = report['models']['align']['splits']['val']['overlap'][name]
        page += f'| `{name}` | {target["unique_standard_inchi"]:,} | {a["overlapping_identities"]:,} ({a["fraction"]:.2%}) | {b["overlapping_identities"]:,} ({b["fraction"]:.2%}) |\n'
    page += '\n' + (
        'The final generator `bebaec…` records `aa2fea…` as its initialization checkpoint. Auditing only the final training stage would miss this earlier exposure. Zero exact identity overlap for the patent view in these two files is not proof of scaffold, source or complete training-history independence.\n\n'
        if en else
        '最终生成权重 `bebaec…` 记录的初始化来源为 `aa2fea…`。仅检查最后一阶段的训练集，会漏掉早期模型见过的分子。专利视图在这两个文件中未发现相同结构身份，仍不能据此声称骨架、来源或完整训练历史均独立。\n\n'
    )
    page += '## ' + ('Final generator: file fingerprint discrepancy' if en else '最终生成模型：文件指纹不一致') + '\n\n'
    train = report['models']['generate']['splits']['train']
    page += (
        'The run log names `data/g1_all`, but the checkpoint-recorded train digest matches `data/g1_ne/train.jsonl`, not the current `g1_all/train.jsonl`. The historical training code copied hashes from `verification.json` without recomputing file bytes. Therefore neither file is certified here as the exact historical input. The final validation file does match and has zero exact identity overlap with these four views.\n\n'
        if en else
        '运行日志指向 `data/g1_all`，但 checkpoint 保存的训练哈希与 `data/g1_ne/train.jsonl` 相符，与当前 `g1_all/train.jsonl` 不符。历史训练代码直接复制 `verification.json` 中的哈希，没有重新计算文件内容，因此本审计不能认定任一文件就是当时实际读取的完整内容。最终验证文件的哈希匹配，与四份视图均无相同结构身份。\n\n'
    )
    page += f'- Checkpoint-recorded training-file SHA-256: `{train["checkpoint_recorded_sha256"]}`\n- Current `g1_all/train.jsonl` SHA-256: `{train["sha256"]}`\n\n'
    page += (
        'For reference, the current 2,121,498-record `g1_all` file overlaps the four evaluation views by 1,982 / 181 / 4,216 / 44 identities, respectively; 16 records lack stored InChI. These are current-file statistics, not verified historical training overlap. Both the SDK and the original training entry now verify file hashes before starting a new run. No historical weights, manifests or data were rewritten, and no training was performed.\n\n'
        if en else
        '作为现有文件统计，当前 `g1_all` 的 2,121,498 条记录与上述四份视图分别重叠 1,982 / 181 / 4,216 / 44 个结构身份；另有 16 条没有保存 InChI。这些数值不能冒充已核实的历史训练重叠。新 SDK 和原训练入口现均会在启动前重新校验文件哈希。本次未改写历史权重、清单或数据，也未执行训练。\n\n'
    )
    page += '## ' + ('Identity scope and next benchmark' if en else '身份定义与后续基准') + '\n\n'
    page += (
        'Matching uses stored standard-InChI strings, generating missing evaluation IDs with RDKit. It is a molecular-identity check, not a comparison of identical spectral records, scaffolds, all stereoisomers or patent families. Stored training IDs were not recomputed for every molecule. Independent benchmarks must exclude relevant training/validation identities across initialization stages, resolve the final-stage discrepancy and keep acquisition/source controls explicit. A 32-candidate retrieval score, even 100%, is not a substitute.\n\n'
        if en else
        '比对采用保存的 standard-InChI 字符串，评测记录缺少身份时由 RDKit 生成。这是分子身份检查，不是相同原始谱图、骨架、所有立体异构体或专利家族的重叠检查；没有对每条训练记录重新生成 InChI。后续独立基准需要排除初始化各阶段相关训练/验证身份，解决末阶段文件差异，并明确采集条件与来源控制。即使 32 个候选的检索得到 100%，也不能替代这些工作。\n\n'
    )
    page += '[Full audit JSON / 完整审计](assets/reports/nmr_checkpoint_overlap_20261117.json) · [Model review / 模型检查](model-audit.md) · [SDK](api.md)\n'
    return page

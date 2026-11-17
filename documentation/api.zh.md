# Python SDK — OpenMolSpec v1.0

数据加载、模型类、训练准备和统一评测入口现已实现。基础安装不依赖第三方库。当前是 v1.0 SDK：冻结推理已有实际运行证据；训练启动器已用微型 train/val 示例完成编码器和生成器各一步训练，并验证 checkpoint 保存、配置重载与推理结果一致；这是软件链路验证，不是学习性能结论。

## 安装

[带版本号的发布页](https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/tag/v1.0)提供约 250 KB 的 wheel 及校验和。使用数据加载与模型接口时，可以直接安装到自己的环境：

```bash
python -m pip install "https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/v1.0/openmolspec-1.0.0-py3-none-any.whl"
```

需要 notebook、源码及可选依赖时，克隆仓库：

```bash
git clone --branch release/openmolspec-v1 https://github.com/jiaqingxie/openmolspec-studio-frontend.git
cd openmolspec-studio-frontend
python3 -m venv .venv
.venv/bin/python -m pip install .
# 按需安装数据读取与分析依赖：
.venv/bin/python -m pip install '.[data,analysis]'
# 需要使用打包的 NMR Transformer 训练器时：
# .venv/bin/python -m pip install '.[train]'
```

此 alpha 版本尚未发布到 PyPI。NMRNet、Vib2Mol 和 MS 模型通过 `python=` 使用作者环境；客户端仅向其提供 OpenMolSpec 模块，保留作者环境的 torch/numpy 版本。原始数据生产命令使用 `pip install ".[production]"` 安装依赖。

## 数据加载、来源和固定划分

```python
from openmolspec.dataset import molspectra, list_datasets

print([card['name'] for card in list_datasets()])
data = molspectra('opendatalab_nmr', root='/path/to/hc_nmr_inchi_v1')
splits = data.get_split()       # 保留已有 train / val / test
rows = splits['test'].head(3)   # 流式读取，不把全库载入内存
hc = splits['test'].select(modalities=['1H', '13C'], limit=32)
print(data.summary())
# data.verify()                # 对完整文件计算哈希，与审计版本比较
```

| 注册名称 | 文件格式 | 数据域与归属 |
| --- | --- | --- |
| `opendatalab_nmr` | `train.jsonl`、`val.jsonl`、`test.jsonl` | 团队整理的外部实验 NMR |
| `nmrspec_test`、`patent_test_10k`、`nmrexp_exp_10k`、`nmrgym_test` | `test.jsonl` | 整理后的实验评测视图 |
| `openspec_test` | `openspec_test.lmdb` | OpenMolSpec 计算谱 |
| `massspecgym_test` | `MassSpecGym_test_full.csv` | 外部实验 MS/MS |
| `massspecgym_1_5` | 版本化 `MassSpecGym.tsv`，按原始 fold 过滤 | 外部实验 MS/MS；v1.5 |

`root` 接受目录；只有一个测试文件的视图也可直接传文件。旧 LMDB 内含 Python pickle，读取可信文件时需显式 `trusted=True`。原字段保留，`_openmolspec` 补充数据集、实验/计算域、划分、源文件位置和已有模态；不补造缺失采集条件。card 数量只对应审计版本，不自动等于本地文件数量，`verify()` 会拒绝版本不符的文件。

不会静默下载全量数据。公开发布地址、版本与再分发范围仍待确认；原来源及数量见[数据集说明](datasets.md)。`audit_splits(data.get_split())` 使用 RDKit 重算结构身份，通过磁盘索引检查交叉重叠，默认把同连接关系的立体异构体归组。结果仅适用于传入视图，小子集检查不能证明全库或预训练模型独立性。

## NMRNet：真实冻结推理

```python
from openmolspec.model import NMRNet

model = NMRNet.from_pretrained(
    '/path/to/models', nucleus='13C', python='/path/to/nmr-env/bin/python'
)
result = model.predict([row['smiles'] for row in rows])
print(result['records'])       # atom_indices 与 prediction_ppm
print(result['provenance']['checkpoint_sha256'])
model.save_config('nmrnet-config.json')
restored = NMRNet.from_config('nmrnet-config.json')
```

模型目录应含原始 `nmrnet/nmrnet-orig` 源码和 `nmrnet/weights/finetune/liquid`。此接口使用 CPU、液相 H/C fold 0 和原 scaler。原子索引以 RDKit AddHs(input SMILES) 的零基编号为准，生成构象也保存在来源信息中。训练重叠和溶剂影响仍未核实；B/Si/F/P 不作为已验证变体开放。[作者发布资产](https://zenodo.org/records/19142375)。

运行[真实 SDK 推理 notebook](notebooks/sdk-inference.ipynb)前，安装本包和 `requirements-docs-examples.txt`，并设置：

```bash
export OPENMOLSPEC_MODELS_ROOT=/path/to/models
export OPENMOLSPEC_NMR_PYTHON=/path/to/nmr-env/bin/python
```

notebook 会实际调用 `model.predict`，输出权重哈希，与实测峰比较并绘图。峰匹配误差不等于实验原子指认准确率。

## 模型接口

| 类 | 输入 → 输出 | SDK 训练支持 |
| --- | --- | --- |
| `NMRNet` | SMILES → H/C 原子位移；`assign` 再接收实测峰 | 暂无 |
| `NMRTransformer(stage='align')` | NMR 查询与显式候选 → 排序 | 接已有对齐训练器 |
| `NMRTransformer(stage='generate')` | NMR 与已知分子式 → SMILES | 接已有生成训练器，需对齐权重 |
| `GapModel` | IR/Raman/H/C → gap（eV） | 暂无 |
| `Vib2Mol` | IR/Raman/H/C → SMILES；`retrieve(..., rerank=True)` 对显式候选做 ITM 重排 | 暂无 |
| `MSPredictor(model='glacier' or 'iceberg')` | 结构、加合物、碰撞能和仪器 → MS/MS | 暂无 |

振动输入为 `ir`、`raman`（各 1024 点）及 `nmr_h`、`nmr_c`（ppm 数组），需采用相容参考与归一化。缺通道默认拒绝，显式 `allow_missing_modalities=True` 时才运行并标为消融。NMR 检索不输入分子式，生成必须提供。各模型支持配置保存/加载；保存路径与参数，不复制权重。

## 用自己的 NMR 数据训练

```python
from openmolspec.dataset import MolecularSpectra
from openmolspec.training import prepare_nmr_training
from openmolspec.model import NMRTransformer

custom = MolecularSpectra.from_jsonl(
    splits={'train': 'train.jsonl', 'val': 'val.jsonl'},
    name='my_experiment', domain='experimental',
)
prepared = prepare_nmr_training(custom['train'], custom['val'], 'prepared-nmr')
model = NMRTransformer(stage='align', device='cpu')
plan = model.training_plan(prepared, run_dir='runs/my-alignment', epochs=10, batch_size=32)
print(plan.describe())
print(plan.validate())
# model.fit(plan)              # 用户显式调用时才启动训练
```

记录包含 `smiles`、`formula`、`h_nmr`、`c_nmr`，以及可选 `[has_H, has_C]` 掩码。准备阶段检查分子式、核种及训练/验证集连接结构重叠。`select` 保留数据角色，既有 test 视图不能直接用于训练。启动前重新核验文件哈希和结构重叠，运行时建立新目录、日志、plan 和最佳权重哈希。生成训练还需要 `alignment_checkpoint=`；旧权重只用于初始化，不恢复优化器/调度器状态。

[已执行的训练准备 notebook](notebooks/sdk-training-preflight.ipynb) 分别使用 OpenDataLab 原 train/val 的两个真实记录，只做准备与检查，**没有训练**。另一项实际训练检查已完成两个阶段：[训练链路报告](assets/reports/sdk_training_roundtrip_20261117.json) 记录两个训练样本、两个验证样本、每阶段一次优化器更新、checkpoint 哈希和保存重载后的推理一致性。记录保留原始划分，没有使用测试集。这不构成学习性能结论。选择示例时发现一条无氢 `BrOBr` 结构附有 ¹H 记录；训练准备会拒绝这种核种缺失情况，原始加载器仍保留记录供回查。

## 任务目录与统一评测

```python
from openmolspec.task import list_tasks
from openmolspec.benchmark import Benchmark

print(list_tasks(group='nmr'))
bench = Benchmark(workspace='/path/to/OpenMolSpec', python='/path/to/runtime/bin/python')
report = bench.run('nmr.retrieval.hc.s2m', datasets=['nmrspec_test'],
                   limit=32, output='results/my-benchmark.json')
```

保留 31 项活跃评测入口，暂缓任务不运行。接口完成不等于模型准确或已独立验证；请结合[模型审计](model-audit.md)和[评测协议](protocols.md)解释结果。


完整检查四个本地评测 JSONL，共 39,183 条记录：专利 10,000 条视图中有 5 条核种与结构不一致（5 条 H 标记，其中 2 条同时有 C 标记）；另三份视图在这些检查下未发现标记。这不代表所有原谱或 268 万身份全库均已完成质量核验。[下载审计](assets/reports/sdk_nmr_input_audit_20261117.json)。


从仓库复现软件训练链路检查：

```bash
python scripts/verify_sdk_training.py \
  --python /path/to/nmr-env/bin/python \
  --work runs/sdk-training-check \
  --output results/sdk-training-check.json
```

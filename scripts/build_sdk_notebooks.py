"""Generate real SDK inference and training-preflight notebook sources."""
import argparse
import hashlib
import json
from pathlib import Path
from manual_citations import markdown as references

ROOT = Path(__file__).resolve().parents[1]


def book(kind, en):
    cells = []
    def md(text):
        cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': [text]})
    def code(text):
        cells.append({'cell_type': 'code', 'metadata': {}, 'source': [text], 'execution_count': None, 'outputs': []})
    files = ['src/openmolspec/' + n for n in ['dataset.py', 'model.py', 'training.py', '_runtime.py', '_worker.py', 'benchmark.py']]
    md(('# Python SDK: real NMR inference' if en else '# Python SDK：真实 NMR 推理') if kind == 'inference' else
       ('# Training data preparation and preflight' if en else '# 训练数据准备与启动前检查'))
    md(('This tutorial connects dataset records to the NMRNet model interface. You will inspect a molecular record, configure its model runtime, predict atomwise shifts and compare them with experimental peak positions.' if en else
        '本教程把数据记录与 NMRNet 模型接口连接起来。你将查看分子记录、配置模型环境、预测逐原子位移，并与实验峰位置比较。') if kind=='inference' else
       ('This tutorial prepares molecular spectra for learning. You will read named training/validation files, validate their chemistry and identity separation, choose model settings and inspect saved training/checkpoint results.' if en else
        '本教程准备谱学训练数据。你将读取训练／验证文件，检查分子字段和身份分离，选择模型设置，并查看保存的训练与权重结果。'))
    code("import json, os, sys, io, tempfile\nfrom pathlib import Path\nfrom IPython.display import display, SVG\nroot = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'documentation/assets').is_dir())\nfrom openmolspec.dataset import MolecularSpectra, list_datasets\nprint('Registered datasets:', [c['name'] for c in list_datasets()])")
    if kind == 'inference':
        files += ['documentation/assets/sdk-nmr-test-examples.jsonl', 'src/openmolspec/assets/datasets.json',
                  'scripts/documentation_figures.py', 'src/openmolspec/plotting.py', 'openmolspec_bench/assignment.py', 'openmolspec_bench/data.py', 'openmolspec_bench/runner.py']
        md('## 1. Read molecular spectra\n\nThe bundled NMRSpec examples include molecular structures, formulas, spectral records and reference peak arrays. Read the first record to see the fields used by prediction and evaluation.' if en else
           '## 1. 读取分子谱\n\n附带的 NMRSpec 示例包含结构、分子式、谱记录和参考峰数组。先查看第一条，了解预测与评测所使用的字段。')
        code("data = MolecularSpectra.from_jsonl(splits={'test': root / 'documentation/assets/sdk-nmr-test-examples.jsonl'}, name='documented_nmrspec_examples', domain='experimental')\nrows = data['test'].head(3)\nprint(json.dumps(rows[0], indent=2, ensure_ascii=False))\nprint('Split roles:', list(data.get_split()))")
        md('## 2. Configure and call NMRNet\n\nSet `OPENMOLSPEC_MODELS_ROOT` to the directory containing `nmrnet/`, and `OPENMOLSPEC_NMR_PYTHON` to the interpreter with the model dependencies. The call below constructs a conformer and predicts the carbon shifts. Each returned shift has a zero-based atom index.' if en else
           '## 2. 配置并调用 NMRNet\n\n`OPENMOLSPEC_MODELS_ROOT` 指向包含 `nmrnet/` 的目录，`OPENMOLSPEC_NMR_PYTHON` 指向安装了模型依赖的解释器。下面生成构象并预测碳位移，每个预测值附有 0 起始原子编号。')
        code("from openmolspec.model import NMRNet\nmodel_root = os.environ.get('OPENMOLSPEC_MODELS_ROOT')\nif not model_root:\n    raise RuntimeError('Set OPENMOLSPEC_MODELS_ROOT to the directory containing nmrnet/; see Python SDK guide')\nmodel = NMRNet.from_pretrained(model_root, nucleus='13C', python=os.environ.get('OPENMOLSPEC_NMR_PYTHON', sys.executable))\nresult = model.predict(rows[0]['smiles'])\nprint(json.dumps(result['records'], indent=2))\nprint('Checkpoint SHA-256:', result['provenance']['checkpoint_sha256'])\nassert result['training_performed'] is False")
        md('## 3. Evaluate and plot the prediction\n\n`evaluate_nmr` matches predicted shifts to the experimental peak positions and reports the residual error and coverage. The figure places reference and predicted peaks on the same ppm axis, making missing, extra and shifted peaks visible.' if en else
           '## 3. 评估并绘制预测\n\n`evaluate_nmr` 将预测位移与实验峰匹配，给出残差和覆盖率。图中参考与预测使用同一 ppm 轴，可直接观察缺失峰、额外峰和位移差。')
        code("from openmolspec.benchmark import evaluate_nmr\nreference = rows[0]['reference_peaks_ppm']\nprint(json.dumps(evaluate_nmr(result, [reference]), indent=2))\nimport matplotlib.pyplot as plt\nsys.path.insert(0, str(root / 'scripts'))\nfrom documentation_figures import render_task\nfigure_evidence = {'examples': [{'input': {'smiles': rows[0]['smiles']}}], 'plot': {'kind': 'nmr_peaks', 'smiles': rows[0]['smiles'], 'reference_ppm': reference, 'prediction_ppm': result['records'][0]['prediction_ppm'], 'label': 'Actual SDK inference; first documented NMRSpec molecule'}}\nfig = render_task('nmr.forward.13C', figure_evidence)\nimage = io.StringIO()\nfig.savefig(image, format='svg', metadata={'Date': None})\ndisplay(SVG(image.getvalue()))\nplt.close(fig)")
    else:
        files += [f'documentation/assets/sdk-nmr-{s}-examples.jsonl' for s in ('train', 'val')]
        md('## 1. Load training and validation records\n\nThe example files contain two OpenDataLab/WanJuan molecules per split. Keep the split names when importing your own files so the preparation step can check molecular overlap. Each record supplies a structure, formula, spectral text and available-channel mask.' if en else
           '## 1. 加载训练和验证记录\n\n示例文件在每个划分中各包含两个 OpenDataLab/WanJuan 分子。导入自己的文件时保留划分名称，准备阶段会检查分子重叠。每条记录提供结构、分子式、谱文本与通道掩码。')
        code("data = MolecularSpectra.from_jsonl(splits={s: root / f'documentation/assets/sdk-nmr-{s}-examples.jsonl' for s in ('train', 'val')}, name='documented_opendatalab_train_val', domain='experimental')\nfor role, view in data.get_split().items():\n    print(role, [row['smiles'] for row in view])")
        md('## 2. Prepare data and inspect a training plan\n\nPreparation validates the structure/formula relationship and H/C nucleus labels. The small Transformer configuration below uses 32 hidden channels and a batch size of two. `validate` checks the prepared files; `describe` prints the command and selected settings.' if en else
           '## 2. 准备数据并查看训练计划\n\n准备阶段检查结构与分子式是否对应，以及 H/C 核种标签。下面的小型 Transformer 使用 32 维隐藏通道、批次大小为 2。`validate` 检查准备好的文件，`describe` 打印命令与所选设置。')
        code("from openmolspec.training import prepare_nmr_training\nfrom openmolspec.model import NMRTransformer\nprepared_tmp = tempfile.TemporaryDirectory(prefix='openmolspec-training-tutorial-')\nprepared = prepare_nmr_training(data['train'], data['val'], Path(prepared_tmp.name) / 'data')\nmodel = NMRTransformer(stage='align')\nplan = model.training_plan(prepared, run_dir=Path(prepared_tmp.name) / 'run', epochs=1, batch_size=2, parameters={'hidden_size': 32, 'heads': 4, 'encoder_layers': 1, 'decoder_layers': 1, 'feedforward_size': 64, 'projection_size': 16, 'max_train_batches': 1, 'max_val_examples': 2})\nprint(json.dumps(plan.validate(), indent=2))\nprint(json.dumps(plan.describe(), indent=2))\nassert not plan.run_dir.exists()")
        md('## 3. Launch training and inspect saved checkpoints\n\nInstall the training dependencies and call `trained = model.fit(plan)` to launch the plan. The following cell reads the saved encoder and generator training report and checks checkpoint identity and save/reload prediction agreement.' if en else
           '## 3. 启动训练并查看保存的权重\n\n安装训练依赖后，调用 `trained = model.fit(plan)` 启动计划。下面读取保存的编码器与生成器训练报告，检查权重身份，以及保存重载后的预测一致性。')
        files += ['documentation/assets/reports/sdk_training_roundtrip_20261117.json']
        code("roundtrip = json.loads((root / 'documentation/assets/reports/sdk_training_roundtrip_20261117.json').read_text())\nassert roundtrip['completed'] and roundtrip['training_performed']\nassert roundtrip['test_records'] == 0\nfor stage, result in roundtrip['stages'].items():\n    assert result['save_reload_inference_equal']\n    print(stage, 'training/save/reload passed', result['checkpoint_sha256'])\nprint('Verified training stages:', len(roundtrip['stages']))")
    md('[Python SDK guide](../api.md)')
    md(references(['nmrnet','nmrtrans'] if kind=='inference' else ['opendatalab','openmolspec'],en))
    for i, cell in enumerate(cells):
        cell['id'] = hashlib.sha256(f'{kind}:{en}:{i}'.encode()).hexdigest()[:12]
    return {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
            'language_info': {'name': 'python'}, 'openmolspec_evidence_files': files,
            'openmolspec_model_execution': kind == 'inference'}, 'nbformat': 4, 'nbformat_minor': 5}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for en in (True, False):
        for kind in ('inference', 'training-preflight'):
            path = ROOT / 'documentation/notebooks' / f'sdk-{kind}{"" if en else ".zh"}.ipynb'
            notebook = book(kind, en)
            if args.check:
                actual = json.loads(path.read_text())
                if [''.join(c['source']) for c in actual['cells']] != [''.join(c['source']) for c in notebook['cells']]:
                    raise SystemExit(f'Stale notebook source: {path}')
            else:
                from documentation_notebooks import write_notebook
                write_notebook(path,notebook)
    print('SDK notebook sources verified')


if __name__ == '__main__':
    main()

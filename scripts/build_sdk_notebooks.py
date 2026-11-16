"""Generate real SDK inference and training-preflight notebook sources."""
import argparse
import hashlib
import json
from pathlib import Path

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
    code("import json, os, sys, io, tempfile\nfrom pathlib import Path\nfrom IPython.display import display, SVG\nroot = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'documentation/assets').is_dir())\nfrom openmolspec.dataset import MolecularSpectra, list_datasets\nprint('Registered datasets:', [c['name'] for c in list_datasets()])")
    if kind == 'inference':
        files += ['documentation/assets/sdk-nmr-test-examples.jsonl', 'src/openmolspec/assets/datasets.json',
                  'openmolspec_bench/assignment.py', 'openmolspec_bench/data.py', 'openmolspec_bench/runner.py']
        md('This notebook actually calls the frozen checkpoint. Configure OPENMOLSPEC_MODELS_ROOT and OPENMOLSPEC_NMR_PYTHON using the SDK guide. The three documented NMRSpec records are held-out-role examples, not a new dataset or training set.' if en else
           '本 notebook 实际调用冻结权重。按 SDK 指南配置 OPENMOLSPEC_MODELS_ROOT 和 OPENMOLSPEC_NMR_PYTHON。三个 NMRSpec 记录是已有测试视图的文档示例，不是新的数据集或训练集。')
        code("data = MolecularSpectra.from_jsonl(splits={'test': root / 'documentation/assets/sdk-nmr-test-examples.jsonl'}, name='documented_nmrspec_examples', domain='experimental')\nrows = data['test'].head(3)\nprint(json.dumps(rows[0], indent=2, ensure_ascii=False))\nprint('Split roles:', list(data.get_split()))")
        code("from openmolspec.model import NMRNet\nmodel_root = os.environ.get('OPENMOLSPEC_MODELS_ROOT')\nif not model_root:\n    raise RuntimeError('Set OPENMOLSPEC_MODELS_ROOT to the directory containing nmrnet/; see Python SDK guide')\nmodel = NMRNet.from_pretrained(model_root, nucleus='13C', python=os.environ.get('OPENMOLSPEC_NMR_PYTHON', sys.executable))\nresult = model.predict(rows[0]['smiles'])\nprint(json.dumps(result['records'], indent=2))\nprint('Checkpoint SHA-256:', result['provenance']['checkpoint_sha256'])\nassert result['training_performed'] is False")
        md('Minimum-error matching against unassigned experimental peaks measures peak agreement, not experimental atom-assignment accuracy.' if en else '参考为未指认的实验峰。最小误差匹配衡量峰位置一致性，不是实验原子指认准确率。')
        code("from openmolspec.benchmark import evaluate_nmr\nreference = rows[0]['reference_peaks_ppm']\nprint(json.dumps(evaluate_nmr(result, [reference]), indent=2))\nimport matplotlib.pyplot as plt\nfig, ax = plt.subplots(figsize=(9, 3))\nax.vlines(reference, 0, 1, color='black', label='Experimental reference peaks')\nax.vlines(result['records'][0]['prediction_ppm'], -1, 0, color='#2980b9', label='Frozen NMRNet atom shifts')\nax.invert_xaxis()\nax.set(xlabel='13C chemical shift (ppm)', ylabel='Display sticks (not intensities)', title='Actual SDK inference: first documented NMRSpec molecule')\nax.legend(fontsize=8)\nfig.tight_layout()\nimage = io.StringIO()\nfig.savefig(image, format='svg', metadata={'Date': None})\ndisplay(SVG(image.getvalue()))\nplt.close(fig)")
    else:
        files += [f'documentation/assets/sdk-nmr-{s}-examples.jsonl' for s in ('train', 'val')]
        md('Two real OpenDataLab/WanJuan records from each original train/validation split, selected for readable size and compatible nucleus/formula fields. These are software preflight examples, not a performance benchmark. No training or optimizer update occurs.' if en else
           '分别取 OpenDataLab / WanJuan 原训练集、验证集的两个真实记录，按可读大小及核种/分子式相容性选择。这些是软件检查样本，不是性能基准。不训练模型、不更新优化器。')
        code("data = MolecularSpectra.from_jsonl(splits={s: root / f'documentation/assets/sdk-nmr-{s}-examples.jsonl' for s in ('train', 'val')}, name='documented_opendatalab_train_val', domain='experimental')\nfor role, view in data.get_split().items():\n    print(role, [row['smiles'] for row in view])")
        code("from openmolspec.training import prepare_nmr_training\nfrom openmolspec.model import NMRTransformer\nprepared_tmp = tempfile.TemporaryDirectory(prefix='openmolspec-training-tutorial-')\nprepared = prepare_nmr_training(data['train'], data['val'], Path(prepared_tmp.name) / 'data')\nmodel = NMRTransformer(stage='align')\nplan = model.training_plan(prepared, run_dir=Path(prepared_tmp.name) / 'run', epochs=1, batch_size=2, parameters={'hidden_size': 32, 'heads': 4, 'encoder_layers': 1, 'decoder_layers': 1, 'feedforward_size': 64, 'projection_size': 16, 'max_train_batches': 1, 'max_val_examples': 2})\nprint(json.dumps(plan.validate(), indent=2))\nprint(json.dumps(plan.describe(), indent=2))\nassert not plan.run_dir.exists()")
        md('Calling model.fit(plan) explicitly launches training after installing training dependencies. It is not executed here. The new wrapper has preflight/rejection tests; a complete training/save/reload round trip remains unverified. Pretrained initialization restores model weights, not optimizer/scheduler state.' if en else
           '安装训练依赖后，显式调用 model.fit(plan) 才启动训练；这里未执行。新封装已验证预处理和错误拦截，尚未验证训练、保存、重载的完整闭环。旧权重只用于初始化，不恢复优化器/调度器状态。')
    md('[Python SDK guide](../api.md)')
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
                path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + '\n')
    print('SDK notebook sources verified')


if __name__ == '__main__':
    main()

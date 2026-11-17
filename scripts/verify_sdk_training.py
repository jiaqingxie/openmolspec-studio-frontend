"""Explicitly execute the authorized, tiny SDK training/save/load integration check."""
import argparse
import json
from pathlib import Path
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--stage', choices=['align','generate','all'], default='all')
    args = parser.parse_args()
    if (args.work.exists() and not args.resume) or args.output.exists():
        parser.error('Choose unused work and result paths')
    from openmolspec.dataset import MolecularSpectra
    from openmolspec.model import NMRTransformer
    from openmolspec.training import prepare_nmr_training
    root = Path(__file__).resolve().parents[1]
    args.work.mkdir(parents=True, exist_ok=args.resume)
    started = time.monotonic()
    def heartbeat():
        while True:
            time.sleep(20)
            print(f'SDK training check active: {time.monotonic() - started:.0f}s', flush=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    data = MolecularSpectra.from_jsonl(
        splits={role: root / f'documentation/assets/sdk-nmr-{role}-examples.jsonl' for role in ('train', 'val')},
        name='original_opendatalab_roles_tiny_check', domain='experimental')
    prepared = args.work / 'data'
    if not prepared.exists():
        prepared = prepare_nmr_training(data['train'], data['val'], prepared)
    alignment = NMRTransformer(stage='align', python=args.python, device='cpu')
    plan = alignment.training_plan(prepared, run_dir=args.work / 'align', epochs=1, batch_size=2,
        parameters={'hidden_size':32,'heads':4,'encoder_layers':1,'decoder_layers':1,
                    'feedforward_size':64,'projection_size':16,'max_train_batches':1,'max_val_examples':2})
    report = {'scope':'software integration only, not a performance experiment',
              'authorization':'user requested running the missing learning-value experiments on 2026-11-17',
              'train_records':2,'validation_records':2,'test_records':0,'training_performed':True,
              'steps_per_stage':1,'stages':{}}
    progress = args.work / 'verification-progress.json'
    if progress.exists(): report = json.loads(progress.read_text())
    if (args.work / 'align/result.json').exists():
        result = json.loads((args.work / 'align/result.json').read_text())
        alignment.config['checkpoint'] = result['checkpoint']
        report['stages'].setdefault('align',result)
    else:
        print('Starting one alignment optimizer step', flush=True)
        report['stages']['align'] = alignment.fit(plan)
    progress.write_text(json.dumps(report,indent=2)+'\n')
    validation = data['val'].head(2)
    candidates = [row['smiles'] for row in validation]
    if args.stage in ('align','all') and not report['stages']['align'].get('save_reload_inference_equal'):
        before = alignment.retrieve(validation[0], candidates, top_k=2)
        if not (args.work / 'alignment.json').exists(): alignment.save_config(args.work / 'alignment.json')
        restored = NMRTransformer.from_config(args.work / 'alignment.json')
        assert before == restored.retrieve(validation[0], candidates, top_k=2)
        report['stages']['align']['save_reload_inference_equal'] = True
        progress.write_text(json.dumps(report,indent=2)+'\n')
    if args.stage == 'align':
        print('Alignment train/save/reload/inference passed',flush=True)
        return
    generation = NMRTransformer(stage='generate', python=args.python, device='cpu')
    run_dir = args.work / 'generate'
    if run_dir.exists() and not (run_dir / 'result.json').exists():
        run_dir = args.work / ('generate-retry-'+str(int(time.time())))
    plan = generation.training_plan(prepared, run_dir=run_dir, epochs=1, batch_size=2,
        alignment_checkpoint=alignment.config['checkpoint'],
        parameters={'max_train_batches':1,'max_val_batches':1,'generate_examples':1,'beam_size':1})
    if report['stages'].get('generate'):
        generation.config['checkpoint'] = report['stages']['generate']['checkpoint']
    else:
        print('Starting one generation optimizer step', flush=True)
        report['stages']['generate'] = generation.fit(plan)
        progress.write_text(json.dumps(report,indent=2)+'\n')
    before = generation.predict(validation[:1], beam_size=1)
    if not (args.work / 'generation.json').exists(): generation.save_config(args.work / 'generation.json')
    restored = NMRTransformer.from_config(args.work / 'generation.json')
    assert before == restored.predict(validation[:1], beam_size=1)
    report['stages']['generate']['save_reload_inference_equal'] = True
    report['completed'] = all(stage.get('save_reload_inference_equal') for stage in report['stages'].values())
    report['elapsed_seconds'] = round(time.monotonic()-started, 3)
    progress.write_text(json.dumps(report,indent=2)+'\n')
    if report['completed']: args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()

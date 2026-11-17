"""Package the production benchmark adapters and configurations for readers."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FULL_COMMITS={
    'equiformer_v3':'a7300c58df683dc99cb48027d5bfd4c887486c48',
    'vib2mol':'207a86eb3050012ab5ea20a7e237a5b075d8d057',
    'vib2conf':'70388376639785c2007fc084f15c22f06c1b328a',
}

README='''# OpenMolSpec benchmark training source

This source snapshot contains the benchmark launcher, model adapters, data
preparation and versioned YAML configurations used by the OpenMolSpec manual.

Run these commands from this directory:

```bash
python -m pip install numpy pandas pyarrow scipy pyyaml rdkit lmdb
python -m benchmarks --help
python -m benchmarks check
python -m benchmarks run --config benchmarks/configs/structure2property/equiformer_v3.yaml --dry-run
```

The dry run expands a configuration into its exact command. To train, install
PyTorch/PyG and the selected model's dependencies, prepare the dataset referenced
by `data.root`, then run the same command without `--dry-run`.

Retrieve the pinned model implementations beside their adapters with:

```bash
bash benchmarks/scripts/setup_models.sh
```

Model repositories:

- https://github.com/atomicarchitects/equiformer_v3
- https://github.com/X1nyuLu/vib2mol
- https://github.com/X1nyuLu/vib2conf

Their source revisions are recorded in `benchmarks/models/registry.py`.
The source archive contains the OpenMolSpec adapters; upstream repositories,
model weights and molecular datasets are obtained through their source projects.
`SOURCE_MANIFEST.json` records each bundled file's SHA-256.

Manual: https://jiaqingxie.github.io/openmolspec.github.io/
'''


def build(source,output):
    """Write a deterministic archive and its per-file source manifest."""
    root=source/'benchmarks'
    entries={}
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if not path.is_file() or any(part in ['upstream','__pycache__','.git'] or part.startswith('.') for part in relative.parts):continue
        if path.suffix not in ['.py','.sh','.yaml','.yml']:continue
        entries['benchmarks/'+relative.as_posix()]=path.read_bytes()
    registry=ast.parse((root/'models/registry.py').read_text())
    pins=next(ast.literal_eval(node.value) for node in registry.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='UPSTREAM_PINS' for target in node.targets))
    setup=entries['benchmarks/scripts/setup_models.sh'].decode()
    for name,pin in pins.items():
        assert FULL_COMMITS[name].startswith(pin['commit'])
        setup=setup.replace(' '+pin['commit']+'\n',' '+FULL_COMMITS[name]+'\n')
        pin['source_commit_prefix']=pin['commit'];pin['commit']=FULL_COMMITS[name]
    entries['benchmarks/scripts/setup_models.sh']=setup.encode()
    manifest={'schema_version':1,'snapshot':'2026-11-18','upstream_pins':pins,
        'source_patches':{'benchmarks/scripts/setup_models.sh':'Use verified full commit IDs for Git fetch.'},
        'files':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in entries.items()}}
    entries['README.md']=README.encode()
    entries['SOURCE_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output.mkdir(parents=True,exist_ok=True);archive=output/'openmolspec-benchmark-source.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as stream:
        for name,data in sorted(entries.items()):
            info=zipfile.ZipInfo('openmolspec-benchmarks/'+name,date_time=(2026,11,18,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o755 if name.endswith('.sh') else 0o644)<<16
            stream.writestr(info,data)
    report={**manifest,'archive':archive.name,'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (output/'benchmark-source-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Production project root containing benchmarks/')
    parser.add_argument('--output',type=Path,default=ROOT/'documentation/assets/benchmarks')
    args=parser.parse_args();report=build(args.source,args.output)
    print(json.dumps({key:report[key] for key in ['archive','archive_bytes','archive_sha256']}))


if __name__=='__main__':main()

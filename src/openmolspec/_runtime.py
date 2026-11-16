"""Launch optional author runtimes without importing their dependencies in the client."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def runtime_env():
    return os.environ.copy()


def runtime_command(python, module, arguments):
    # Expose only our packages to the author interpreter. Adding the entire client
    # site-packages to PYTHONPATH would override the author's torch/numpy versions.
    roots = {}
    for package in ('openmolspec', 'openmolspec_bench', 'spec2struct_fork', 'openmolspec_ui'):
        spec = importlib.util.find_spec(package)
        if spec and spec.origin:
            roots[package] = str(Path(spec.origin).resolve().parents[1])
    bootstrap = '''import importlib.abc, importlib.machinery, json, runpy, sys
module, roots = sys.argv[1], json.loads(sys.argv[2])
sys.argv = [module, *sys.argv[3:]]
class PackageFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in roots:
            return importlib.machinery.PathFinder.find_spec(fullname, [roots[fullname]])
sys.meta_path.insert(0, PackageFinder())
runpy.run_module(module, run_name='__main__')
'''
    return [str(python or sys.executable), '-c', bootstrap, module, json.dumps(roots), *map(str, arguments)]


def invoke(request, *, python=None, timeout=600):
    with tempfile.TemporaryDirectory(prefix='openmolspec-api-') as temporary:
        root = Path(temporary)
        source, result = root / 'request.json', root / 'result.json'
        source.write_text(json.dumps(request, allow_nan=False, default=lambda value: value.tolist()))
        command = runtime_command(python, 'openmolspec._worker', [source, result])
        completed = subprocess.run(command, env=runtime_env(), text=True, capture_output=True, timeout=timeout)
        if completed.returncode:
            raise RuntimeError(f'Model runtime exited {completed.returncode}:\n{completed.stderr[-4000:]}')
        if not result.is_file():
            raise RuntimeError('Model runtime produced no result')
        return json.loads(result.read_text())

"""Preserve verified notebook outputs when regenerating unchanged sources."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def _contains(actual,expected):
    if isinstance(expected,dict):return isinstance(actual,dict) and all(key in actual and _contains(actual[key],value) for key,value in expected.items())
    return actual==expected


def write_notebook(path,notebook):
    """Keep an executed notebook only when its source and evidence remain valid.

    Parameters
    ----------
    path : pathlib.Path
        Notebook destination.
    notebook : dict
        Generated notebook source and expected metadata.

    Returns
    -------
    bool
        ``True`` when current verified outputs were retained, otherwise
        ``False`` after writing the new unexecuted source.
    """
    from build_readthedocs import validate_notebook
    if path.is_file():
        actual=json.loads(path.read_text())
        sources=lambda book:[(cell['cell_type'],''.join(cell['source'])) for cell in book['cells']]
        if sources(actual)==sources(notebook) and _contains(actual.get('metadata',{}),notebook.get('metadata',{})):
            try:
                digest=hashlib.sha256((ROOT/'documentation/assets/evaluation_index.json').read_bytes()).hexdigest()
                validate_notebook(path,digest)
                execution=actual.get('metadata',{}).get('openmolspec_execution',{})
                if execution.get('engine')=='jupyter' and bool(execution.get('model_execution_enabled'))==bool(notebook['metadata'].get('openmolspec_model_execution')):
                    return True
            except (ValueError,KeyError):pass
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(notebook,ensure_ascii=False,indent=2)+'\n')
    return False

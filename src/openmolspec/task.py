"""The shared task catalog, grouped for the public SDK."""
from dataclasses import asdict


def list_tasks(*, group=None, include_deferred=False):
    from openmolspec_bench.catalog import TASKS
    result = []
    for task in TASKS:
        category = ('deferred' if not task.enabled else 'nmr' if task.id.startswith('nmr.') else
                    'ms' if task.id.startswith('ms.') else 'multimodal' if task.id.endswith(('.hc', '_hc')) else 'vibrational')
        if (task.enabled or include_deferred) and (group is None or category == group):
            result.append({**asdict(task), 'group': category})
    return result

"""The shared task catalog, grouped for the public SDK."""
from dataclasses import asdict


def list_tasks(*, group=None, include_deferred=False):
    """List the spectroscopy tasks and their model/evaluation interfaces.

    Parameters
    ----------
    group : {'nmr', 'ms', 'vibrational', 'multimodal', 'deferred'} or None
        Select one task family. ``None`` returns all enabled families.
    include_deferred : bool, default False
        Include the additional task definitions outside the active suite.

    Returns
    -------
    list of dict
        Task ID, title, spectral channels, domain, backend, metrics and group.

    Examples
    --------
    >>> nmr = list_tasks(group='nmr')
    >>> all(task['id'].startswith('nmr.') for task in nmr)
    True
    """
    from openmolspec_bench.catalog import TASKS, spectroscopy_group
    result = []
    for task in TASKS:
        category = spectroscopy_group(task)
        if (task.enabled or include_deferred) and (group is None or category == group):
            result.append({**asdict(task), 'group': category})
    return result

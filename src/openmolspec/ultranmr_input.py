"""Prepare the inputs to UltraNMR's formula-conditioned NMRGym decoder."""

import math
import re


def decoder_inputs(h_shifts, c_shifts, formula, atom_types):
    """Encode a measured H/C peak list and independently supplied neutral formula.

    Pass the installed UltraNMR release's DEFAULT_ATOM_TYPES to keep its element
    vocabulary order. Return numeric lists suitable for conversion to tensors.
    Repeated shifts retain their original counts and ordering.
    """
    if not isinstance(formula, str) or not re.fullmatch(
        r"(?:[A-Z][a-z]?(?:[1-9][0-9]*)?)+", formula
    ):
        raise ValueError("Supply an explicit neutral elemental formula")
    counts = dict.fromkeys(atom_types, 0)
    for symbol, count in re.findall(r"([A-Z][a-z]?)([1-9][0-9]*)?", formula):
        if symbol not in counts:
            raise ValueError("Element outside the checkpoint vocabulary: " + symbol)
        counts[symbol] += int(count or 1)
    h, c = list(h_shifts), list(c_shifts)
    if (
        not h
        or not c
        or any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            for v in h + c
        )
    ):
        raise ValueError("Supply nonempty, finite H and C shift lists")
    return dict(
        raw_shifts=h + c,
        counts=[1.0] * len(h) + [0.0] * len(c),
        types=[0] * len(h) + [1] * len(c),
        formula_counts=list(counts.values()),
    )

"""Rank proposed structures, optionally generating alternatives from the same measured NMR."""

import argparse
import json
from pathlib import Path
from openmolspec.model import NMRTransformer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--request",
        type=Path,
        required=True,
        help="JSON object containing query and candidates",
    )
    p.add_argument("--align", type=Path, required=True)
    p.add_argument("--generate", type=Path, help="Generation checkpoint")
    p.add_argument("--reject-shortlist", action="store_true")
    p.add_argument("--formula", help="Independently supplied molecular formula")
    p.add_argument("--python", help="Python for the checkpoint runtime")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.reject_shortlist and not (a.formula and a.generate):
        p.error("Generating alternatives requires --formula and --generate")
    request = json.loads(a.request.read_text())
    query = {
        k: v
        for k, v in request["query"].items()
        if k in ("h_nmr", "c_nmr", "modality_mask")
    }
    align = NMRTransformer.from_pretrained(a.align, stage="align", python=a.python)
    result = {"query": query, "retrieval": align.retrieve(query, request["candidates"])}
    if a.reject_shortlist:
        generator = NMRTransformer.from_pretrained(
            a.generate, stage="generate", python=a.python
        )
        result["given_formula"] = a.formula
        result["generation"] = generator.predict({**query, "formula": a.formula})
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()

"""Compute solution shifts using the validation-selected checkpoint."""

import json
from pathlib import Path
import sys

from openmolspec.solution_shifts import SolutionShiftPredictor
from openmolspec_bench.data import sha256


def predict(payload):
    model = SolutionShiftPredictor(Path(payload["model_dir"]))
    if model.nucleus != payload.get("nucleus", "31P"):
        raise ValueError("Configured checkpoint nucleus differs from request")
    record = model.predict(payload["smiles"], payload.get("solvent"))
    return {
        "task": "nmr.forward." + model.nucleus,
        "model": model.config.get("engine", "lightgbm"),
        "checkpoint_sha256": model.config.get("gnn_sha256")
        or model.config.get("booster_sha256") or sha256(Path(payload["model_dir"]) / "model.json"),
        "records": [record],
        "unit": "ppm",
    }


if __name__ == "__main__":
    print("OMS_RESULT_V1:" + json.dumps(predict(json.load(sys.stdin)), allow_nan=False))

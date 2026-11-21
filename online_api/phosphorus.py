"""Compute phosphorus shifts using the validation-selected checkpoint."""

import json
from pathlib import Path
import sys

from openmolspec.solution_shifts import SolutionShiftPredictor


def predict(payload):
    model = SolutionShiftPredictor(Path(payload["model_dir"]))
    if model.nucleus != "31P":
        raise ValueError("Configured checkpoint must predict phosphorus")
    record = model.predict(payload["smiles"], payload.get("solvent"))
    return {
        "task": "nmr.forward.31P",
        "model": model.config.get("engine", "lightgbm"),
        "checkpoint_sha256": model.config.get("gnn_sha256")
        or model.config["booster_sha256"],
        "records": [record],
        "unit": "ppm",
    }


if __name__ == "__main__":
    print("OMS_RESULT_V1:" + json.dumps(predict(json.load(sys.stdin)), allow_nan=False))

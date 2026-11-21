"""Run the released experimental H/C peak predictor in its model interpreter."""

import json
from pathlib import Path
import sys

from openmolspec.assigned_shifts import PeakSpectrumPredictor
from openmolspec_bench.data import sha256


def predict(payload):
    directory = Path(payload["model_dir"]).resolve()
    predictor = PeakSpectrumPredictor(directory)
    if predictor.nucleus != payload["nucleus"]:
        raise ValueError("Nucleus differs from selected peak predictor")
    record = predictor.predict(payload["smiles"], payload.get("solvent"))
    record["atom_indices"] = [p["atom_indices"] for p in record["peaks"]]
    if not record["peaks"]:
        raise ValueError("This molecule has no site of the requested nucleus")
    return dict(
        task="nmr.forward." + predictor.nucleus,
        model="peak_spectrum",
        checkpoint_sha256=sha256(directory / "model.json"),
        records=[record],
    )


if __name__ == "__main__":
    print("OMS_RESULT_V1:" + json.dumps(predict(json.load(sys.stdin)), allow_nan=False))

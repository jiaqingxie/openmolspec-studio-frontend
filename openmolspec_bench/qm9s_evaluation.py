"""Evaluate structure-disjoint QM9S IR/Raman predictions on their exact source geometries."""

import json
from pathlib import Path
import random

import numpy as np
from .data import sha256
from .vibrational_profile import checkpoint_hashes, mode_spectra, transform


def evaluate(runner, directory, fresh=False):
    from .runner import require

    manifest = require(Path(directory) / "model.json")
    config = json.loads(manifest.read_text())
    data = require(manifest.parent / "test.npz")
    if sha256(data) != config["test_npz_sha256"]:
        raise ValueError("QM9S evaluation archive checksum mismatch")
    with np.load(data, allow_pickle=False) as a:
        grid = a["grid"]
        ids = list(range(len(a["keys"])))
        if runner.args.sampling == "reservoir":
            random.Random(runner.args.seed).shuffle(ids)
        ids = ids[: runner.args.limit]
        if len(set(a["keys"].tolist())) != len(a["keys"]):
            raise ValueError("Duplicate QM9S held-out connectivity")
        raw = {ch: a["raw_" + ch][ids] for ch in ("ir", "raman")}
        mode_inputs = {
            ch: a["mode_" + ch][ids]
            for ch in raw
            if config.get("sources", {}).get(ch) == "modes"
        }
        if fresh:
            from openmolspec_ui.inference import OpenMolSpecService
            from openmolspec_ui.config import discover_assets
            from openmolspec_ui.chemistry import molecule_from_xyz
            from rdkit import Chem

            service = OpenMolSpecService(
                discover_assets(runner.args.portable_root), device=runner.args.device
            )
            if checkpoint_hashes(service.assets) != config["checkpoints"]:
                raise ValueError("QM9S model checkpoint mismatch")
            xyz, ptr = a["geometry"], a["ptr"]
            for j, i in enumerate(ids):
                rows = xyz[ptr[i] : ptr[i + 1]]
                text = [str(len(rows)), "QM9S native optimized geometry"]
                for z, x, y, w in rows:
                    text.append(
                        f"{Chem.GetPeriodicTable().GetElementSymbol(int(z))} {x:.9f} {y:.9f} {w:.9f}"
                    )
                result = service.predict_spectra(
                    molecule_from_xyz("\n".join(text) + "\n"),
                    include_nmr=False,
                    include_qm9s_modes=bool(mode_inputs),
                )
                if mode_inputs:
                    discrete = mode_spectra(result, grid)
                    for ch in mode_inputs:
                        mode_inputs[ch][j] = discrete[ch]
                for ch in raw:
                    raw[ch][j] = np.interp(grid, result["wavenumber"], result[ch])
        metrics, baseline, example = {}, {}, {}
        for ch, values in raw.items():
            observed = a["reference_" + ch][ids]
            for output, settings, inputs in (
                (baseline, [1.0, 0.0], values),
                (metrics, config["profile"][ch], mode_inputs.get(ch, values)),
            ):
                pred = transform(inputs, *settings, grid)
                product = np.sum(pred * observed, axis=1)
                norms = np.linalg.norm(pred, axis=1) * np.linalg.norm(observed, axis=1)
                output[ch + "_cosine_similarity"] = float(
                    (product / np.maximum(norms, 1e-18)).mean()
                )
                output[ch + "_mae"] = float(abs(pred - observed).mean())
            example[ch] = dict(
                prediction=pred[0].tolist(), reference=observed[0].tolist()
            )
        return dict(
            dataset=runner.artifact(data),
            domain="computed",
            profile=runner.artifact(manifest),
            inference_mode=(
                "fresh_from_native_coordinates"
                if fresh
                else "score_verified_frozen_predictions"
            ),
            sample_ids=a["keys"][ids].tolist(),
            reference=config["reference"],
            metrics=metrics,
            baseline_metrics=baseline,
            fresh_inference=fresh,
            example=dict(
                connectivity=str(a["keys"][ids[0]]),
                wavenumber_cm1=grid.tolist(),
                channels=example,
            ),
        )

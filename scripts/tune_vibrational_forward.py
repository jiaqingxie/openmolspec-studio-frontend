"""Tune IR/Raman frequency and width on QM9S validation geometries, then score held-out structures."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import pickle
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openmolspec_bench.vibrational_profile import (
    checkpoint_hashes,
    mode_spectra,
    transform as calibrate,
)
from openmolspec_bench.data import sha256
from openmolspec_ui.chemistry import molecule_from_xyz
from openmolspec_ui.config import discover_assets
from openmolspec_ui.inference import OpenMolSpecService


def score(pred, ref):
    cosine = np.sum(pred * ref, axis=1) / np.maximum(
        np.linalg.norm(pred, axis=1) * np.linalg.norm(ref, axis=1), 1e-18
    )
    return cosine, np.mean(abs(pred - ref), axis=1)


def select_profile(sources, reference, grid, coarse):
    """Choose the spectrum representation, frequency correction and resolution on validation."""
    candidates = {}
    for source, values in sources.items():

        def cosine(scale, width):
            return float(
                score(calibrate(values, scale, width, grid), reference)[0].mean()
            )

        scores = {(scale, width): cosine(scale, width) for scale, width in coarse}
        scale, width = max(scores, key=scores.get)
        for ds, dw in itertools.product(
            (-0.005, -0.0025, 0.0, 0.0025, 0.005), (-3.0, 0.0, 3.0)
        ):
            candidate = (scale + ds, max(0.0, width + dw))
            if candidate not in scores:
                scores[candidate] = cosine(*candidate)
        candidates.update({(source, *k): v for k, v in scores.items()})
    selected = max(candidates, key=candidates.get)
    return selected, candidates


def main():
    import torch
    from rdkit import Chem

    p = argparse.ArgumentParser(description=__doc__)
    for n in ("input", "cache", "portable", "report"):
        p.add_argument("--" + n, type=Path, required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    with a.input.open("rb") as f:
        records = pickle.load(f)
    grid = np.linspace(500.0, 4000.0, 997)
    service = OpenMolSpecService(discover_assets(a.portable.resolve()), device="cpu")
    stored = {}
    if a.cache.exists():
        with a.cache.open("rb") as f:
            while True:
                try:
                    k, pred = pickle.load(f)
                    stored[k] = pred
                except EOFError:
                    break
    for i, row in enumerate(records):
        if "mode_ir" in stored.get(row["key"], {}):
            continue
        xyz = [str(len(row["geom"])), "QM9S optimized coordinates"]
        for z, x, y, w in row["geom"]:
            xyz.append(
                f"{Chem.GetPeriodicTable().GetElementSymbol(int(z))} {x:.9f} {y:.9f} {w:.9f}"
            )
        m = molecule_from_xyz("\n".join(xyz) + "\n")
        np.testing.assert_allclose(
            m.mol.GetConformer().GetPositions(),
            np.array(row["geom"])[:, 1:],
            atol=1e-7,
            rtol=0,
        )
        result = service.predict_spectra(m, include_nmr=False, include_qm9s_modes=True)
        current = {
            c: np.interp(grid, result["wavenumber"], result[c]).astype("f")
            for c in ("ir", "raman")
        }
        current.update(
            {
                "mode_" + ch: v.astype("f")
                for ch, v in mode_spectra(result, grid).items()
            }
        )
        with a.cache.open("ab") as f:
            pickle.dump((row["key"], current), f)
        stored[row["key"]] = current
        if i % 25 == 0:
            print("predicted", i, flush=True)
    val = np.array(
        [
            int(
                hashlib.sha256(("vibration-val-v1:" + r["key"]).encode()).hexdigest()[
                    :8
                ],
                16,
            )
            % 2
            == 0
            for r in records
        ]
    )
    if len(set(r["key"] for r in records)) != len(records):
        raise ValueError("Duplicate vibrational identity")
    report = dict(
        reference="QM9S optimized coordinates and same-record Hessian, dipole and polarizability derivatives on OpenMolSpec-reserved connectivities; harmonic factor 0.965, Lorentzian HWHM 10 cm^-1, Raman 532 nm and 298 K",
        validation_identities=int(val.sum()),
        test_identities=int((~val).sum()),
        reference_sha256=sha256(a.input),
        predictions_sha256=sha256(a.cache),
        checkpoints=checkpoint_hashes(service.assets),
        channels={},
    )
    settings = list(
        itertools.product(
            [0.94, 0.955, 0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.035, 1.05, 1.065],
            [0, 5, 10, 15, 25, 40, 60, 80],
        )
    )
    for ch in ("ir", "raman"):
        ref = np.array([np.interp(grid, np.arange(500, 4001), r[ch]) for r in records])
        ref /= np.maximum(ref.max(axis=1, keepdims=True), 1e-15)
        raw = np.array([stored[r["key"]][ch] for r in records])
        sources = {
            "openspec": raw,
            "modes": np.array([stored[r["key"]]["mode_" + ch] for r in records]),
        }
        best, candidates = select_profile(
            {k: v[val] for k, v in sources.items()}, ref[val], grid, settings
        )
        source, scale, width = best
        base = calibrate(raw[~val], 1.0, 0.0, grid)
        pred = calibrate(sources[source][~val], scale, width, grid)
        c0, m0 = score(base, ref[~val])
        c1, m1 = score(pred, ref[~val])
        delta = c1 - c0
        rng = np.random.default_rng(2607)
        report["channels"][ch] = dict(
            selected=[scale, width],
            selected_source=source,
            representation_comparison={
                s: max(v for setting, v in candidates.items() if setting[0] == s)
                for s in sources
            },
            grid_size=len(candidates),
            validation_cosine=candidates[best],
            baseline_validation_cosine=candidates[("openspec", 1.0, 0.0)],
            baseline_test_cosine=float(c0.mean()),
            selected_test_cosine=float(c1.mean()),
            baseline_test_mae=float(m0.mean()),
            selected_test_mae=float(m1.mean()),
            cosine_difference_ci95=np.percentile(
                rng.choice(delta, (2000, len(delta))).mean(axis=1), [2.5, 97.5]
            ).tolist(),
        )
    for ch, item in report["channels"].items():
        item["reference_profile_source"] = (
            item["selected_source"]
            if item["cosine_difference_ci95"][0] > 0
            else "openspec"
        )
        item["reference_profile_setting"] = (
            item["selected"] if item["cosine_difference_ci95"][0] > 0 else [1.0, 0.0]
        )
    bundle = a.cache.parent / "qm9s-evaluation"
    bundle.mkdir(exist_ok=True)
    heldout = [row for row, keep in zip(records, ~val) if keep]
    arrays = dict(
        grid=grid,
        keys=np.array([r["key"] for r in heldout]),
        geometry=np.concatenate([r["geom"] for r in heldout]),
        ptr=np.cumsum([0, *[len(r["geom"]) for r in heldout]]),
    )
    for ch in ("ir", "raman"):
        ref = np.array([np.interp(grid, np.arange(500, 4001), r[ch]) for r in heldout])
        arrays["reference_" + ch] = ref / np.maximum(
            ref.max(axis=1, keepdims=True), 1e-15
        )
        arrays["raw_" + ch] = np.array([stored[r["key"]][ch] for r in heldout])
        arrays["mode_" + ch] = np.array(
            [stored[r["key"]]["mode_" + ch] for r in heldout]
        )
    with (bundle / "test.partial").open("wb") as f:
        np.savez_compressed(f, **arrays)
    (bundle / "test.partial").replace(bundle / "test.npz")
    config = dict(
        reference=report["reference"],
        checkpoints=report["checkpoints"],
        sources={
            ch: d["reference_profile_source"] for ch, d in report["channels"].items()
        },
        profile={
            ch: d["reference_profile_setting"] for ch, d in report["channels"].items()
        },
        test_npz_sha256=sha256(bundle / "test.npz"),
    )
    (bundle / "model.json").write_text(json.dumps(config, indent=2) + "\n")
    a.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(report, flush=True)


if __name__ == "__main__":
    main()

"""Match observed product ions to atom-indexed fragments proposed by a fixed MechFrag-MS policy."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from .data import sha256
from .ms import select_ms_records


def policy_manifest(study):
    """Resolve an explicit policy lock or the preferred manifest in a run directory."""
    location = Path(study).resolve()
    if not location.is_dir():
        return location
    latest = location / "locked_balanced_context.json"
    return latest if latest.is_file() else location / "locked_policy.json"


class FragmentAnnotator:
    def __init__(self, source, study):
        source, study = Path(source).resolve(), Path(study).resolve()
        sys.path[:0] = [str(source), str(source / "scripts")]
        from evaluate_policy_blend import load_native

        lock = policy_manifest(study)
        locked = json.loads(lock.read_text())
        self.lock_name = lock.name
        self.variant = locked["variant"]
        folder = lock.parent / self.variant
        if (
            "config_sha256" in locked
            and sha256(folder / "config.json") != locked["config_sha256"]
        ):
            raise ValueError("Configuration differs from the locked MechFrag model")
        self.digest = sha256(folder / "best.pt")
        if self.digest != locked["sha256"]:
            raise ValueError("Checkpoint differs from the locked MechFrag policy")
        self.network = load_native(folder, "cpu")

    def annotate(self, row, ppm=10.0):
        import torch
        from mechfrag import chem
        from mechfrag.preprocess import convert_sample
        from mechfrag.dataset import collate
        from mechfrag.policy_spectrum import policy_tree, fragment_ions

        s = convert_sample(
            {
                "spec_id": row.get("spec_id", "query"),
                "smiles": row["smiles"],
                "adduct": row["adduct"],
            },
            structure_only=True,
        )
        if s is None or row["instrument"] not in chem.INSTRUMENT_TO_IDX:
            raise ValueError("Unsupported molecule, adduct, or instrument")
        ce = float(row["collision_energy"])
        observed = np.asarray(row["mz"], dtype=float)
        if (
            observed.ndim != 1
            or not len(observed)
            or not np.isfinite(observed).all()
            or min(observed) <= 0
            or not np.isfinite(ce)
            or ce < 0
            or not 0 < ppm <= 100
        ):
            raise ValueError("Invalid m/z, collision energy, or ppm tolerance")
        s.update(
            ce=ce,
            instrument_idx=chem.INSTRUMENT_TO_IDX[row["instrument"]],
            bond_bde=chem.bde_feature(s["elem_idx"], s["bond_index"], s["bond_feat"]),
        )
        net = self.network
        with torch.inference_mode():
            batch = collate([s])
            h, _ = net.model.encode(batch)
            tree = policy_tree(
                net.model,
                h,
                batch,
                net.width,
                net.depth,
                net.branches,
                paths_per_fragment=net.paths_per_fragment,
                propagate_routes=net.propagate_routes,
            )
            masses, weights = fragment_ions(net.model, h, batch, tree)
        # Only intact fragment hypotheses have a fully specified structural atom mask.
        masses = masses[..., 0].numpy()
        weights = weights[..., 0].numpy()
        atoms = np.split(tree[0].numpy(), np.cumsum(tree[1].numpy())[:-1])
        hits = []
        for mz in observed:
            error = 1e6 * (masses - mz) / mz
            candidates = np.flatnonzero((np.abs(error) <= ppm) & (weights > 0))
            match = None
            if len(candidates):
                idx = candidates[np.argmax(weights.flat[candidates])]
                f, i, j = np.unravel_index(idx, masses.shape)
                match = dict(
                    atom_indices=atoms[f].tolist(),
                    calculated_mz=float(masses[f, i, j]),
                    ppm_error=float(error[f, i, j]),
                    h_shift=int(i + chem.H_SHIFT_MIN),
                    ion_mode=("retained_adduct", "charge_only")[j],
                    candidate_ions=int(len(candidates)),
                )
            hits.append(dict(observed_mz=float(mz), match=match))
        return dict(
            smiles=row["smiles"],
            atom_index_basis="zero-based RDKit atom order of the input SMILES",
            checkpoint_sha256=self.digest,
            peaks=hits,
            matched=sum(h["match"] is not None for h in hits),
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "study", "csv", "metadata", "magma", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    import torch

    torch.set_num_threads(1)
    baseline = {r["spec_id"]: r for r in json.loads(a.magma.read_text())["records"]}
    rows, _ = select_ms_records(a.csv, a.metadata, len(baseline), max_heavy_atoms=24)
    if {r["spec_id"] for r in rows} != set(baseline):
        raise ValueError("MAGMa panel mismatch")
    annotator = FragmentAnnotator(a.source, a.study)
    records = []
    skipped = []
    for row in rows:
        if not row["instrument"] or not row["collision_energy"]:
            skipped.append(
                dict(spec_id=row["spec_id"], reason="missing acquisition conditions")
            )
            continue
        row["mz"] = [peak[0] for peak in row["reference_peaks"]]
        pred = annotator.annotate(row)
        old = baseline[row["spec_id"]]
        if len(pred["peaks"]) != old["n_peaks"]:
            raise ValueError("Measured peak counts differ")
        records.append(
            dict(spec_id=row["spec_id"], magma_matched=old["n_matched"], **pred)
        )
    n = sum(len(r["peaks"]) for r in records)
    out = dict(
        complete=True,
        records=records,
        skipped=skipped,
        ppm=10,
        checkpoint_sha256=annotator.digest,
        variant=annotator.variant,
        lock=annotator.lock_name,
        peaks=n,
        matched_fraction=sum(r["matched"] for r in records) / n,
        magma_matched_fraction_same_peaks=sum(r["magma_matched"] for r in records) / n,
        interpretation="Measured peak m/z coverage; atom masks are model hypotheses.",
    )
    a.output.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()

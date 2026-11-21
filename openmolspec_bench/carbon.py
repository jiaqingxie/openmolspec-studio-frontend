"""Predict one solution 13C peak per graph-symmetry class with five NMRNet++ folds."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from .data import sha256


def group_carbon_shifts(mol, atom_shifts):
    from rdkit import Chem

    indices = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6]
    values = np.asarray(atom_shifts, dtype=float)
    if not indices or values.shape != (len(indices),) or not np.isfinite(values).all():
        raise ValueError("Expected one finite prediction for every carbon in the input")
    ranks = Chem.CanonicalRankAtoms(mol, breakTies=False, includeChirality=True)
    groups = {}
    for pos, atom_index in enumerate(indices):
        groups.setdefault(ranks[atom_index], []).append(pos)
    peaks = [
        dict(
            atom_indices=[indices[p] for p in positions],
            shift_ppm=float(values[positions].mean()),
        )
        for positions in groups.values()
    ]
    return sorted(peaks, key=lambda peak: peak["shift_ppm"])


def predict(request):
    from rdkit import Chem
    from importlib.resources import files
    from .assignment import predict_atoms

    profile = files("openmolspec").joinpath("assets/carbon-folds.json")
    config = json.loads(profile.read_text())
    structures = request["smiles"]
    models = Path(request["models_root"])
    predictions, traces = [], []
    with TemporaryDirectory(prefix="openmolspec-carbon-") as work:
        for fold, digest in enumerate(config["checkpoint_sha256"]):
            values, trace = predict_atoms(
                structures,
                "C",
                models,
                Path(work) / str(fold),
                backend="nmrnetpp",
                fold=fold,
            )
            if (
                trace["checkpoint_sha256"] != digest
                or trace["scaler_sha256"] != config["scaler_sha256"]
                or trace["dictionary_sha256"] != config["dictionary_sha256"]
            ):
                raise ValueError(
                    "NMRNet++ assets disagree with the selected carbon ensemble"
                )
            predictions.append(values)
            traces.append(
                dict(
                    fold=fold,
                    checkpoint_sha256=digest,
                    state_dict_audit=trace["state_dict_audit"],
                )
            )
    records = []
    for i, smiles in enumerate(structures):
        averaged = np.mean(np.stack([v[i] for v in predictions]), axis=0)
        peaks = group_carbon_shifts(Chem.MolFromSmiles(smiles), averaged)
        records.append(
            dict(
                smiles=smiles,
                nucleus="13C",
                prediction_ppm=[p["shift_ppm"] for p in peaks],
                atom_indices=[p["atom_indices"] for p in peaks],
                peaks=peaks,
                unit="ppm",
            )
        )
    return dict(
        model="NMRNet++",
        task="nmr.forward.13C",
        checkpoint_sha256=sha256(profile),
        records=records,
        unit="ppm",
        training_performed=False,
        inference_mode="direct_frozen_checkpoint",
        provenance=dict(
            folds=traces,
            scaler_sha256=config["scaler_sha256"],
            dictionary_sha256=config["dictionary_sha256"],
            geometry="RDKit AddHs, seed 42, MMFF",
            atom_index_basis="zero-based input SMILES",
        ),
    )

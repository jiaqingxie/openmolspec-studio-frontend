"""Score solution chemical shifts against held-out experimental records."""

from collections import Counter, defaultdict
import gzip
import json
import pickle
import random

import numpy as np

from .data import readonly_lmdb
from .runner import MissingAsset


def historical_rows(path, nucleus):
    """Read the original single-labelled-atom pool unmodified."""
    env = readonly_lmdb(path)
    try:
        with env.begin() as txn:
            for key, value in txn.cursor():
                row = pickle.loads(value)
                mask = np.asarray(row["atoms_target_mask"], dtype=bool)
                atoms = np.asarray(row["atoms"])
                symbol = nucleus[-1]
                if (
                    mask.sum() != 1
                    or atoms[mask].item() != symbol
                    or (atoms == symbol).sum() != 1
                ):
                    raise ValueError("Historical pool requires one target atom")
                yield dict(
                    record_id=key.decode(),
                    smiles=row["smiles"],
                    solvent=None,
                    source="legacy",
                    reference_ppm=float(np.asarray(row["atoms_target"])[mask].item()),
                )
    finally:
        env.close()


def evaluate(runner, nucleus):
    from rdkit import Chem
    from openmolspec.solution_shifts import SolutionShiftPredictor, analyte

    args = runner.args
    model_root = args.solution_shift_root or args.workspace / "runs/solution-shifts-v1"
    model_dir = model_root / nucleus
    selected_dir = args.workspace / "runs/solution-shifts-selected" / nucleus
    if args.solution_shift_root is None and (selected_dir / "model.json").is_file():
        model_dir = selected_dir
    checkpoint = runner.artifact(model_dir / "model.json")
    model = SolutionShiftPredictor(model_dir)
    if model.nucleus != nucleus:
        raise ValueError("Selected model is for a different nucleus")
    split_file = runner.artifact(model_dir / "identity-splits.tsv.gz")
    if split_file["sha256"] != model.config["identity_splits_sha256"]:
        raise ValueError("Training split manifest digest mismatch")
    historical = args.solution_reference == "historical-pool"
    role = "pool" if historical else "test"
    with gzip.open(split_file["path"], "rt") as stream:
        reserved = {
            key for key, group in (line.split() for line in stream) if group == role
        }

    if historical:
        path = args.models_root / "nmrnetpp" / f"pool_{nucleus[-1]}" / "valid.lmdb"
        dataset = runner.artifact(path)
        if dataset["sha256"] != model.config["reserved_pool_sha256"]:
            raise ValueError("Historical pool digest mismatch")
        rows = list(historical_rows(path, nucleus))
    else:
        path = model_dir / "test-references.jsonl.gz"
        dataset = runner.artifact(path)
        if dataset["sha256"] != model.config["test_references_sha256"]:
            raise ValueError("Experimental test reference digest mismatch")
        with gzip.open(path, "rt") as stream:
            rows = [
                dict(json.loads(line), record_id=str(i))
                for i, line in enumerate(stream)
            ]
    if args.sampling == "reservoir":
        random.Random(args.seed).shuffle(rows)
    predictions, skipped, molecule_errors = [], Counter(), defaultdict(list)
    for row in rows:
        try:
            mol, _ = analyte(row["smiles"], nucleus)
        except ValueError as error:
            if not historical:
                raise
            skipped[str(error)] += 1
            continue
        identity = Chem.MolToInchiKey(mol).split("-")[0]
        if historical and len(identity) != 14:
            skipped["missing_connectivity_key"] += 1
            continue
        if identity not in reserved or identity != row.get("connectivity", identity):
            raise ValueError(
                f"Identity {identity} is not the expected held-out structure"
            )
        (site,) = model.predict(row["smiles"], row["solvent"])["environments"]
        prediction = site["prediction_ppm"]
        reference = row["reference_ppm"]
        if not np.isfinite(reference) or not np.isfinite(prediction):
            raise ValueError("Nonfinite experimental shift")
        molecule_errors[identity].append(abs(prediction - reference))
        predictions.append(dict(row, connectivity=identity, prediction_ppm=prediction))
        if len(predictions) == args.limit:
            break
    if not predictions:
        raise MissingAsset("No eligible records in the experimental reference set")
    error = np.array([r["prediction_ppm"] - r["reference_ppm"] for r in predictions])
    return dict(
        metrics=dict(
            mae_ppm=float(abs(error).mean()),
            rmse_ppm=float(np.sqrt(np.mean(error**2))),
            molecule_macro_mae_ppm=float(
                np.mean([np.mean(x) for x in molecule_errors.values()])
            ),
            median_absolute_ppm=float(np.median(abs(error))),
            p90_absolute_ppm=float(np.percentile(abs(error), 90)),
            examples=len(predictions),
        ),
        dataset_name=f"experimental_solution_{nucleus}_{role}",
        dataset=dataset,
        checkpoint=checkpoint,
        identity_splits=split_file,
        selection=dict(
            sampling=args.sampling,
            seed=args.seed,
            pool_size=len(rows),
            distinct_selected_identities=len(molecule_errors),
            skipped=dict(skipped),
        ),
        sample_ids=[r["record_id"] for r in predictions],
        predictions=predictions,
        model_domain="experimental_solution",
        evaluation_domain="experimental_solution",
        inference_mode="fresh_model_predictions",
        split_leakage_audit="all_selected_connectivities_reserved_before_fit",
    )

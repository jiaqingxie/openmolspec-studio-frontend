"""Fit a solution-shift model using training identities only; select on validation and score held-out molecules."""

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import lightgbm as lgb
import numpy as np
from openmolspec.solution_shifts import NUCLEI, feature_matrix, root_estimate
from openmolspec_bench.data import sha256

ORDER = {"": 0, "train": 1, "val": 2, "test": 3, "pool": 4}


def records(path):
    with gzip.open(path, "rt") as stream:
        for line in stream:
            yield json.loads(line)


def partition(path):
    priority = defaultdict(int)
    for key, _, _, _, obs in records(path):
        priority[key] = max(priority[key], max(ORDER[role] for _, role, _, _, _ in obs))
    roles = {}
    for key, level in priority.items():
        if level:
            roles[key] = next(role for role, v in ORDER.items() if v == level)
        else:
            bucket = (
                int(
                    hashlib.sha256(("solution-shift-v1:" + key).encode()).hexdigest()[
                        :12
                    ],
                    16,
                )
                % 100
            )
            roles[key] = "train" if bucket < 80 else "val" if bucket < 90 else "test"
    return roles


def write_test_references(features, roles, destination):
    """Export measured single-environment test records in feature preparation order."""
    solvents = (
        None,
        "CDCl3",
        "DMSO-d6",
        "D2O",
        "CD3OD",
        "C6D6",
        "acetone-d6",
        "CD3CN",
        "THF-d8",
        "CD2Cl2",
        "toluene-d8",
        "other",
    )
    with gzip.GzipFile(filename=str(destination), mode="wb", mtime=0) as stream:
        for key, smiles, _, sites, observations in records(features):
            if roles[key] != "test" or len(sites) != 1:
                continue
            seen = set()
            for source, _, solvent, peaks, _ in observations:
                signature = (source, solvent, tuple(peaks))
                if len(peaks) == 1 and signature not in seen:
                    row = dict(
                        connectivity=key,
                        smiles=smiles,
                        source=source,
                        solvent=solvents[solvent],
                        reference_ppm=peaks[0],
                    )
                    stream.write(
                        (json.dumps(row, separators=(",", ":")) + "\n").encode()
                    )
                    seen.add(signature)
    return sha256(destination)


def metrics(errors, keys):
    if not len(errors):
        return {"observations": 0, "identities": 0}
    x = np.asarray(errors, dtype=float)
    groups = defaultdict(list)
    for key, e in zip(keys, np.abs(x)):
        groups[key].append(e)
    return {
        "observations": len(x),
        "identities": len(groups),
        "mae_ppm": float(np.abs(x).mean()),
        "molecule_macro_mae_ppm": float(np.mean([np.mean(v) for v in groups.values()])),
        "median_absolute_ppm": float(np.median(np.abs(x))),
        "p90_absolute_ppm": float(np.percentile(np.abs(x), 90)),
        "rmse_ppm": float(np.sqrt(np.mean(x * x))),
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--features", required=True, type=Path)
    cli.add_argument("--nucleus", required=True, choices=NUCLEI)
    cli.add_argument("--output", required=True, type=Path)
    cli.add_argument("--report", required=True, type=Path)
    cli.add_argument(
        "--old-diagnostic",
        type=Path,
        help="Directory containing the original frozen 32-row prediction fold and manifest",
    )
    cli.add_argument("--max-rounds", type=int, default=1000)
    cli.add_argument("--num-leaves", type=int, default=63)
    cli.add_argument("--min-leaf", type=int, default=15)
    cli.add_argument("--threads", type=int, default=2)
    cli.add_argument(
        "--fixed-rounds", type=int, help="Reproduce a previously selected tree count"
    )
    cli.add_argument(
        "--environment-weight",
        type=float,
        choices=(0, 0.25, 0.5, 0.75, 1),
        help="Reproduce a previously selected local-environment weight",
    )
    args = cli.parse_args()
    if args.fixed_rounds is not None and args.fixed_rounds < 1:
        cli.error("--fixed-rounds must be positive")
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    inputs = json.loads(args.features.with_suffix(".manifest.json").read_text())
    if not any(
        Path(path).name == f"nmrexp_{args.nucleus}_usable.parquet"
        for path in inputs["sources"]
    ):
        raise ValueError(
            "Prepared feature nucleus differs from the requested model nucleus"
        )
    if sha256(args.features) != inputs["output_sha256"]:
        raise ValueError("Prepared feature file does not match the source manifest")
    roles = partition(args.features)
    print("Identity split", Counter(roles.values()), flush=True)
    train = {}  # One target median per connectivity, environment and solvent.
    evaluate = defaultdict(list)
    scaffold_by_key = defaultdict(set)
    codes_by_row = []
    coverage = Counter()
    examples = {}

    def matrix_rows():
        for key, smiles, scaffold, sites, obs in records(args.features):
            role = roles[key]
            scaffold_by_key[key].add(scaffold)
            by_solvent = {}
            for source, source_role, solvent, peaks, index in obs:
                coverage[f"{role}/{source}/input"] += 1
                if role == "pool" and source != "legacy":
                    continue
                if len(peaks) != len(sites):
                    coverage[f"{role}/{source}/unmatched_cardinality"] += 1
                    continue
                if role == "train" and len(sites) != 1:
                    coverage[f"{role}/{source}/unassigned_multisite"] += 1
                    continue
                if solvent not in by_solvent:
                    selected = []
                    for _, codes, features in sites:
                        selected.append(len(codes_by_row))
                        codes_by_row.append(codes)
                        yield features, solvent
                    by_solvent[solvent] = tuple(selected)
                ids = by_solvent[solvent]
                coverage[f"{role}/{source}/usable"] += 1
                if role == "train":
                    signature = (key, solvent, tuple(codes_by_row[ids[0]]))
                    row, targets = train.setdefault(signature, (ids[0], set()))
                    targets.add(peaks[0])
                else:
                    evaluate[role].append(
                        (key, source, ids, tuple(sorted(peaks)), index)
                    )
                    if role == "pool" and index is not None and index < 32:
                        examples[index] = (smiles, ids[0], peaks[0])

    X = feature_matrix(matrix_rows())
    train_ids = np.array([entry[0] for entry in train.values()], dtype=int)
    y = np.array([np.median(list(entry[1])) for entry in train.values()], dtype=float)
    train_keys = [item[0] for item in train]
    per_key = Counter(train_keys)
    train_weights = np.asarray([1 / per_key[k] for k in train_keys])
    train_weights /= train_weights.mean()
    train_scaffolds = {s for k in per_key for s in scaffold_by_key[k] if s}
    baseline = float(np.median(y))
    print("Sparse features", X.shape, X.nnz, "training rows", len(y), flush=True)
    # Compress repeated measurements (including equivalent input SMILES) in the lookup as well.
    stats = [defaultdict(list) for _ in range(6)]
    for idx, target in zip(train_ids, y):
        for r in (3, 4, 5):
            stats[r][str(codes_by_row[idx][r])].append(float(target))
    tables = [
        {
            code: [float(np.median(vals)), len(vals)]
            for code, vals in table.items()
            if len(vals) >= 2
        }
        for table in stats
    ]
    train.clear()
    del stats
    evaluate = {role: list(dict.fromkeys(rows)) for role, rows in evaluate.items()}
    val = [row for row in evaluate["val"] if len(row[2]) == 1]
    val_ids = np.asarray([row[2][0] for row in val])
    val_y = np.asarray([row[3][0] for row in val])
    val_key_counts = Counter(r[0] for r in val)
    val_w = np.array([1 / val_key_counts[r[0]] for r in val])
    params = {
        "objective": "regression_l1",
        "metric": "l1",
        "learning_rate": 0.055,
        "num_leaves": args.num_leaves,
        "min_data_in_leaf": args.min_leaf,
        "feature_fraction": 0.85,
        "num_threads": args.threads,
        "verbosity": -1,
        "seed": 7351,
        "max_bin": 63,
        "force_col_wise": True,
        "deterministic": True,
    }
    fit = lgb.Dataset(
        X[train_ids], label=y, weight=train_weights, categorical_feature=[0]
    )
    hold = lgb.Dataset(X[val_ids], label=val_y, weight=val_w, reference=fit)
    callbacks = [lgb.log_evaluation(100)]
    if args.fixed_rounds is None:
        callbacks.append(lgb.early_stopping(70, verbose=False))
    tree = lgb.train(
        params,
        fit,
        num_boost_round=args.fixed_rounds or args.max_rounds,
        valid_sets=[hold],
        callbacks=callbacks,
    )
    iteration = tree.best_iteration or tree.current_iteration()
    valid_pred = tree.predict(X[val_ids], num_threads=args.threads)

    def local_or_model(ids, base):
        values = []
        for i, estimate in zip(ids, base):
            local = root_estimate(tables, codes_by_row[i])
            values.append(estimate if local is None else local)
        return np.asarray(values)

    val_lookup = local_or_model(val_ids, valid_pred)
    val_scores = {
        a: float(
            np.average(
                np.abs((1 - a) * valid_pred + a * val_lookup - val_y), weights=val_w
            )
        )
        for a in [0, 0.25, 0.5, 0.75, 1.0]
    }
    alpha = (
        args.environment_weight
        if args.environment_weight is not None
        else min(val_scores, key=val_scores.get)
    )
    print(
        "Validation",
        val_scores,
        "selected",
        alpha,
        "trees",
        iteration,
        flush=True,
    )
    tree.save_model(str(output / "booster.txt"), num_iteration=iteration)
    with gzip.GzipFile(
        filename=str(output / "environments.json.gz"), mode="wb", mtime=0
    ) as stream:
        stream.write(json.dumps(tables, sort_keys=True, separators=(",", ":")).encode())
    split_path = output / "identity-splits.tsv.gz"
    with gzip.GzipFile(filename=str(split_path), mode="wb", mtime=0) as stream:
        for key in sorted(roles):
            stream.write(f"{key}\t{roles[key]}\n".encode())
    config = {
        "feature_schema": 1,
        "nucleus": args.nucleus,
        "environment_weight": alpha,
        "reserved_pool_sha256": next(
            v for k, v in inputs["sources"].items() if k.endswith("valid.lmdb")
        ),
        "training_identities": len(per_key),
        "test_references_sha256": write_test_references(
            args.features, roles, output / "test-references.jsonl.gz"
        ),
        "identity_splits_sha256": sha256(split_path),
        "booster_sha256": sha256(output / "booster.txt"),
        "environments_sha256": sha256(output / "environments.json.gz"),
    }
    (output / "model.json").write_text(json.dumps(config, indent=2) + "\n")
    pred = tree.predict(X, num_threads=args.threads)
    lookup = local_or_model(range(len(pred)), pred)
    est = (1 - alpha) * pred + alpha * lookup
    scored = defaultdict(list)
    tests = output / "heldout-predictions.jsonl.gz"
    with gzip.open(tests, "wt", compresslevel=3) as stream:
        for role, rows in evaluate.items():
            for key, source, ids, truth, index in rows:
                single = len(ids) == 1
                task = "single" if single else "multi"
                categories = [role + "_" + task, role + "_" + task + "_" + source]
                if role == "pool" and index < 32:
                    categories.append("legacy_first32")
                if role in ("test", "pool") and single:
                    s = scaffold_by_key[key]
                    if s and "" not in s and s.isdisjoint(train_scaffolds):
                        categories.append(role + "_single_unseen_scaffold")
                p = np.sort(est[list(ids)])
                # Multi-site comparisons are optimal 1-D peak-set matches, without atom labels.
                for category in categories:
                    for error, target in zip(p - truth, truth):
                        scored[category].append(
                            (key, float(error), float(baseline - target))
                        )
                if role != "val":
                    stream.write(
                        json.dumps(
                            {
                                "split": role,
                                "source": source,
                                "connectivity": key,
                                "source_index": index,
                                "reference_ppm": truth,
                                "sorted_prediction_ppm": p.tolist(),
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
    quality = {}
    for name, rows in scored.items():
        keys, errors, base_errors = zip(*rows)
        quality[name] = {
            **metrics(errors, keys),
            "train_median_baseline_mae_ppm": float(np.mean(np.abs(base_errors))),
        }
    legacy = []
    if args.old_diagnostic:
        from openmolspec_bench.runner import read_prediction_folds

        files = sorted(args.old_diagnostic.glob("*/*.out.pkl"))
        folds = read_prediction_folds(files)
        targets = read_prediction_folds(files, field="target")
        manifest = json.loads((args.old_diagnostic / "input_manifest.json").read_text())
        for idx, (smiles, row, truth) in sorted(examples.items()):
            if manifest["records"][idx]["smiles"] != smiles:
                raise ValueError("Legacy molecule mismatch")
            if not all(
                abs(float(np.ravel(f[idx])[0]) - truth) < 0.001 for f in targets
            ):
                raise ValueError("Legacy target mismatch")
            old = float(np.mean([np.ravel(f[idx])[0] for f in folds]))
            legacy.append(
                {
                    "index": idx,
                    "smiles": smiles,
                    "target_ppm": truth,
                    "old_ppm": old,
                    "new_ppm": float(est[row]),
                }
            )
    if legacy:
        quality["legacy_first32"]["old_model_mae_on_same_rows_ppm"] = float(
            np.mean([abs(r["old_ppm"] - r["target_ppm"]) for r in legacy])
        )
    report = {
        "nucleus": args.nucleus,
        "source_manifest": inputs,
        "feature_schema": 1,
        "split": "First InChIKey block of target-containing component. pool > WanJuan test > WanJuan val > WanJuan train. Other identities use SHA256 80/10/10.",
        "split_identity_counts": dict(Counter(roles.values())),
        "fitted_training_identities": len(per_key),
        "fitted_training_rows": len(y),
        "test_identities_in_fitted_training": len(
            set(per_key) & {k for k, v in roles.items() if v in ("pool", "test", "val")}
        ),
        "raw_observation_coverage": dict(coverage),
        "training_median_ppm": baseline,
        "parameters": params,
        "best_iteration": iteration,
        "validation_macro_mae_by_weight": val_scores,
        "environment_weight": alpha,
        "metrics": quality,
        "legacy_rows": legacy,
        "model": config,
        "heldout_predictions_sha256": sha256(tests),
    }
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        "Completed",
        args.nucleus,
        {k: quality[k] for k in ("test_single", "pool_single", "legacy_first32") if k in quality},
        flush=True,
    )


if __name__ == "__main__":
    main()

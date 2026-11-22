"""Metrics with explicit candidate pools and unmatched-peak coverage."""

import numpy as np


def retrieval_metrics(scores, query_ids, candidate_ids):
    scores = np.asarray(scores, dtype=float)
    if scores.shape != (len(query_ids), len(candidate_ids)) or not scores.size:
        raise ValueError("Score shape must match nonempty query/candidate identities")
    if not np.isfinite(scores).all():
        raise ValueError("Retrieval scores must be finite")
    # Stable ordering makes tied scores deterministic, including all-zero baselines.
    ranks = []
    for row, identity in zip(scores, query_ids):
        order = np.argsort(-row, kind="stable")
        matches = [rank for rank, index in enumerate(order, 1) if candidate_ids[index] == identity]
        if not matches:
            raise ValueError(f"Query identity absent from candidate pool: {identity}")
        ranks.append(matches[0])
    ranks = np.asarray(ranks)
    return {**{f"recall_at_{k}": float(np.mean(ranks <= k)) for k in (1, 5, 10)},
            "mrr": float(np.mean(1 / ranks)), "queries": len(ranks),
            "candidate_pool": len(candidate_ids), "unique_candidates": len(set(candidate_ids)),
            "tie_policy": "stable_candidate_order"}


def weighted_r2(predicted, reference, weights):
    """Pooled coefficient of determination; undefined for constant reference shifts."""
    reference = np.asarray(reference, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    weights = np.asarray(weights, dtype=float)
    center = np.average(reference, weights=weights)
    total = np.dot(weights, (reference - center) ** 2)
    if reference.min() == reference.max() or total == 0:
        return None
    return float(1 - np.dot(weights, (predicted - reference) ** 2) / total)


def peak_metrics(predictions, references):
    from scipy.optimize import linear_sum_assignment

    if len(predictions) != len(references) or not len(predictions):
        raise ValueError("Need nonempty paired peak lists")
    absolute, squared, fractions, count_errors = [], [], [], []
    matched_pred, matched_ref, weights = [], [], []
    used = 0
    for predicted, reference in zip(predictions, references):
        predicted, reference = np.asarray(predicted, dtype=float), np.asarray(reference, dtype=float)
        if predicted.ndim != 1 or reference.ndim != 1:
            raise ValueError("Peak lists must be one dimensional")
        if not np.isfinite(predicted).all() or not np.isfinite(reference).all():
            raise ValueError("Peak values must be finite")
        count_errors.append(abs(len(predicted) - len(reference)))
        fractions.append(min(len(predicted), len(reference)) / max(len(predicted), len(reference), 1))
        if not len(predicted) or not len(reference):
            continue
        costs = np.abs(predicted[:, None] - reference[None, :])
        rows, columns = linear_sum_assignment(costs)
        matched_pred.extend(predicted[rows])
        matched_ref.extend(reference[columns])
        weights.extend(np.full(len(rows), 1.0 / len(rows)))
        errors = costs[rows, columns]
        absolute.append(float(errors.mean()))
        squared.append(float(np.mean(errors ** 2)))
        used += 1
    if not used:
        raise ValueError("No nonempty peak pairs")
    return {"matched_peak_r2": weighted_r2(matched_pred, matched_ref, weights),
            "matched_peaks": len(matched_ref),
            "reference_peaks": sum(map(len, references)), "predicted_peaks": sum(map(len, predictions)),
            "matched_peak_mae_ppm": float(np.mean(absolute)),
            "matched_peak_rmse_ppm": float(np.sqrt(np.mean(squared))),
            "peak_count_mae": float(np.mean(count_errors)),
            "matched_fraction": float(np.mean(fractions)), "examples": len(predictions),
            "scored_examples": used, "aggregation": "equal_weight_per_molecule",
            "assignment": "minimum_absolute_error_without_atom_labels"}


def regression_metrics(predicted, reference):
    predicted, reference = np.asarray(predicted, dtype=float), np.asarray(reference, dtype=float)
    if predicted.shape != reference.shape or not predicted.size:
        raise ValueError("Need equally shaped nonempty regression arrays")
    if not np.isfinite(predicted).all() or not np.isfinite(reference).all():
        raise ValueError("Regression arrays must be finite")
    error = predicted - reference
    return {"mae_ev": float(np.mean(np.abs(error))), "rmse_ev": float(np.sqrt(np.mean(error ** 2))),
            "examples": int(predicted.size)}

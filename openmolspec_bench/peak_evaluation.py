"""Fresh peak-list inference and count-sensitive scoring on measured H/C spectra."""

import numpy as np
from scipy.optimize import linear_sum_assignment
from .metrics import peak_metrics


def matching_errors(predictions, references, penalty):
    errors = []
    for predicted, observed in zip(predictions, references):
        cost = np.minimum(np.abs(np.subtract.outer(predicted, observed)), 2 * penalty)
        i, j = linear_sum_assignment(cost)
        errors.append(
            (cost[i, j].sum() + penalty * abs(len(observed) - len(predicted)))
            / max(len(observed), len(predicted), 1)
        )
    return np.asarray(errors)


def evaluate(runner, directory, references):
    from openmolspec.assigned_shifts import PeakSpectrumPredictor

    model = PeakSpectrumPredictor(directory)
    predictions, measured, ids, examples = [], [], [], []
    for smiles, peaks in references.items():
        result = model.predict(smiles)
        values = result["prediction_ppm"]
        ids.append(smiles)
        predictions.append(values)
        measured.append(peaks)
        if len(examples) < 3:
            examples.append(
                dict(
                    smiles=smiles,
                    reference_ppm=peaks,
                    prediction_ppm=values,
                    peaks=result["peaks"],
                )
            )
    metrics = peak_metrics(predictions, measured)
    penalty = 1.0 if model.nucleus == "1H" else 10.0
    metrics["count_penalized_error_ppm"] = float(
        matching_errors(predictions, measured, penalty).mean()
    )
    return dict(
        model="peak_spectrum",
        metrics=metrics,
        inference_mode="fresh_from_smiles",
        selected_references=len(references),
        covered_references=len(predictions),
        sample_ids=ids,
        examples=examples,
        model_config=runner.artifact(directory / "model.json"),
        unmatched_peak_penalty_ppm=penalty,
    )

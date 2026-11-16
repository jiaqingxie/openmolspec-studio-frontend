# H/C peak-to-atom assignment

Propose atom assignments for measured peaks and a known structure.

## Model and protocol

Run the released liquid NMRNet H/C fold-0 checkpoint directly on a seeded 3D conformer. Require complete checkpoint restoration, preserve RDKit AddHs(input SMILES) atom indices, group topological symmetry sites, and use minimum-cost matching with explicit unmatched peaks and sites. Default tolerances are 0.5 ppm for H and 5 ppm for C.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "smiles": "CCO",
  "nucleus": "13C",
  "peaks_ppm": [
    18.2,
    58.3
  ],
  "tolerance_ppm": 5.0
}
```

## Outputs and metrics

Report matched fraction, residual MAE and candidate atom indices. The 32-molecule carbon run matched 488 peaks; an additional online hydrogen request completed. assignment_accuracy is null because independent atom-assignment labels were not supplied.

Metric fields: `matched_peak_fraction_macro`, `matched_residual_mae_ppm`, `assignment_accuracy`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.assignment --limit 8 --output results/nmr-assignment.json
```

## Interpretation and limits

Residual error is not assignment accuracy. Topological symmetry is not proof of magnetic equivalence. Solvent and conformer ensembles are not modeled; H/C only. See the source JSON for input geometry, checkpoint hash and sample identities.

## Recorded results

```json
[
  {
    "task": "nmr.assignment",
    "status": "passed",
    "metrics": {
      "molecules": 32,
      "matched_peaks": 488,
      "matched_peak_fraction_macro": 0.9392376720501721,
      "matched_residual_mae_ppm": 0.8991307922920895,
      "assignment_accuracy": null
    },
    "selection": {
      "read": 32,
      "missing_modality": 0,
      "duplicate_structure": 0,
      "exceeds_model_capacity": 0
    },
    "purpose": "real_peak_assignment_execution_not_atom_accuracy_benchmark",
    "limitations": [
      "No experimental atom assignment ground truth supplied.",
      "Symmetry is topological; conformer/solvent effects can change observed equivalence.",
      "Residual and coverage are diagnostics, not assignment accuracy.",
      "Training overlap unverified; frozen model is not solvent-conditioned."
    ],
    "source_file": "assignment_carbon32_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-assignment.ipynb)

## Source

[Original implementation / release](https://github.com/Colin-Jay/NMRNet)

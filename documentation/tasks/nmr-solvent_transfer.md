# H/C cross-solvent transfer: experimental-reference baseline

Estimate target-solvent shifts from a measured source-solvent spectrum using paired experimental references.

## Model and protocol

Use reviewed, one-dimensional H/C NMRShiftDB records; exclude calculated-condition entries, unknown/mixed solvents and conflicting repeated atom shifts. Pair the same database atom across solvents. Retrieve the nearest other molecular connectivity by Morgan Tanimoto, then the nearest source shift, and add that reference atom's measured solvent difference. No parameters are fitted. All records sharing the query connectivity, including stereoisomers, are excluded.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "smiles": "CCO",
  "nucleus": "1H",
  "source_solvent": "CDCl3",
  "target_solvent": "DMSO-d6",
  "source_peaks_ppm": [
    1.2,
    3.65
  ]
}
```

## Outputs and metrics

Report H and C errors separately and compare with leaving the source shift unchanged. The completed run covers 32 distinct molecules and 296 paired atoms. Predictions expose reference molecules, atom/spectrum IDs and similarity.

Metric fields: `mae_ppm`, `unchanged_shift_mae_ppm`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.solvent_transfer --limit 8 --output results/nmr-solvent_transfer.json
```

## Interpretation and limits

This is a retrieval baseline, not a pretrained neural solvent model. It does not consistently improve both nuclei over unchanged shifts. The reference library is small, and temperature/concentration/reference conventions are not independently harmonized. Neural solvent checkpoints remain unavailable.

## Recorded results

```json
[
  {
    "task": "nmr.solvent_transfer",
    "status": "passed",
    "metrics": {
      "13C": {
        "atoms": 140,
        "molecules": 13,
        "mae_ppm": 1.0942857142857159,
        "unchanged_shift_mae_ppm": 1.1637142857142861,
        "rmse_ppm": 1.9093510490665238
      },
      "1H": {
        "atoms": 156,
        "molecules": 19,
        "mae_ppm": 0.13762820512820512,
        "unchanged_shift_mae_ppm": 0.13538461538461527,
        "rmse_ppm": 0.3761793421174233
      }
    },
    "counts": {
      "distinct_molecules": 32,
      "paired_atoms": 296,
      "skipped_pairs": 3
    },
    "seed": 42,
    "model_kind": "retrieval_baseline_not_neural_model",
    "purpose": "leave_one_connectivity_out_reference_baseline",
    "limitations": [
      "Existing neural solvent model is not installed; this is a reference-retrieval baseline.",
      "No parameter fitting or test-label calibration. Query connectivity and stereoisomers excluded.",
      "Temperature, concentration and original experimental referencing are not independently harmonized.",
      "Low-similarity references can be inaccurate; a successful run does not establish useful accuracy."
    ],
    "source_file": "solvent_transfer_reference32_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-solvent_transfer.ipynb)

## Source

[Original implementation / release](https://nmrshiftdb.nmr.uni-koeln.de/)

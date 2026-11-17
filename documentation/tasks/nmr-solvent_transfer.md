# H/C cross-solvent transfer: experimental-reference baseline

Estimate target-solvent shifts from a measured source-solvent spectrum using paired experimental references.

## Current evidence

Executable reference baseline; H does not improve on unchanged shifts. A solvent-conditioned model and independent paired data are still needed.

## What goes in

| Field | Meaning |
| --- | --- |
| `structure / nucleus` | Molecular connectivity and 1H or 13C. |
| `solvents` | Explicit source and target solvents that have paired references. |
| `source_ppm` | Measured source-solvent shifts in ppm. |

## What comes out

| Field | Meaning |
| --- | --- |
| `target_ppm / delta_ppm` | Estimated target shift and solvent difference from an independent reference. |
| `reference` | Reference identity, spectra/atom IDs, Tanimoto similarity and exclusions. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

![nmr.solvent_transfer actual results](../assets/gallery/nmr-solvent_transfer.png)

[SVG](../assets/gallery/nmr-solvent_transfer.svg) · [PNG](../assets/gallery/nmr-solvent_transfer.png) · [Full input/output JSON](../assets/examples/nmr-solvent_transfer.json)

<details><summary>Inspect the actual input and output fields</summary>

```json
{
  "input": {
    "nucleus": "1H",
    "source_ppm": 1.45,
    "source_solvent": "CD3OD",
    "target_solvent": "acetone-d6",
    "query_connectivity": "C1CCCCC1"
  },
  "output": {
    "source_ppm": 1.45,
    "predicted_target_ppm": 1.3799999999999997,
    "predicted_delta_ppm": -0.07000000000000028,
    "source_solvent": "CD3OD",
    "target_solvent": "acetone-d6",
    "nucleus": "1H",
    "query_connectivity": "C1CCCCC1",
    "reference": {
      "identity": "C1COCCO1",
      "molecule_id": "10016061",
      "atom_id": "10093018",
      "source_ppm": 3.66,
      "target_ppm": 3.59,
      "source_spectrum_ids": [
        "20197666"
      ],
      "target_spectrum_ids": [
        "20197080"
      ]
    },
    "tanimoto_similarity": 0.125,
    "same_connectivity_excluded": true,
    "method": "nearest_paired_experimental_reference_delta",
    "model_kind": "retrieval_baseline_not_neural_model",
    "query_molecule_id": "10811",
    "query_atom_id": "10046537",
    "target_reference_ppm": 1.43,
    "source_spectrum_ids": [
      "20197663"
    ],
    "target_spectrum_ids": [
      "20197659"
    ]
  }
}
```

</details>

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | 13C | atoms | 140 |
| recorded evaluation | 13C | molecules | 13 |
| recorded evaluation | 13C | mae_ppm | 1.09429 |
| recorded evaluation | 13C | unchanged_shift_mae_ppm | 1.16371 |
| recorded evaluation | 13C | rmse_ppm | 1.90935 |
| recorded evaluation | 1H | atoms | 156 |
| recorded evaluation | 1H | molecules | 19 |
| recorded evaluation | 1H | mae_ppm | 0.137628 |
| recorded evaluation | 1H | unchanged_shift_mae_ppm | 0.135385 |
| recorded evaluation | 1H | rmse_ppm | 0.376179 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

Use reviewed, one-dimensional H/C NMRShiftDB records; exclude calculated-condition entries, unknown/mixed solvents and conflicting repeated atom shifts. Pair the same database atom across solvents. Retrieve the nearest other molecular connectivity by Morgan Tanimoto, then the nearest source shift, and add that reference atom's measured solvent difference. No parameters are fitted. All records sharing the query connectivity, including stereoisomers, are excluded.

Report H and C errors separately and compare with leaving the source shift unchanged. The completed run covers 32 distinct molecules and 296 paired atoms. Predictions expose reference molecules, atom/spectrum IDs and similarity.

## Reproduce

[Notebook with executed figures](../notebooks/nmr-solvent_transfer.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.solvent_transfer --limit 8 --output results/nmr-solvent_transfer-new.json
```

## Limits and provenance

This is a retrieval baseline, not a pretrained neural solvent model. It does not consistently improve both nuclei over unchanged shifts. The reference library is small, and temperature/concentration/reference conventions are not independently harmonized. Neural solvent checkpoints remain unavailable.

<details><summary>Source reports and SHA-256 fingerprints</summary>

- [solvent_transfer_reference32_20261116.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/solvent_transfer_reference32_20261116.json) — SHA-256 `7532dc2b785a93aa51323934bb748b768f1bfc7c820809bc2065d0840afc543f`

</details>


[Original model / 原模型](https://nmrshiftdb.nmr.uni-koeln.de/) · [Model review / 模型检查](../model-audit.md)

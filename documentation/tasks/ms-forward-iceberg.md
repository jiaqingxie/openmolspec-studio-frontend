# Molecule to MS/MS with ICEBERG

Predict an MS/MS peak list from a molecular structure under an explicitly supplied adduct, collision energy and instrument. The model parameters remain frozen.

## Current evidence

Appropriate author model interface and explicit conditions; 31 scored spectra are insufficient for a broad accuracy claim. Protocol/overlap audit precedes fine-tuning.

## What goes in

| Field | Meaning |
| --- | --- |
| `smiles / adduct` | Molecular structure and ion/adduct, e.g. the actual [M+H]+ or [M+Na]+ in the record. |
| `collision_energy / instrument` | Recorded acquisition settings supported by the released model; do not invent missing values. |
| `precursor_mz` | Recorded precursor m/z; input conventions follow the author interface. |

## What comes out

| Field | Meaning |
| --- | --- |
| `predicted_peaks` | Pairs of m/z and relative intensity; figures retain the top 100 predicted peaks. |
| `similarity` | Cosine/entropy similarity to all observed reference peaks, with skipped records counted. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

![ms.forward.iceberg actual results](../assets/gallery/ms-forward-iceberg.png)

[SVG](../assets/gallery/ms-forward-iceberg.svg) · [PNG](../assets/gallery/ms-forward-iceberg.png) · [Full input/output JSON](../assets/examples/ms-forward-iceberg.json)

<details><summary>Inspect the actual input and output fields</summary>

```json
{
  "input": {
    "smiles": "C/C1=C\\[C@@H](C)C/C=C/[C@H]2[C@@H]3O[C@]3(C)[C@@H](C)[C@H]3[C@H](Cc4c[nH]c5ccccc45)NC(=O)[C@]32C(=O)/C=C/C(=O)[C@@H]1O",
    "adduct": "[M+Na]+",
    "collision_energy": "35.0",
    "instrument": "Orbitrap",
    "precursor_mz": 551.2511
  },
  "sample_id": "MassSpecGymID0000403",
  "output": {
    "predicted_peaks_top100": {
      "length": 100,
      "first_values": [
        [
          93.06987621515076,
          0.0043686628341674805
        ],
        [
          129.0573002311496,
          0.004620126914232969
        ],
        [
          130.065125248125,
          0.07967650890350342
        ],
        [
          131.07295026510042,
          0.011109611950814724
        ]
      ]
    }
  },
  "reference": {
    "observed_peaks": {
      "length": 12,
      "first_values": [
        [
          160.0366,
          0.03803803803803804
        ],
        [
          240.0992,
          0.03803803803803804
        ],
        [
          287.1152,
          0.04704704704704705
        ],
        [
          289.0945,
          0.042042042042042045
        ]
      ]
    }
  },
  "metrics": {
    "cosine_similarity": 0.9412847417548776,
    "entropy_similarity": 0.6221104979157452,
    "predicted_nonzero_bins": 100,
    "reference_nonzero_bins": 12
  }
}
```

</details>

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | cosine_similarity | 0.4625 |
| recorded evaluation | recorded model | entropy_similarity | 0.369847 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

The adapter loads the authors' released checkpoint and calls their predict_mol interface. Our held-out CSV provides observed peaks; acquisition metadata must match its spectrum ID, molecule and adduct. Duplicate molecules are excluded by default.

Mass is in Da/m/z. Scores use 150000 max-pooled bins over 0–1500 Da, the top 100 predicted bins, cosine similarity and entropy similarity against all observed peaks. Missing acquisition conditions are skipped without imputation. This is not identical to a benchmark that discards unassigned observed peaks.

## Reproduce

[Notebook with executed figures](../notebooks/ms-forward-iceberg.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.forward.iceberg --limit 8 --output results/ms-forward-iceberg-new.json
```

## Limits and provenance

Pretrained MassSpecGym weights may overlap a differently constructed split. Training overlap and complete instrument/adduct support metadata have not been independently established.

<details><summary>Source reports and SHA-256 fingerprints</summary>

- [ms_iceberg_32_molecules_20261116.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/ms_iceberg_32_molecules_20261116.json) — SHA-256 `7b403aa40d8478ff3ff8ee93ed6bec4151493d88eb0d2521f037542889c443ee`

</details>


[Original model / 原模型](https://github.com/coleygroup/ms-pred) · [Model review / 模型检查](../model-audit.md)

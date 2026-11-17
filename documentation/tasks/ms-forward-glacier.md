# Molecule to MS/MS with GLACIER

Predict an MS/MS peak list from a molecular structure under an explicitly supplied adduct, collision energy and instrument. The model parameters remain frozen.

## Example and evaluation

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

![ms.forward.glacier actual results](../assets/gallery/ms-forward-glacier.png)

[SVG](../assets/gallery/ms-forward-glacier.svg) · [PNG](../assets/gallery/ms-forward-glacier.png) · [Full input/output JSON](../assets/examples/ms-forward-glacier.json)

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
          67.0542266590246,
          0.011822191998362541
        ],
        [
          81.06987672302459,
          0.16171321272850037
        ],
        [
          83.0491412790246,
          0.008260359987616539
        ],
        [
          83.0855267569754,
          0.0016736892284825444
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
    "cosine_similarity": 0.029863639020685673,
    "entropy_similarity": 0.03731316551570296,
    "predicted_nonzero_bins": 100,
    "reference_nonzero_bins": 12
  }
}
```

</details>

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | cosine_similarity | 0.485717 |
| recorded evaluation | recorded model | entropy_similarity | 0.41328 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

The adapter loads the authors' released checkpoint and calls their predict_mol interface. Our held-out CSV provides observed peaks; acquisition metadata must match its spectrum ID, molecule and adduct. Duplicate molecules are excluded by default.

Mass is in Da/m/z. Scores use 150000 max-pooled bins over 0–1500 Da, the top 100 predicted bins, cosine similarity and entropy similarity against all observed peaks. Missing acquisition conditions are skipped without imputation. This is not identical to a benchmark that discards unassigned observed peaks.

## Reproduce

[Notebook with executed figures](../notebooks/ms-forward-glacier.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.forward.glacier --limit 8 --output results/ms-forward-glacier-new.json
```

## Call and adapt this model

```python
from openmolspec.model import MSPredictor
model = MSPredictor(model='glacier', source='/path/to/ms-pred',
    weights='/path/to/weights', python='/path/to/ms-env/bin/python')
result = model.predict(smiles=smiles, adduct='[M+H]+',
    collision_energy=20., instrument='Orbitrap')
```

Fine-tune using the [author training modules](https://github.com/coleygroup/ms-pred). Build molecule-disjoint splits with structures, acquisition conditions, measured peak intensities and the fragment targets required by the chosen architecture. ICEBERG exposes `ms_pred.iceberg.train_gen` and `ms_pred.iceberg.train_inten`; GLACIER exposes `ms_pred.glacier.train_joint` and contrastive joint training. Inspect each entry’s `--help` and the released configuration before launching. ICEBERG fragment generation uses binary cross-entropy over valid atom decisions; its intensity module supports cosine or entropy objectives. GLACIER joint/contrastive losses depend on its configuration; preserve the selected variant when reporting fine-tuning. Here m is the scheduled MAGMa weight, w_I and w_F are configured loss weights, and fragment supervision combines matched atom-membership and fragment-cardinality cross-entropy. The contrastive variant additionally uses its configured decoy objective.

$$L_{\rm cosine}=1-\frac{\hat s\cdot s}{\|\hat s\|\|s\|}.$$

$$L_{\rm joint}=w_I[mL_{I,\rm MAGMa}+(1-m)L_{I,\rm end-to-end}]+w_FmL_{\rm fragment}.$$

## Data requirements and references

Pretrained MassSpecGym weights may overlap a differently constructed split. Training overlap and complete instrument/adduct support metadata have not been independently established.

<details><summary>Source reports and SHA-256 fingerprints</summary>

- [ms_glacier_32_molecules_20261116.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/ms_glacier_32_molecules_20261116.json) — SHA-256 `a4d084c72c7df758f49500942cdfcea91047cb3da3616b9adb93b5bc6e8470c6`

</details>


[Original model / 原模型](https://github.com/coleygroup/ms-pred) · [Model review / 模型检查](../model-audit.md)

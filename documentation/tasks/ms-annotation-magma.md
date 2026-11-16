# MS/MS peak annotation with MAGMa

Enumerate candidate molecular fragments and match their masses to observed MS/MS peaks. This is an algorithmic task and uses no trained parameters.

## Current evidence

Algorithmic annotation, not a trainable neural model. Improve matching and validation rather than propose fine-tuning.

## What goes in

| Field | Meaning |
| --- | --- |
| `smiles / peaks` | Known structure, measured MS/MS peaks [m/z, relative intensity], and adduct. |
| `ppm_tolerance` | Mass tolerance, default 10 ppm; not an NMR chemical-shift tolerance. |

## What comes out

| Field | Meaning |
| --- | --- |
| `peak_annotations` | Candidate fragments, formulas, mass errors and atom/bond indices on engine_smiles. |
| `interpretation` | Algorithmic candidate explanations; neither learned predictions nor unique confirmed mechanisms. |

## A real recorded example

The first recorded example is shown below, regardless of whether it succeeds. Array previews explicitly state their lengths; download the evidence JSON for complete values. Reference labels are kept separate from model inputs.

```json
{
  "input": {
    "smiles": "C1=CC=C(C(=C1)C2=CC=C(C=C2)C(=O)O)C3=NNN=N3",
    "adduct": "[M+H]+",
    "observed_peaks": {
      "length": 40,
      "first_values": [
        [
          86.0158,
          0.14814814814814814
        ],
        [
          87.0237,
          0.16016016016016016
        ],
        [
          97.0082,
          0.06906906906906907
        ],
        [
          98.0159,
          1.0
        ]
      ]
    }
  },
  "sample_id": "MassSpecGymID0046618",
  "output": {
    "engine_smiles": "O=C(O)c1ccc(-c2ccccc2-c2nn[nH]n2)cc1",
    "peak_annotations": {
      "length": 40,
      "first_values": [
        {
          "peak_id": 7,
          "mz": 86.0158,
          "intensity": 0.14814814814814814,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 16256,
            "atom_indices": {
              "length": 7,
              "first_values": [
                7,
                8,
                9,
                10
              ]
            },
            "bond_indices_cut": [
              6,
              13,
              21
            ],
            "bond_atom_pairs_cut": [
              [
                6,
                7
              ],
              [
                13,
                14
              ],
              [
                17,
                13
              ]
            ],
            "formula": "C7H4",
            "matched_mass": 85.007825032,
            "ppm_diff": 8.21707883641277,
            "score": 5.0,
            "h_shift": -3,
            "tree_depth": 3,
            "parent_fragment_ids": [
              130944,
              245632,
              802815
            ],
            "lineage_root_to_fragment": [
              1048575,
              262016,
              245632,
              16256
            ]
          }
        },
        {
          "peak_id": 8,
          "mz": 87.0237,
          "intensity": 0.16016016016016016,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 786554,
            "atom_indices": {
              "length": 7,
              "first_values": [
                1,
                3,
                4,
                5
              ]
            },
            "bond_indices_cut": [
              0,
              1,
              6
            ],
            "bond_atom_pairs_cut": [
              [
                0,
                1
              ],
              [
                1,
                2
              ],
              [
                6,
                7
              ]
            ],
            "formula": "C7H4",
            "matched_mass": 86.015650064,
            "ppm_diff": 8.992363592338872,
            "score": 5.0,
            "h_shift": -2,
            "tree_depth": 3,
            "parent_fragment_ids": [
              786555,
              786558,
              1048570
            ],
            "lineage_root_to_fragment": [
              1048575,
              1048574,
              1048570,
              786554
            ]
          }
        },
        {
          "peak_id": 10,
          "mz": 97.0082,
          "intensity": 0.06906906906906907,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 8160,
            "atom_indices": {
              "length": 8,
              "first_values": [
                5,
                6,
                7,
                8
              ]
            },
            "bond_indices_cut": [
              4,
              12,
              17
            ],
            "bond_atom_pairs_cut": [
              [
                4,
                5
              ],
              [
                12,
                13
              ],
              [
                6,
                18
              ]
            ],
            "formula": "C8H5",
            "matched_mass": 96.0,
            "ppm_diff": 9.620291666697275,
            "score": 6.0,
            "h_shift": -5,
            "tree_depth": 3,
            "parent_fragment_ids": [
              262112,
              532479,
              794607
            ],
            "lineage_root_to_fragment": [
              1048575,
              1048559,
              794607,
              8160
            ]
          }
        },
        {
          "peak_id": 11,
          "mz": 98.0159,
          "intensity": 1.0,
          "matched": true,
          "matched_fragment": {
            "fragment_id": 786936,
            "atom_indices": {
              "length": 8,
              "first_values": [
                3,
                4,
                5,
                6
              ]
            },
            "bond_indices_cut": [
              2,
              8,
              20
            ],
            "bond_atom_pairs_cut": [
              [
                1,
                3
              ],
              [
                8,
                9
              ],
              [
                12,
                7
              ]
            ],
            "formula": "C8H5",
            "matched_mass": 97.007825032,
            "ppm_diff": 8.23145967595748,
            "score": 6.0,
            "h_shift": -4,
            "tree_depth": 3,
            "parent_fragment_ids": [
              786943,
              790520,
              1048056
            ],
            "lineage_root_to_fragment": [
              1048575,
              1048568,
              1048056,
              786936
            ]
          }
        }
      ]
    }
  }
}
```

![ms.annotation.magma actual results](../assets/gallery/ms-annotation-magma.png)

[SVG](../assets/gallery/ms-annotation-magma.svg) · [PNG](../assets/gallery/ms-annotation-magma.png) · [Full input/output JSON](../assets/examples/ms-annotation-magma.json)

## Actual evaluation results

| Dataset / scope | Model / variant | Metric | Value |
| --- | --- | --- | ---: |
| recorded evaluation | recorded model | matched_peak_fraction | 0.568182 |
| recorded evaluation | recorded model | checked_fragments | 1534 |

Sample sizes and candidate pools belong to each run. The figure may show one molecule; the table reports the cited run, not a new benchmark on that molecule.

## Model and method

The adapter retains MAGMa v8's original canonicalization and 10 ppm default tolerance. Every exported fragment is checked against engine_smiles, the actual graph used by the engine, rather than assuming the input SMILES has the same atom order.

Report matched-peak fraction, annotated-spectrum count and checked-fragment count. A matched fragment is an algorithmic explanation, not an experimentally confirmed unique fragmentation mechanism.

## Reproduce

[Notebook with executed figures](../notebooks/ms-annotation-magma.ipynb) · [Quick Start](../quickstart.md)

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.annotation.magma --limit 8 --output results/ms-annotation-magma-new.json
```

## Limits and provenance

Hydrogen shifts, graph depth and canonicalization have specific engine semantics. Do not reinterpret graph depth as an experimentally measured reaction sequence.

- [magma_real_test_verified_20261115.json](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/magma_real_test_verified_20261115.json) — SHA-256 `e65563b00863389105f5eae392d493167d693ac4ca38b9f1abfbd40942d1946b`

[Original model / 原模型](https://github.com/Dsadd4/MassSpecGym-MAGMA-annotation) · [Model review / 模型检查](../model-audit.md)

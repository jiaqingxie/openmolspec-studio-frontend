# MS/MS peak annotation with MAGMa

Enumerate candidate molecular fragments and match their masses to observed MS/MS peaks. This is an algorithmic task and uses no trained parameters.

## Model and protocol

The adapter retains MAGMa v8's original canonicalization and 10 ppm default tolerance. Every exported fragment is checked against engine_smiles, the actual graph used by the engine, rather than assuming the input SMILES has the same atom order.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "spec_id": "example-input-only",
  "smiles": "CCO",
  "adduct": "[M+H]+",
  "collision_energy": 20,
  "instrument": "Orbitrap",
  "precursor_mz": 47.0491,
  "peaks": [
    [
      31.0178,
      1.0
    ],
    [
      47.0491,
      0.4
    ]
  ]
}
```

## Outputs and metrics

Report matched-peak fraction, annotated-spectrum count and checked-fragment count. A matched fragment is an algorithmic explanation, not an experimentally confirmed unique fragmentation mechanism.

Metric fields: `matched_peak_fraction`, `checked_fragments`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.annotation.magma --limit 8 --output results/ms-annotation-magma.json
```

## Interpretation and limits

Hydrogen shifts, graph depth and canonicalization have specific engine semantics. Do not reinterpret graph depth as an experimentally measured reaction sequence.

## Recorded results

```json
[
  {
    "task": "ms.annotation.magma",
    "metrics": {
      "matched_peak_fraction": 0.5681818181818182,
      "annotated_spectra": 2,
      "checked_fragments": 1534
    },
    "counts": {
      "passed": 2
    },
    "selection": {
      "split_rows_examined": 2040,
      "exceeds_heavy_atom_limit": 2005,
      "duplicate_molecule": 33,
      "missing_acquisition_metadata": 0
    },
    "source_file": "magma_real_test_verified_20261115.json",
    "sample_limit": 2
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/ms-annotation-magma.ipynb)

## Source

[Original implementation / release](https://github.com/Dsadd4/MassSpecGym-MAGMA-annotation)

# Molecule to MS/MS with ICEBERG

Predict an MS/MS peak list from a molecular structure under an explicitly supplied adduct, collision energy and instrument. The model parameters remain frozen.

## Model and protocol

The adapter loads the authors' released checkpoint and calls their predict_mol interface. Our held-out CSV provides observed peaks; acquisition metadata must match its spectrum ID, molecule and adduct. Duplicate molecules are excluded by default.

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

Mass is in Da/m/z. Scores use 150000 max-pooled bins over 0–1500 Da, the top 100 predicted bins, cosine similarity and entropy similarity against all observed peaks. Missing acquisition conditions are skipped without imputation. This is not identical to a benchmark that discards unassigned observed peaks.

Metric fields: `cosine_similarity`, `entropy_similarity`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks ms.forward.iceberg --limit 8 --output results/ms-forward-iceberg.json
```

## Interpretation and limits

Pretrained MassSpecGym weights may overlap a differently constructed split. Training overlap and complete instrument/adduct support metadata have not been independently established.

## Recorded results

```json
[
  {
    "task": "ms.forward.iceberg",
    "metrics": {
      "cosine_similarity": 0.4624995623966228,
      "entropy_similarity": 0.3698472199736009
    },
    "counts": {
      "passed": 31,
      "skipped": 1
    },
    "selection": {
      "split_rows_examined": 1444,
      "exceeds_heavy_atom_limit": 473,
      "duplicate_molecule": 939,
      "missing_acquisition_metadata": 0
    },
    "sampling": "first_real_test_records_with_at_most_40_heavy_atoms",
    "unique_molecules": 32,
    "source_file": "ms_iceberg_32_molecules_20261116.json",
    "sample_limit": 32
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/ms-forward-iceberg.ipynb)

## Source

[Original implementation / release](https://github.com/coleygroup/ms-pred)

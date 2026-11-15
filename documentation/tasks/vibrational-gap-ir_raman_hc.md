# HOMO–LUMO gap prediction: IR + Raman + H/C

Predict the molecular HOMO–LUMO gap in eV from spectral inputs, using the existing shared spectroscopy Transformer.

## Model and protocol

The checkpoint was trained for ir-raman-nmr inputs. Complete-input evaluation supplies both IR/Raman and H/C peaks. Other variants deliberately omit channels and are ablations of the same four-modality checkpoint, not separately trained unimodal models.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "ir": "1024 min-max-normalized intensities",
  "raman": "1024 min-max-normalized intensities",
  "wavenumber_cm1": [
    400,
    4000
  ],
  "nmr_h_shifts_ppm": [
    1.2,
    3.65
  ],
  "nmr_c_shifts_ppm": [
    18.2,
    58.3
  ],
  "nmr_reference_id": "must match checkpoint",
  "formula": "not supplied to Vib2Mol"
}
```

## Outputs and metrics

The bundled Vib2Mol LMDB stores gap in Hartree; convert it once to eV using 27.211386245988. The prediction is unnormalized with the checkpoint's stored target mean/std. H/C normalization and reference must agree with the checkpoint. Report MAE/RMSE and the fixed training-mean baseline on exactly the same records.

Metric fields: `mae_ev`, `rmse_ev`. Domain: `computed`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks vibrational.gap.ir_raman_hc --limit 8 --output results/vibrational-gap-ir_raman_hc.json
```

## Interpretation and limits

A small first-record sample may be biased by source order. Use seeded reservoir sampling for broader checks; missing-channel scores must remain separate from complete-input scores.

## Recorded results

```json
[
  {
    "task": "vibrational.gap.ir_raman_hc",
    "dataset_name": null,
    "status": "passed",
    "metrics": {
      "mae_ev": 0.1314457535089349,
      "rmse_ev": 0.20596364382966384,
      "examples": 128
    },
    "given_nmr": true,
    "source_counts": {
      "ZINCV2": 58,
      "SDBS": 4,
      "PCQM4MV2": 20,
      "WILEYIR": 9,
      "ZINCV1": 12,
      "RXN": 6,
      "QM9": 18,
      "WILEYRAMAN": 1
    },
    "selection": {
      "read": 20390,
      "duplicate_structure": 3662,
      "eligible_distinct_structures": 16728,
      "selected": 128
    },
    "sampling": "reservoir",
    "seed": 42,
    "training_mean_baseline": {
      "constant_ev": 5.645122750946045,
      "mae_ev": 0.8999401965027582,
      "rmse_ev": 1.0696170714220543,
      "examples": 128
    },
    "source_file": "gap_protocol_random128_20261116.json",
    "sample_limit": 128
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/vibrational-gap-ir_raman_hc.ipynb)

## Source

[Original implementation / release](https://github.com/X1nyuLu/openSpec-alpha)

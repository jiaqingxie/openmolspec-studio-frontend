# Peak-to-atom assignment

Map observed peaks to atoms in a known structure.

## Model and protocol

Candidate approaches are frozen atomwise NMRNet plus matching, or released TransPeakNet H/C HSQC weights and matching code. Requires reference atom indices on the exact graph, symmetry handling and verified experimental assignments. Unassigned H/C peak lists do not provide assignment ground truth.

## Inputs and example

The example below illustrates the schema; it is not a measured spectrum or an accuracy result.

```json
{
  "smiles": "CCO",
  "nucleus": "13C",
  "observed_peaks_ppm": [
    18.2,
    58.3
  ],
  "atom_index_basis": "RDKit molecule reconstructed from the exact input SMILES"
}
```

## Outputs and metrics

No validated score is emitted while required assets or adapters are missing.

Metric fields: `assignment_accuracy`. Domain: `experimental`.

## Run the existing model

```bash
python -m openmolspec_bench run --workspace /path/to/OpenMolSpec \
  --tasks nmr.assignment --limit 8 --output results/nmr-assignment.json
```

## Interpretation and limits

This task remains explicit in the catalog and is skipped rather than trained to completion.

## Recorded results

```json
[
  {
    "status": "not_evaluated",
    "reason": "候选为已有逐原子 NMRNet 加匹配，或 TransPeakNet H/C HSQC；需核验原子编号、等价位点和实验指认参考。"
  }
]
```

## Notebook

[Open the runnable notebook](../notebooks/nmr-assignment.ipynb)

## Source

[Original implementation / release](https://github.com/siriusxiao62/2dNMR)

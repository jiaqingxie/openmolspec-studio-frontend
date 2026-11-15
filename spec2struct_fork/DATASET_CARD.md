# H/C-NMR Dataset

`model_data/hc_nmr_v1/` was prepared from the complete
`data/raw/WanJuan_MolSpectra_v1_0_3.jsonl` file (472,114 patents; 19,787,346 compound
entries). Each JSONL row represents one compound with a canonical isomeric
SMILES, its RDKit molecular formula, and every nonempty recognized ¹H or ¹³C
NMR record. No mass spectra are used. `modality_mask` is `[has_H, has_C]`.

| Split | Examples |
| --- | ---: |
| Train | 9,967,326 |
| Validation | 1,154,280 |
| Test | 1,143,783 |
| **Total** | **12,265,389** |

There are 11,362,079 H-only examples, 32,814 C-only examples, and 870,496
with both modalities. Thus 12,232,575 examples contain H-NMR and 903,310
contain C-NMR. The files retain 12,382,173 H records and 914,389 C records;
one compound can have multiple records. The most frequent raw types are
`1H NMR` and `13C NMR`. DEPT-labelled records are included with C-NMR.

## Preparation and validation

The extractor discards entries without SMILES or recognized nonempty H/C-NMR,
SMILES that RDKit cannot parse, canonical SMILES longer than 160 bytes, and
characters outside the model's SMILES alphabet. It keeps source metadata and
raw spectrum type labels. A SHA-256 hash of the Bemis–Murcko scaffold assigns
train/validation/test at 80/10/10; acyclic compounds use canonical SMILES as
their grouping key. The observed proportions differ because grouping preserves
scaffold separation.

`verification.json` reports `status: passed`: all 12,265,389 rows were checked
for schema, modality masks, split assignment, and summary counts; 1,227
SMILES/formula pairs were spot-checked; each split has a SHA-256 digest.
The audit found 3,234 H records and 136 C records whose nonempty shift text
has no digit (0.026% and 0.015% of the respective record totals). These are
retained as source text but may carry little peak information. A few unusual
raw labels include 2D or decoupled NMR descriptions; review them before using
this corpus as a strict one-dimensional NMR benchmark.

Regenerate and audit with:

```bash
.venv/bin/python -m spec2struct.data --input data/raw/WanJuan_MolSpectra_v1_0_3.jsonl --output-dir model_data/hc_nmr_v1
.venv/bin/python -m spec2struct.verify --data-dir model_data/hc_nmr_v1
```

The preparation command refuses to overwrite an existing output directory.

## Molecule-unique training view

`model_data/hc_nmr_unique_v1/` has exactly one row per canonical isomeric
SMILES. Its 2,682,840 molecules come from all 12,265,389 source rows; 9,582,549
rows repeat a molecule already represented. Train/validation/test contain
2,176,296 / 251,199 / 255,345 unique molecules. The modality breakdown is
2,434,873 H-only, 9,369 C-only, and 238,598 H+C. Of the H+C molecules, 22,658
use selected H and C records from different patent sources.

For each molecule and modality, deduplication chooses the source row with the
most records containing digits, then the most shift text. It keeps all NMR
records **from those selected rows**, along with their provenance and the
number of source rows. Other measurements are still available in the full
`hc_nmr_v1` dataset; the unique view is a compact training representation.
Its own `verification.json` reports `passed` and checks strict SMILES order,
uniqueness, masks, splits, source-row totals, and file digests.

```bash
.venv/bin/python -m spec2struct.dedup \
  --source-dir model_data/hc_nmr_v1 \
  --output-dir model_data/hc_nmr_unique_v1
.venv/bin/python -m spec2struct.verify --data-dir model_data/hc_nmr_unique_v1
```

## Standard-InChI training view

`model_data/hc_nmr_inchi_v1/` is the recommended training dataset. It groups
the SMILES-unique candidates by RDKit standard InChI, including different
tautomeric SMILES that represent the same InChI. It has **2,680,271 unique
InChIs**: 2,174,218 train, 250,984 validation, and 255,069 test. There are
2,432,515 H-only, 9,344 C-only, and 238,412 H+C examples. An additional
2,070 SMILES rows collapsed into other InChI groups; 2,007 InChIs have more
than one source SMILES.

For each InChI, the lexicographically smallest source SMILES is the target.
The most informative H and C rows are selected separately; their original
SMILES and patent provenance are recorded. Splits are reassigned from the
representative structure's scaffold, so an InChI cannot appear in more than
one split. The full measurements remain in `hc_nmr_v1`.

Standard InChI could not be generated for 499 SMILES candidates, representing
893 original rows. Those rows are preserved in
`hc_nmr_inchi_v1/inchi_failures.jsonl` and excluded from the InChI-keyed
training view. `verification.json` reports `passed` after checking every row,
the failed-row counts, SMILES/InChI spot checks, and InChI uniqueness across
all three splits.

```bash
.venv/bin/python -m spec2struct.inchi_dedup \
  --source-dir model_data/hc_nmr_unique_v1 \
  --output-dir model_data/hc_nmr_inchi_v1
.venv/bin/python -m spec2struct.verify --data-dir model_data/hc_nmr_inchi_v1
```

# NMR training-history and evaluation overlap

The 2026-11-17 audit compared all 39,183 records in four prepared evaluation views against the available training/validation files associated with three NMR Transformer checkpoints. It found confirmed molecular overlap and one provenance discrepancy. Saved results remain available as functional and diagnostic evidence, not independent unseen-molecule benchmarks. This audit does not cover the separate NMRNet H/C or MS weights.

## Confirmed overlap

Both files in `mix_align_v2` match the hashes recorded by the retrieval checkpoint `f90bd7…` and the intermediate generator `aa2fea…`. The scan covers 3,608,853 training and 50,000 validation records. Counts below are unique evaluation identities present in each file; columns must not be added without checking their intersection.

| Evaluation view | Identities | In training | In validation |
| --- | ---: | ---: | ---: |
| `nmrspec_test` | 10,000 | 3,281 (32.81%) | 125 (1.25%) |
| `patent_test_10k` | 10,000 | 0 (0.00%) | 0 (0.00%) |
| `nmrexp_exp_10k` | 9,183 | 6,794 (73.98%) | 277 (3.02%) |
| `nmrgym_test` | 10,000 | 139 (1.39%) | 1 (0.01%) |

The final generator `bebaec…` records `aa2fea…` as its initialization checkpoint. Auditing only the final training stage would miss this earlier exposure. Zero exact identity overlap for the patent view in these two files is not proof of scaffold, source or complete training-history independence.

## Final generator: file fingerprint discrepancy

The run log names `data/g1_all`, but the checkpoint-recorded train digest matches `data/g1_ne/train.jsonl`, not the current `g1_all/train.jsonl`. The historical training code copied hashes from `verification.json` without recomputing file bytes. Therefore neither file is certified here as the exact historical input. The final validation file does match and has zero exact identity overlap with these four views.

- Checkpoint-recorded training-file SHA-256: `bd2aa8f2f11f127462927b368569521f8ec0d38952955ef19bfd73b590f7e165`
- Current `g1_all/train.jsonl` SHA-256: `d06c16ee1e21ba4e3d6fe7c5a8037211bedb05997bd4940646b15875f87cdfb7`

For reference, the current 2,121,498-record `g1_all` file overlaps the four evaluation views by 1,982 / 181 / 4,216 / 44 identities, respectively; 16 records lack stored InChI. These are current-file statistics, not verified historical training overlap. Both the SDK and the original training entry now verify file hashes before starting a new run. No historical weights, manifests or data were rewritten, and no training was performed.

## Identity scope and next benchmark

Matching uses stored standard-InChI strings, generating missing evaluation IDs with RDKit. It is a molecular-identity check, not a comparison of identical spectral records, scaffolds, all stereoisomers or patent families. Stored training IDs were not recomputed for every molecule. Independent benchmarks must exclude relevant training/validation identities across initialization stages, resolve the final-stage discrepancy and keep acquisition/source controls explicit. A 32-candidate retrieval score, even 100%, is not a substitute.

[Full audit JSON / 完整审计](assets/reports/nmr_checkpoint_overlap_20261117.json) · [Model review / 模型检查](model-audit.md) · [SDK](api.md)

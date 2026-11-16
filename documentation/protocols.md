# Evaluation protocols

All published figures use actual recorded results. Each evidence JSON carries source report hashes. Execution success is separate from scientific validity. Small candidate-pool results, prepared-data split labels and matched-peak errors must not be described as independent generalization or atom-assignment accuracy.

Complete IR/Raman/H/C input and missing-channel ablations are reported separately. Gap units are converted once from Hartree to eV. MS scores compare with all observed peaks under explicit acquisition conditions. No training or fitted calibration is performed.

[Dataset definitions](datasets.md) · [Model-by-model audit](model-audit.md)

**Evaluation limitation:** molecular overlap with checkpoint-recorded training data is confirmed for several NMR views. The final generator also has a training-file fingerprint discrepancy. These runs do not establish independent generalization.  [Training-history audit / 训练历史审计](training-overlap.md)

# Evaluation protocols

Every run records input/checkpoint hashes, sample IDs, modality conditions, candidate pools and execution states. F/P cached results whose logged targets disagree with current input labels are invalidated. Correct pairing is necessary but does not establish solid-to-solution reference compatibility.

The gap and Xinyu Vib2Mol checkpoints expect IR+Raman+H/C. Missing-channel variants are ablations, reported separately. Gap targets are converted from Hartree to eV once; stored H/C and target normalization is reused. Vib2Mol generation uses canonical unique valid beams and ITM positive-class reranking.

MS scores use real held-out CSV spectra and matched acquisition metadata. Missing collision energy/instrument is skipped without imputation. Small samples and unverified training overlap do not establish full-benchmark accuracy.

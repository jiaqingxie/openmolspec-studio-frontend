# FAQ

**Which input should I start with?** A known structure supports forward prediction and assignment. Spectral inputs support retrieval or generation. Relaxation/diffusion time traces use Inversion. See [Tasks](tasks/index.md).

**Can I load a measured IR peak list as a complete curve?** A sparse list does not contain measured continuous intensities. Keep its representation explicit and use an adapter designed for that input form.

**What does a zero or constant spectrum mean?** Inspect the source and processing map. Constant arrays cannot be min–max normalized by dividing by their range. The Data pages report them separately.

**Why are dataset counts different from the paper?** Counts may refer to spectra, compound records, unique identities or conformers; a local filtered view can also be smaller than the published source. Use the versioned count scope in each data card.

**Can I choose my own splits?** Yes. `split_records` exports a new random or scaffold-grouped dataset, with a manifest. Fixed benchmark views retain their original roles. See [Splits](data/splits.md).

**How do I fine-tune a model?** Each [task page](tasks/index.md) gives the objective and either an SDK training plan or the relevant author implementation. Data, labels and acquisition conditions must match that objective.

**Why do repeated response hashes differ when predictions agree?** Runtime metadata can refer to fresh temporary files. Spectra Harness records both response and prediction hashes.

**How are atom indices defined?** NMR assignment uses zero-based RDKit indices on the stated input graph, including explicit hydrogens when described. MAGMa uses its exported engine graph. Keep the graph and index convention with every result.

**What is required to reproduce a tutorial?** Install the package, tutorial dependencies and a licensed Arial font. Set `OPENMOLSPEC_ARIAL_FONT` to its TTF path when Arial is not installed. Model tutorials additionally require the documented author runtime and weights; theory simulations use NumPy/SciPy and Matplotlib.

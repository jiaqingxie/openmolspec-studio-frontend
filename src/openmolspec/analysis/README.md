# Analysis and figures

These scripts read generated manifests, reports or release catalogs and create
publication statistics and figures. They do not modify Gaussian source data.

| Script | Purpose |
|---|---|
| `analyze_dataset_comparison.py` | Build descriptor caches and compare OpenMolSpec with public datasets |
| `plot_openmolspec_overview.py` | Draw the main cross-dataset overview figure |
| `plot_dataset_statistics.py` | Draw supplementary scale/modality comparisons |
| `plot_element_coverage.py` | Compare documented element coverage |
| `plot_align_chemical_distribution.py` | Visualize the molecule-unique align chemical space and official scaffold split |
| `plot_align_overview.py` | Draw the combined 2x3 Align/conformation scale, coverage and composition figure |
| `visualize_opt_trajectory.py` | Render one optimization trajectory as an animated GIF |

Run scripts from the repository root. Generated publication figures belong in
`docs/figures/`; temporary analyses and large tables belong in `reports/`.

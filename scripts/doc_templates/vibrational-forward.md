## QM9S reference convention

On 337 validation structures, each channel was compared across normal-mode and openSpec intensities, frequency corrections and broadening widths. The following scores weight each of 303 other molecular connectivities equally. All 640 structures came from the OpenMolSpec reserved QM9 split. The reference uses the source Hessian and response derivatives at each molecule’s optimized geometry.

| Channel | Native → selected cosine | Paired 95% interval for cosine gain | Native → selected intensity MAE |
| --- | ---: | ---: | ---: |
| IR | 0.9621 → 0.9835 | [+0.0192, +0.0236] | 0.0100 → 0.0067 |
| Raman | 0.9125 → 0.9850 | [+0.0682, +0.0764] | 0.0198 → 0.0070 |

IR uses mode activities, a frequency multiplier of 0.9975 and Gaussian σ of 2 cm⁻¹. Raman uses mode activities, a frequency multiplier of 0.9975 and Gaussian σ of 2 cm⁻¹.

The QM9S profile returns 997 normalized intensities per channel on 500–4,000 cm⁻¹ for H/C/N/O/F molecules with up to nine heavy atoms. The computed reference uses a 0.965 harmonic frequency scale and 10 cm⁻¹ Lorentzian half-width. The Raman convention uses 532 nm at 298 K. Benchmarks used native QM9S coordinates. The website generates coordinates from the submitted SMILES. The original openSpec convention remains available for the 1,024-point grid.

[Predict online](https://jiaqingxie.github.io/openmolspec.github.io/#tool-ir-raman) · [Download paired benchmark and SDK](https://github.com/jiaqingxie/openmolspec-studio-frontend/releases/download/vibrational-forward-v2/openmolspec-qm9s.zip)

Unzip the download, install the wheel with NumPy and SciPy, then run this command inside the extracted directory. Adding `--qm9s-fresh --portable-root /path/to/openmolspec-studio-portable` recomputes the four networks on the archived coordinates using the installed model runtime and original weights.

```bash
python -m openmolspec_bench run --tasks vibrational.forward --qm9s-bundle benchmark --limit 10000 --output qm9s-result.json
```

The archive includes a transformed subset of QM9S by Zou et al., comprising the optimized coordinates, reconstructed reference spectra and OpenMolSpec predictions. [QM9S dataset](https://figshare.com/articles/dataset/QM9S_dataset/24235333) · [Underlying publication](https://doi.org/10.1038/s43588-023-00550-y) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

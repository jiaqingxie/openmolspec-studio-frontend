# Mass spectrometry

## Molecular mass, ions and adducts

A mass spectrometer measures ions. The observed coordinate is mass-to-charge ratio, $m/z$, rather than neutral molecular mass. Protonation, deprotonation, sodium adduction, charge state and electron mass conventions affect the mapping from a molecular formula to an ion. Exact monoisotopic mass, nominal mass and average molecular weight serve different purposes.

An isolated reported m/z can help constrain molecular identity. It does not contain the fragment intensities needed to train or evaluate an MS/MS spectrum predictor. [Data](../data/index.md) distinguishes these record forms.

## Isotope patterns and resolving power

Natural isotope abundances produce a distribution of ion masses. In a carbon-only illustration, the number of ¹³C atoms follows a binomial distribution. Real envelopes also depend on hydrogen, nitrogen, oxygen, sulfur, halogens and the ion composition. Resolving power is commonly expressed as $R=m/\Delta m$, with the width convention specified, often FWHM.

The [isotope tutorial](../notebooks/theory-ms-isotopes.ipynb) normalizes a carbon-only probability distribution and shows two resolving powers. It is a teaching simulation of an isotope envelope, not an experimental fragmentation spectrum.

## Tandem mass spectrometry

MS/MS selects a precursor and records product ions after activation. Fragmentation depends on molecular graph, charge localization, adduct, collision energy, instrument and acquisition mode. Relative intensities can change substantially across conditions. Numerical energy values from different instrument conventions are not automatically equivalent.

GLACIER and ICEBERG in OpenMolSpec require explicit acquisition inputs. MAGMa proposes mass-compatible fragments on a specified graph. A fragment mass match supports a candidate explanation; multiple pathways or isomers may remain possible.

## Comparing spectra

For vectors $x$ and $y$, cosine similarity is $(x\cdot y)/(\|x\|\|y\|)$. Peak tolerance or bin width, normalization, precursor removal, filtering and unassigned-peak handling all affect the result. Report these choices and the spectrum identities with every comparison. Evaluation should also respect molecule, acquisition and source partitions.

## Sources

- [MassSpecGym](https://huggingface.co/datasets/roman-bushuiev/MassSpecGym): versioned experimental MS/MS and benchmark definitions.
- [ms-pred](https://github.com/coleygroup/ms-pred): GLACIER/ICEBERG implementations and model training procedures.

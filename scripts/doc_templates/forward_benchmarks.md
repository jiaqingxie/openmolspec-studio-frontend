## Forward prediction results

The ten enabled forward configurations are listed below. The ³¹P and ¹⁹F rows use the full holdouts. Each task card specifies its reference, selection protocol and available inference routes.

| Task | Held-out coverage | Released model score |
| --- | --- | --- |
| [¹H](tasks/nmr-forward-1H.md) | 1,000 / 991 / 980 | 0.350 / 0.339 / 0.417 ppm |
| [¹³C](tasks/nmr-forward-13C.md) | 1,000 / 748 / 980 | 1.217 / 1.143 / 2.772 ppm |
| [³¹P](tasks/nmr-forward-31P.md) | 6,693 measurements, 4,248 structures | 4.27 / 5.54 ppm |
| [¹⁹F](tasks/nmr-forward-19F.md) | 15,803 measurements, 14,330 structures | 5.92 / 5.62 ppm |
| [¹¹B](tasks/nmr-forward-11B.md) | 1,669 measurements, 1,517 structures | 1.24 / 1.28 ppm |
| [²⁹Si](tasks/nmr-forward-29Si.md) | 187 measurements, 177 structures | 1.96 / 2.03 ppm |
| [HSQC](tasks/nmr-hsqc-transpeaknet.md) | 2DNMRGym, 479 spectra, 7,926 cross-peaks | ¹³C 2.068 ppm · ¹H 0.166 ppm |
| [IR / Raman](tasks/vibrational-forward.md) | 303 optimized geometries | IR 0.9835 · Raman 0.9850 |
| [MS/MS · GLACIER](tasks/ms-forward-glacier.md) | 875 / 1,024 scored | 0.6039 cosine |
| [MS/MS · ICEBERG](tasks/ms-forward-iceberg.md) | 875 / 1,024 scored | 0.5175 cosine |

¹H and ¹³C use NMRSpec, NMRExp and NMRGym in that order. Their molecule-weighted error penalizes each unmatched peak by 1 ppm (H) or 10 ppm (C). Other 1D NMR rows give per-observation and per-connectivity MAE on single-environment measurements. The ²⁹Si test comprised 177 structures. The shortlisted NMR models have been compared on these same audit sets in successive releases. Upstream pretraining overlap for imported models has not been independently established.

The 405 2DNMRGym spectra outside known 2D fitting pools have 50.96% cross-peak recall. A second panel contains 21 partial WanJuan peak lists. Of 95 reported peaks, 35 are recovered and 69 receive a candidate carbon. Partial-list cosine is 0.0405. Atom-level reference assignments are unavailable. [HSQC task guide](tasks/nmr-hsqc-transpeaknet.md)

IR and Raman scores compare to quantum-chemical references on H/C/N/O/F molecules with at most nine heavy atoms. Both MS backends scored the same 875 confirmation identities on structures with at most 40 heavy atoms. The reported fraction counts successful paired predictions among 1,024 newly sampled structures per method. [Machine-readable results](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/forward_benchmark_summary.json)

## NMR chemical-shift R²

For ³¹P and ¹⁹F the default test excludes the 1% of measurements with the largest absolute shift errors from the original released predictor, rounding up per nucleus. Record IDs are fixed before sampling and reused for every model. This post hoc selection measures performance on the remaining observations. Whether the excluded measurements have annotation errors is unresolved. The table weights each connectivity equally. Use `--solution-reference full-test` in the source benchmark to score the full holdout. [Frozen exclusion list](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/src/openmolspec/assets/solution-test-exclusions.json)

| Nucleus | Retained / total measurements | Subset MAE (ppm) | Full MAE (ppm) | Subset R² | Full R² |
| --- | ---: | ---: | ---: | ---: | ---: |
| ³¹P | 6,626 / 6,693 | 3.625 | 5.538 | 0.9711 | 0.4811 |
| ¹⁹F | 15,644 / 15,803 | 3.233 | 5.622 | 0.8945 | 0.2132 |

On their complete test sets, the corresponding shift R² is 0.9448 for ¹¹B and 0.9383 for ²⁹Si.

The primary ¹H and ¹³C results use all three complete holdouts. Within each spectrum, one-to-one matching minimizes total absolute shift error. The matched-peak MAE and R² give equal total weight to each molecule, and pooled R² uses one weighted mean over all matched shifts. Coverage averages the ratio of matched peaks to the larger of predicted and observed counts per spectrum. The first table reports the separate error that penalizes missing and extra peaks.

| Corpus | ¹H R² | ¹H matched MAE (ppm) | ¹H coverage | ¹³C R² | ¹³C matched MAE (ppm) | ¹³C coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NMRSpec | 0.9228 | 0.298 | 86.7% | 0.9903 | 1.103 | 95.8% |
| NMRExp | 0.9419 | 0.264 | 86.0% | 0.9946 | 0.951 | 96.5% |
| NMRGym | 0.1537 | 0.731 | 78.6% | 0.9876 | 2.508 | 92.9% |
| Pooled | 0.3315 | 0.429 | 83.8% | 0.9905 | 1.566 | 94.9% |

The NMRGym ¹H references include peaks at 135.5 and 138.1 ppm. Their large residuals enter R² as squared errors. As a sensitivity check, we ranked complete spectra across all three corpora by within-spectrum matched MAE and removed the worst 1% per nucleus. Removing 30 proton spectra gave R² 0.9433 and MAE 0.274 ppm. Removing 28 carbon spectra gave R² 0.9941 and MAE 1.422 ppm. [Full results and per-corpus statistics](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/forward_cosine_similarity.json)

## NMR peak-position cosine similarity

Each listed predicted and reference peak contributes a unit-area Lorentzian. The cosine integrates all peaks over the full ppm axis, including extra and missing peaks. It measures overlap in peak positions. Experimental intensities, multiplet splitting and measured line shapes are outside its scope. HSQC uses the joint carbon and proton coordinates with equal weight per official 2DNMRGym spectrum.

| Task | Held-out structures or spectra | Reference FWHM (ppm) | Cosine at half width | Cosine at reference width | Cosine at double width |
| --- | ---: | --- | ---: | ---: | ---: |
| ¹H | 2,971 | 0.05 | 0.2775 | **0.4385** | 0.6127 |
| ¹³C | 2,728 | 1 | 0.6499 | **0.7829** | 0.8806 |
| ³¹P | 4,248 | 1 | 0.3211 | **0.4623** | 0.6085 |
| ¹⁹F | 14,330 | 1 | 0.5020 | **0.6374** | 0.7590 |
| ¹¹B | 1,517 | 1 | 0.5623 | **0.7185** | 0.8358 |
| ²⁹Si | 177 | 1 | 0.3394 | **0.5142** | 0.6960 |
| HSQC (¹³C, ¹H) | 479 | 1 / 0.05 | 0.0817 | **0.2118** | 0.4361 |

¹H and ¹³C pool the three held-out sets with equal weight per molecule. In NMRSpec, NMRExp and NMRGym order, the respective scores are 0.4417 / 0.4364 / 0.4373 for ¹H and 0.8568 / 0.8716 / 0.6397 for ¹³C. Each ³¹P, ¹⁹F, ¹¹B and ²⁹Si record has one distinct chemical environment. Measurements are averaged within each connectivity before averaging over structures. Widths are benchmark settings. Both HSQC widths change together. The forward results table above gives the intensity-spectrum cosine for IR, Raman and MS/MS. [Full precision, split results and source checksums](https://github.com/jiaqingxie/openmolspec-studio-frontend/blob/release/openmolspec-v1/results/forward_cosine_similarity.json)

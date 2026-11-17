# OpenMolSpec

<div class="oms-eyebrow">Chemical spectroscopy · Open research platform</div>

<p class="oms-lead"><strong>Datasets, models and reproducible spectroscopy</strong><br>Load molecular spectra, predict observables, retrieve or generate structures, and train NMR models through a common Python interface.</p>

<div class="oms-stat-grid">
<div class="oms-stat"><strong>7</strong><span>dataset registry entries</span></div>
<div class="oms-stat"><strong>31</strong><span>active task configurations</span></div>
<div class="oms-stat"><strong>74</strong><span>executed bilingual notebooks</span></div>
</div>

<div class="oms-paths">
<a class="oms-path" href="datasets.html"><strong>Use the data →</strong><span>Understand sources, distributions, split roles and loading APIs.</span></a>
<a class="oms-path" href="tasks/index.html"><strong>Choose a task →</strong><span>Start from your input: a structure, NMR peaks, MS/MS, IR or Raman.</span></a>
<a class="oms-path" href="api.html"><strong>Predict and train →</strong><span>Use model classes, inspect real examples and prepare training data.</span></a>
</div>

## See an actual result

The geometry-to-spectrum example uses Xinyu’s openSpec models and the exact coordinates of its Gaussian reference. The two curves show the recorded prediction and calculation. This figure shows one of two examples; it establishes a working inference path, not a large independent benchmark.

[![IR and Raman: recorded prediction and reference](assets/gallery/vibrational-forward.png)](tasks/vibrational-forward.md)

[Explore all result figures](gallery.md) · [Open this task](tasks/vibrational-forward.md) · [Read the executed notebook](notebooks/vibrational-forward.ipynb)

## Start with the Python package

Install the versioned wheel using the [SDK guide](api.md), then inspect the dataset registry. Loading full data and running model weights require the assets described there.

```python
from openmolspec.dataset import list_datasets

for card in list_datasets():
    print(card["name"])
```

[Quick Start](quickstart.md) · [Python SDK](api.md) · [Executed notebooks](notebooks/index.md)

## What the data represent

| Collection | Meaning | Where to inspect |
| --- | --- | --- |
| Team-curated experimental NMR | Patent-derived measurements; 2,680,271 stored standard-InChI identities in the current prepared corpus. Curation does not mean we measured these spectra. | [Sources and counts](datasets.md) |
| Computed observables | Calculated IR/Raman and associated molecular properties. Molecular records and geometry frames are counted separately. | [Distributions](datasets.md) |
| External benchmarks | NMRSpec, NMRexp, NMRGym and MS resources retain their own provenance and attribution. | [Data comparison](corpus-comparison.md) |

Dataset counts use different units and can overlap. The registry is an access layer, not seven newly measured datasets.

## Assess a model before using it

H/C NMR, MS/MS and vibrational examples contain actual outputs. B/Si and F/P are diagnostic; cross-solvent transfer is currently an experimental-reference baseline. The training API has completed an encoder/generator train–save–reload integration check on tiny examples; large-scale learning claims require separate experiments.

[Model suitability](model-audit.md) · [Evaluation protocols](protocols.md) · [Training overlap](training-overlap.md) · [Publication status](publication.md)

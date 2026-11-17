# Spectra Harness

Spectra Harness uses one task registry and request contract across Python, a command line and MCP. Its replaceable family plugins are inspired by [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). It runs existing spectroscopy backends and records their behavior.

| Plugin | Direct calls |
| --- | --- |
| NMR Spectra Harness | H/C forward prediction, assignment, spectrum-to-structure retrieval and formula-conditioned generation |
| MS Spectra Harness | GLACIER and ICEBERG under explicit acquisition conditions |
| Vibrational Spectra Harness | Gap prediction, Vib2Mol retrieval, generation and candidate reranking |

The full task list also contains benchmark and algorithmic adapters. `catalog()` lists direct Harness capabilities explicitly; the [task pages](tasks/index.md) provide the other entry points.

## Python

```python
from openmolspec.harness import SpectraHarness

harness = SpectraHarness()
print(harness.catalog())
inputs = {'smiles': 'CCO'}
settings = {'root': '/path/to/models', 'python': '/path/to/nmr-env/bin/python'}
print(harness.validate('nmr.forward.13C', inputs, settings))
report = harness.run('nmr.forward.13C', inputs, settings, repeats=2)
print(report['completed'], report['repeat_predictions_equal'])
prediction = report['result']
```

Each call records elapsed time, success/failure and response/prediction hashes. Full responses can contain changing temporary-file provenance; prediction equality is therefore reported separately. Numerical agreement or successful execution does not measure accuracy without reference labels and a suitable evaluation protocol.

## Command line

Create a JSON object with `task`, `inputs`, `model_config` and optional `repeats`:

```bash
python -m openmolspec.harness catalog
python -m openmolspec.harness validate --request request.json
python -m openmolspec.harness run --request request.json --output new-result.json
```

## MCP

Install the optional `mcp` extra and configure the client with your environment’s Python:

```json
{
  "mcpServers": {
    "openmolspec": {
      "command": "/path/to/environment/bin/python",
      "args": ["-m", "openmolspec.mcp"]
    }
  }
}
```

The server uses stdio and exposes `spectra_tasks`, `spectra_datasets`, `spectra_validate` and `spectra_predict`. MCP parameters use `model_settings` for model/runtime paths. Validation returns an explanatory error for incompatible inputs before launching a model. Model dependencies and weights must exist in the selected backend environment.

The repository includes a [Spectra Harness skill](https://github.com/jiaqingxie/openmolspec-studio-frontend/tree/release/openmolspec-v1/skills/spectra-harness) for agent use. Training remains an explicit SDK operation with a separate training plan, train/validation inputs and a new output directory. See [Models and training](model-audit.md).

## Recorded execution

[Repeated NMR/MS/vibrational calls](assets/reports/spectra_harness_stability_20261117.json) · [MCP protocol](assets/reports/spectra_mcp_protocol_20261117.json) · [MCP real NMR inference](assets/reports/spectra_mcp_real_call_20261117.json)

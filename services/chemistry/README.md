# Chemistry service

Run one chemistry process from the repository root:

```sh
.venv/bin/python -m uvicorn services.chemistry.app:app --host 127.0.0.1 --port 8001
```

Model discovery uses the existing `OPENMOLSPEC_ROOT` and `OPENMOLSPEC_DEVICE` settings. Startup and molecular editing work without checkpoints; calculations expose actual asset availability and fail explicitly when assets are missing. The model facade is created lazily inside one serialized worker. Deploy with one Uvicorn worker.

`OPENMOLSPEC_DATABASE_URL` must point to the same PostgreSQL database used by the application API. Startup initializes and checks the version of the `molspec_chemistry` schema. Molecules, spectra, immutable job inputs, and idempotency records belong to the authenticated account. Use a fresh database for this release.

A restart resumes queued jobs and marks previously running jobs failed with code `interrupted`. Queued jobs can be cancelled. Cancelling a running native calculation returns HTTP 409 with `job_running` because the model call cannot be safely interrupted. Job creation reserves credits in the same transaction, successful jobs settle the reservation, and cancellation, failure, or restart interruption releases it. MCP immediately returns a job ID and `get_calculation` polls its status. HTTP and MCP can share an optional `request_id`. Within one account, reusing a key with the same operation and inputs returns the original job, including after restart. Changing the operation or inputs returns `request_id_conflict`.

Keep the chemistry port on the private network. The application forwards the trusted owner as `X-Molspec-User-ID` and authenticates each private HTTP or MCP request with `X-Molspec-Internal-Key`, which must match `OPENMOLSPEC_INTERNAL_KEY` on both services. It supplies `X-Molspec-Source` as `web` or `mcp` for usage reporting. External clients use the application API's authenticated MCP endpoint. The launcher can check `GET /health` without credentials. The application can check `GET /v1/capabilities` with just the private key.

The official MCP SDK serves stateless Streamable HTTP at the exact `/mcp` URL with DNS rebinding protection. Allowed Host values include IPv4 and IPv6 loopback, `localhost`, and the container service name `chemistry`, with or without a port. Add trusted service or proxy hosts in the comma-separated `OPENMOLSPEC_MCP_ALLOWED_HOSTS` setting. An entry ending in `:*` permits that hostname at any port. Browser MCP requests still require an allowed loopback Origin.

HTTP and MCP use the same validation, input storage, numerical facade, and durable jobs. Uploaded spectra retain original measurements, declared units, and processing history. Eligible spectra declare a theoretical domain and relative intensity, and either cover the full 400–4000 cm⁻¹ grid or explicitly supply its 1024 points as one intensity column. The service interpolates within coverage. Wavelength, experimental, unknown-unit, partial, flat, and legacy spectra remain previewable. `inspect_spectrum` returns a compact record of units, range, eligibility and provenance. A successful forward calculation atomically publishes its IR and Raman IDs for later calculations. Molecular eligibility checks basic structure and a conservative organic element scope. It does not establish model accuracy for a particular molecule.

The upstream checkout under `OPENMOLSPEC_ROOT` supplies production model code and assets. Forward prediction needs the Equiformer Hessian and NMR modules, the Hessian assembler, Hi/Hij/dipole/polarizability checkpoints and each tensor checkpoint's run-level `resolved_config.yaml`, plus an H/C NMR checkpoint. The gap operation needs Vib2Conf code and its gap checkpoint. Retrieval uses the theoretical test-set LMDB. Cached generation also uses `generation_predictions.jsonl`. Direct Vib2Mol needs its upstream implementation and tokenizer, generation weights and NMR normalizer. Asset discovery is defined in `openmolspec_ui/config.py`.

Verify service behavior, real inference adapters using reference-data fixtures, restart recovery, cancellation, and official MCP over a live loopback server:

```sh
OPENMOLSPEC_TEST_DATABASE_URL="$TEST_POSTGRES_ADMIN_DSN" \
  .venv/bin/python -m pytest tests/services/test_chemistry_service.py -q
```

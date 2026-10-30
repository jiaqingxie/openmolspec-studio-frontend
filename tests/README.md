# Tests

Tests are organized as lightweight regression tests for the staged pipeline.

```text
tests/
├── fixtures/              deterministic small input files
├── test_schema.py         v1 schema contract
├── test_processing.py     processing reports and parser failures
├── test_extract_labels.py manifest and modality matching
├── test_pipeline.py       manifest/extraction stages
├── test_internal_validation.py
└── test_dedup_splits.py
```

Run all tests with:

```bash
python -m unittest discover -s tests -v
```

Generated reports, caches, notebook checkpoints and large local reference
artifacts are ignored by `.gitignore`. Small deterministic fixtures under
`tests/fixtures/` are intentionally kept versionable.


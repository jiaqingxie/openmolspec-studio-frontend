import unittest

from openmolspec.core.schema import (
    OPEN_SPEC_V1_SCHEMA,
    REQUIRED_FIELDS,
    SCHEMA_METADATA,
    schema_as_dict,
    validate_record_keys,
)


class SchemaTest(unittest.TestCase):
    def test_schema_metadata(self):
        self.assertEqual(SCHEMA_METADATA["schema_version"], "1.0")
        self.assertEqual(SCHEMA_METADATA["field_count"], len(OPEN_SPEC_V1_SCHEMA))

    def test_required_fields(self):
        self.assertEqual(
            set(REQUIRED_FIELDS),
            {
                "sample_id",
                "source_dataset",
                "source_id",
                "atomic_numbers",
                "parser_version",
                "processing_version",
            },
        )

    def test_every_field_has_contract(self):
        for spec in OPEN_SPEC_V1_SCHEMA.values():
            self.assertTrue(spec.dtype)
            self.assertTrue(spec.shape)
            self.assertTrue(spec.missing_value_policy)
            self.assertTrue(spec.description)

    def test_required_key_validation(self):
        missing = validate_record_keys({"sample_id": "NISTIR-1"})
        self.assertIn("source_dataset", missing)
        self.assertIn("processing_version", missing)

    def test_schema_is_serializable(self):
        serialized = schema_as_dict()
        self.assertEqual(serialized["schema"]["schema_version"], "1.0")
        self.assertIn("raman_spectrum", serialized["fields"])


if __name__ == "__main__":
    unittest.main()


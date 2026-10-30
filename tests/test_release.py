import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openmolspec.release.catalog import build_catalog
from openmolspec.release.export import export_pickle, index_payload, read_array_row
from openmolspec.release.splits import build_splits
from openmolspec.release.validation import validate_release


class ReleasePipelineTest(unittest.TestCase):
    def _fixture(self, root: Path):
        sample_ids = ["A-1", "B-1", "C-1", "D-1", "E-1", "A-duplicate"]
        keys = ["KEYA-AAAA", "KEYB-BBBB", "KEYC-CCCC", "KEYD-DDDD", "KEYE-EEEE", "KEYA-AAAA"]
        manifest = pd.DataFrame({
            "sample_id": sample_ids,
            "source_dataset": ["A", "B", "C", "D", "E", "A"],
            "source_id": ["1", "1", "1", "1", "1", "duplicate"],
            "smiles": ["C", "CC", "CCC", "CCCC", "CCCCC", "C"],
            "canonical_smiles": ["C", "CC", "CCC", "CCCC", "CCCCC", "C"],
            "inchikey": keys,
            "scaffold": ["sA", "sB", "sC", "sD", "sE", "sA"],
            "label_status": ["matched"] * 6,
            "available_modalities": [["frequency", "nmr"]] * 6,
            "frequency_file_hash": ["f"] * 6,
            "nmr_file_hash": ["n"] * 6,
        })
        manifest.to_parquet(root / "manifest.parquet", index=False)
        frequency = pd.DataFrame({
            "sample_id": sample_ids,
            "status": ["success"] * 5 + ["failed"],
            "error_type": [None] * 5 + ["FREQUENCY_PARSE_FAILED"],
            "missing_fields": [[] for _ in sample_ids],
            "quality_flags": [[] for _ in sample_ids],
        })
        frequency.to_parquet(root / "frequency.parquet", index=False)
        nmr = pd.DataFrame({
            "sample_id": sample_ids,
            "status": ["success", "success", "success", "success", "failed", "success"],
            "error_type": [None, None, None, None, "NMR_PARSE_FAILED", None],
            "missing_fields": [[] for _ in sample_ids],
            "quality_flags": [[] for _ in sample_ids],
        })
        nmr.to_parquet(root / "nmr.parquet", index=False)
        config = {
            "_config_path": str(root / "configs" / "release.yaml"),
            "release": {
                "release_id": "test-v1", "dataset_version": "1.0.0",
                "output_dir": str(root / "release"),
                "splits": {"seed": 7, "validation_count": 1, "test_count": 1},
            },
            "inputs": {
                "manifest": str(root / "manifest.parquet"),
                "frequency_report": str(root / "frequency.parquet"),
                "nmr_report": str(root / "nmr.parquet"),
            },
        }
        return config

    def test_catalog_split_and_release_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._fixture(Path(directory))
            catalog = build_catalog(config)
            self.assertEqual(catalog["full_unique_molecules"], 5)
            self.assertEqual(catalog["align_unique_molecules"], 4)
            split = build_splits(config)
            self.assertEqual(split["align_counts"]["validation"], 1)
            self.assertEqual(split["align_counts"]["test"], 1)
            self.assertEqual(split["identity_and_scaffold_overlap_total"], 0)
            align_split = pd.read_parquet(
                Path(config["release"]["output_dir"]) / "splits" / "align_split.parquet"
            )
            for field in ("inchikey", "split_scaffold"):
                train = set(align_split.loc[align_split["split"].eq("train"), field])
                heldout = set(align_split.loc[align_split["split"].ne("train"), field])
                self.assertFalse(train & heldout)
            result = validate_release(config)
            self.assertTrue(result["release_gate_pass"])

    def test_hdf5_shard_roundtrip_and_raman_float64(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame = pd.DataFrame({
                "sample_id": ["A-1", "A-2"],
                "atom": [np.array([6, 1]), np.array([8, 1, 1])],
                "coordinate": [np.zeros((2, 3)), np.ones((3, 3))],
                "raman": [np.array([1, 2], dtype=np.float32), np.array([3, 4], dtype=np.float32)],
                "energy": [-1.0, -2.0],
            })
            source = root / "data.pickle"
            frame.to_pickle(source)
            result = export_pickle(source, root / "export", kind="frequency", shard_size=1, workers=2)
            self.assertEqual(result["shard_count"], 2)
            arrays = root / "export" / "shard-00000.h5"
            np.testing.assert_array_equal(read_array_row(arrays, "atomic_numbers", 0), [6, 1])
            self.assertEqual(read_array_row(arrays, "raman_spectrum", 0).dtype, np.float64)

    def test_payload_index_is_streamed_from_shard_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame = pd.DataFrame({
                "sample_id": ["A-1", "A-2", "A-3"],
                "atom": [np.array([6]), np.array([7]), np.array([8])],
            })
            source = root / "data.pickle"
            frame.to_pickle(source)
            payload = root / "release" / "payload" / "frequency"
            export_pickle(source, payload, kind="frequency", shard_size=2)
            catalog = root / "release" / "catalog"
            catalog.mkdir(parents=True)
            pd.DataFrame({
                "sample_id": ["A-1", "A-2", "A-3"],
                "source_dataset": ["A", "A", "A"],
                "source_id": ["1", "2", "3"],
                "molecule_id": ["M1", "M2", "M3"],
            }).to_parquet(catalog / "records.parquet", index=False)
            config = {
                "_config_path": str(root / "configs" / "release.yaml"),
                "release": {"output_dir": str(root / "release")},
            }
            result = index_payload(config)
            self.assertEqual(result["total_records"], 3)
            index = pd.read_parquet(payload / "index.parquet")
            self.assertEqual(len(index), 3)
            self.assertEqual(set(index["source_dataset"]), {"A"})


if __name__ == "__main__":
    unittest.main()

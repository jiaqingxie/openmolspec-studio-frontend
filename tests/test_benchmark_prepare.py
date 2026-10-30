import pickle
import tempfile
import unittest
from pathlib import Path

import lmdb
import numpy as np
import pandas as pd

from benchmarks.data import prepare


def _synthetic_frame(n=60):
    rows = []
    for index in range(n):
        n_atoms = 6 + (index % 4)
        rows.append(
            {
                "sample_id": f"QM9-{index}",
                "smiles": "CCO",
                "atom": np.arange(n_atoms, dtype=np.int32) + 1,
                "coordinate": np.random.RandomState(index).randn(n_atoms * 3).astype(np.float32),
                "ir": np.random.RandomState(index).rand(1024).astype(np.float32),
                "raman": np.random.RandomState(index).rand(1024).astype(np.float32),
                "energy": np.float32(-10.0 - index),
                "gap": np.float64(0.1 + index / 100),
                "homo": np.float64(-0.2),
                "lumo": np.float64(-0.05),
                "dipole_total": np.float64(1.0 + index / 10),
                "zpve": np.float32(0.1),
            }
        )
    return pd.DataFrame(rows)


class BenchmarkPrepareTest(unittest.TestCase):
    def test_formal_prepare_requires_split_before_loading_data(self):
        with self.assertRaisesRegex(ValueError, "requires --split-file"):
            prepare.run(
                pickle_path="does-not-exist.pickle",
                manifest_path="does-not-exist.parquet",
                record_qc_path="does-not-exist-qc.parquet",
                split_path=None,
                output="unused",
                seed=2025,
                workers=1,
            )

    def test_load_official_split_uses_aligned_sample_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "align_split.parquet"
            pd.DataFrame(
                {
                    "align_sample_id": ["QM9-1", "ZINCV2-2"],
                    "align_source": ["QM9", "ZINCV2"],
                    "inchikey": ["KEY1", "KEY2"],
                    "split_scaffold": ["c1ccccc1", "C1CCCCC1"],
                    "split": ["validation", "test"],
                }
            ).to_parquet(path, index=False)

            result = prepare.load_official_split(str(path))

            self.assertEqual(result["sample_id"].tolist(), ["QM9-1", "ZINCV2-2"])
            self.assertEqual(result["source_dataset"].tolist(), ["QM9", "ZINCV2"])
            self.assertIn("split_scaffold", result.columns)

    def test_stable_molecule_sample_is_reproducible_and_grouped(self):
        identity = pd.DataFrame(
            {
                "sample_id": [f"sample-{index}" for index in range(30)],
                "inchikey": [f"KEY{index // 3}" for index in range(30)],
            }
        )
        first = prepare.stable_molecule_sample(identity, sample_size=10, seed=2025)
        shuffled = identity.sample(frac=1.0, random_state=7).reset_index(drop=True)
        second = prepare.stable_molecule_sample(shuffled, sample_size=10, seed=2025)
        self.assertEqual(set(first["sample_id"]), set(second["sample_id"]))
        self.assertGreaterEqual(len(first), 10)
        for key in first["inchikey"].unique():
            self.assertEqual(
                set(first.loc[first["inchikey"] == key, "sample_id"]),
                set(identity.loc[identity["inchikey"] == key, "sample_id"]),
            )

    def test_build_split_index_no_leakage(self):
        identity = pd.DataFrame(
            {
                "sample_id": [f"QM9-{index}" for index in range(60)],
                "inchikey": [f"KEY{index // 3}" for index in range(60)],
            }
        )
        result = prepare.build_split_index(identity, seed=2025)
        train = set(result.loc[result["split"] == "train", "inchikey"])
        test = set(result.loc[result["split"] == "test", "inchikey"])
        validation = set(result.loc[result["split"] == "validation", "inchikey"])
        self.assertEqual(train & test, set())
        self.assertEqual(train & validation, set())
        self.assertEqual(test & validation, set())
        counts = result["split"].value_counts()
        self.assertAlmostEqual(counts["train"] / len(result), 0.8, delta=0.05)

    def test_kekule_smiles(self):
        values = prepare.kekule_smiles_parallel(["CCO", "c1ccccc1", "C(=O)O"], workers=2)
        self.assertEqual(len(values), 3)
        self.assertIsNotNone(values[0])
        self.assertIn("C", values[2])

    def test_exporters_write_valid_lmdb(self):
        frame = _synthetic_frame(60)
        frame["sample_id"] = frame["sample_id"].astype(str)
        identity = pd.DataFrame(
            {
                "sample_id": frame["sample_id"],
                "inchikey": [f"KEY{index // 3}" for index in range(60)],
                "source_dataset": ["QM9"] * 60,
            }
        )
        split_map = prepare.build_split_index(identity, seed=2025)
        split_map["split"] = split_map["split"].replace({"validation": "eval"})

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            counts_vib2mol = prepare.export_vib2mol(frame, output, split_map, workers=2)
            counts_vib2conf = prepare.export_vib2conf(frame, output, split_map)
            counts_equiformer = prepare.export_equiformer_v3(frame, output, split_map)
            self.assertEqual(counts_vib2mol["train"], 48)
            self.assertEqual(counts_vib2conf["test"], 6)
            self.assertEqual(counts_equiformer["eval"], 6)

            # vib2mol record content
            env = lmdb.open(str(output / "vib2mol" / "openspec_train.lmdb"), readonly=True, subdir=False, lock=False)
            with env.begin() as transaction:
                cursor = transaction.cursor()
                cursor.first()
                record = pickle.loads(cursor.value())
            self.assertIn("ir", record)
            self.assertIn("raman", record)
            self.assertIn("kekule_smiles", record)
            self.assertIn("formula", record)
            self.assertTrue(record["formula"])
            self.assertEqual(record["ir"].shape, (1024,))
            env.close()

            # vib2conf record content
            env = lmdb.open(str(output / "vib2conf" / "train.lmdb"), readonly=True, subdir=False, lock=False)
            with env.begin() as transaction:
                cursor = transaction.cursor()
                cursor.first()
                record = pickle.loads(cursor.value())
            self.assertIn("pos", record)
            self.assertIn("z", record)
            self.assertEqual(record["pos"].shape[1], 3)
            self.assertEqual(record["pos"].shape[0], len(record["z"]))
            env.close()

            # equiformer record content
            env = lmdb.open(str(output / "equiformer_v3" / "train.lmdb"), readonly=True, subdir=False, lock=False)
            with env.begin() as transaction:
                cursor = transaction.cursor()
                cursor.first()
                data = pickle.loads(cursor.value())
            self.assertEqual(tuple(data.pos.shape), (data.atomic_numbers.numel(), 3))
            self.assertEqual(data.natoms.tolist(), [data.pos.shape[0]])
            self.assertTrue(hasattr(data, "energy"))
            env.close()

    def test_lmdb_writer_refuses_stale_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.lmdb"
            prepare._write_lmdb(path, ((str(index), {"value": index}) for index in range(3)))
            with self.assertRaises(FileExistsError):
                prepare._write_lmdb(path, [("new", {"value": 4})])
            count = prepare._write_lmdb(
                path, [("new", {"value": 4})], overwrite=True
            )
            self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()

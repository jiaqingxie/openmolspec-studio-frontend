import tempfile
import unittest
from pathlib import Path

import lmdb
import pandas as pd

from benchmarks.data.subset_vib2mol import run
from benchmarks.trainers.experiment import load_config


class SubsetVib2MolTests(unittest.TestCase):
    def test_copy_and_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "vib2mol").mkdir(parents=True)
            index = pd.DataFrame({"sample_id": ["a", "b", "v", "t"],
                                  "split": ["train", "train", "eval", "test"]})
            index.to_parquet(source / "benchmark_split.parquet")
            (source / "normalization.json").write_text('{"method": "minmax"}')
            for mode in ("train", "eval", "test"):
                with lmdb.open(str(source / "vib2mol" / f"openspec_{mode}.lmdb"),
                               subdir=False, map_size=1 << 20) as env:
                    with env.begin(write=True) as txn:
                        for key in index.loc[index.split == mode, "sample_id"]:
                            txn.put(key.encode(), b"unaltered-" + key.encode())
            selected = index[index.sample_id != "b"].rename(
                columns={"sample_id": "align_sample_id"})
            selected["split"] = selected.split.replace({"eval": "validation"})
            split = root / "split.parquet"
            selected.to_parquet(split)
            output = root / "output"
            summary = run(source, split, output)
            self.assertEqual(summary["state"], "completed")
            self.assertEqual(summary["splits"], {"train": 1, "eval": 1, "test": 1})
            for mode, key in (("train", b"a"), ("eval", b"v"), ("test", b"t")):
                with lmdb.open(str(output / "vib2mol" / f"openspec_{mode}.lmdb"),
                               subdir=False, readonly=True, lock=False) as env:
                    with env.begin() as txn:
                        self.assertEqual(list(txn.cursor()), [(key, b"unaltered-" + key)])
            with self.assertRaises(FileExistsError):
                run(source, split, output)
            selected[selected.split != "test"].to_parquet(split)
            with self.assertRaises(ValueError):
                run(source, split, root / "bad")
            self.assertFalse((root / "bad").exists())
            selected.loc[selected.align_sample_id == "a", "align_sample_id"] = "missing"
            selected.to_parquet(split)
            with self.assertRaises(ValueError):
                run(source, split, root / "missing")

    def test_scaling_configs(self):
        root = Path(__file__).resolve().parents[1]
        for size in (200, 1000):
            config = load_config(root / "benchmarks/configs/spectrum2structure" /
                                 f"vib2mol_ks{size}k.yaml")
            self.assertEqual(config["training"]["max_steps"], 312500)
            self.assertEqual(config["training"]["generation_max_steps"], 312500)
            self.assertEqual(config["training"]["gpus"], 4)
            self.assertEqual(config["training"]["batch_size"], 64)
            self.assertEqual(config["training"]["generation_batch_size"], 64)


if __name__ == "__main__":
    unittest.main()

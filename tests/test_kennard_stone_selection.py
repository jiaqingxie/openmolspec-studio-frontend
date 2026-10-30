import unittest

import numpy as np
import pandas as pd

from benchmarks.data.plot_kennard_stone import (
    kennard_stone_order,
    nested_kennard_stone_rank,
)
from benchmarks.data.select_kennard_stone import build_scaling_split


class KennardStoneSelectionTest(unittest.TestCase):
    def test_kennard_stone_starts_at_feature_space_extreme(self):
        features = np.asarray([[0.0], [1.0], [2.0], [10.0]], dtype=np.float32)
        order = kennard_stone_order(features, np.arange(4, dtype=np.uint64))
        self.assertEqual(order[0], 3)
        self.assertEqual(set(order[:2]), {0, 3})

    def test_nested_rank_is_complete_deterministic_and_scaffold_diverse(self):
        count = 120
        frame = pd.DataFrame(
            {
                "inchikey": [f"KEY-{index:04d}" for index in range(count)],
                "split_scaffold": [f"SCAFFOLD-{index % 30:02d}" for index in range(count)],
                "align_source": ["A" if index % 3 else "B" for index in range(count)],
            }
        )
        rng = np.random.default_rng(7)
        features = rng.normal(size=(count, 16)).astype(np.float32)
        features[:, 0] = np.linspace(80, 500, count)
        features[:, 1] = np.arange(count) % 35
        features[:, 2] = np.arange(count) % 8
        features[:, 3] = np.arange(count) % 5
        features[:, 5] = 0
        first = nested_kennard_stone_rank(
            frame, features, seed=2025, target_group_size=12
        )
        second = nested_kennard_stone_rank(
            frame.sample(frac=1.0, random_state=9).reset_index(drop=True),
            features[frame.sample(frac=1.0, random_state=9).index],
            seed=2025,
            target_group_size=12,
        )
        self.assertEqual(set(first), set(range(1, count + 1)))
        first_map = dict(zip(frame["inchikey"], first))
        shuffled = frame.sample(frac=1.0, random_state=9)
        second_map = dict(zip(shuffled["inchikey"], second))
        self.assertEqual(first_map, second_map)
        selected_20 = set(frame.loc[first <= 20, "inchikey"])
        selected_40 = set(frame.loc[first <= 40, "inchikey"])
        self.assertTrue(selected_20 < selected_40)

    def test_scaling_split_keeps_heldout_rows_and_exact_train_size(self):
        original = pd.DataFrame(
            {
                "align_sample_id": [f"sample-{index}" for index in range(14)],
                "inchikey": [f"key-{index}" for index in range(14)],
                "canonical_smiles": ["CC"] * 14,
                "align_source": ["A"] * 14,
                "split_scaffold": [f"scaffold-{index}" for index in range(14)],
                "split": ["train"] * 10 + ["validation"] * 2 + ["test"] * 2,
            }
        )
        rank = original.iloc[:10][
            ["align_sample_id", "inchikey", "align_source", "split_scaffold"]
        ].copy()
        rank["ks_rank"] = np.arange(1, 11, dtype=np.int32)
        result = build_scaling_split(original, rank, 6)
        self.assertEqual(result["split"].value_counts().to_dict(), {
            "train": 6, "validation": 2, "test": 2,
        })
        self.assertEqual(result.loc[result["split"].eq("train"), "ks_rank"].tolist(), list(range(1, 7)))
        self.assertEqual(
            set(result.loc[result["split"].ne("train"), "align_sample_id"]),
            {"sample-10", "sample-11", "sample-12", "sample-13"},
        )


if __name__ == "__main__":
    unittest.main()

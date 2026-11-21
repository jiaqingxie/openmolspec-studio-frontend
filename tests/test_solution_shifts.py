"""Regression tests for the molecule split and mapping between input atoms and peaks."""

import gzip
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


from openmolspec.solution_shifts import SolutionShiftPredictor, analyte, site_features


class SolutionShiftTests(unittest.TestCase):
    def test_counterion_does_not_renumber_input_atoms(self):
        model = SolutionShiftPredictor.__new__(SolutionShiftPredictor)
        model.nucleus = "31P"
        model.booster = Mock()
        model.booster.predict.return_value = [3.5]
        model.tables = [{} for _ in range(6)]
        model.config = {"environment_weight": 0}
        result = model.predict("[Na+].[O-]P(O)(O)=O")
        self.assertEqual(result["atom_indices"], [2])
        self.assertEqual(
            result["environments"], [{"atom_indices": [2], "prediction_ppm": 3.5}]
        )

    def test_equivalent_fluorines_share_one_site(self):
        mol, _ = analyte("FC(F)(F)c1ccc(F)cc1", "19F")
        sites = site_features(mol, "19F")
        self.assertEqual(sorted(len(group) for group, _, _ in sites), [1, 3])
        reverse, _ = analyte("Fc1ccc(C(F)(F)F)cc1", "19F")
        self.assertEqual(
            sorted((codes, features) for _, codes, features in sites),
            sorted(
                (codes, features)
                for _, codes, features in site_features(reverse, "19F")
            ),
        )

    def test_no_labels_are_assigned_across_target_bearing_components(self):
        with self.assertRaisesRegex(ValueError, "multiple_target_components"):
            analyte("FC.CCF", "19F")

    def test_test_and_pool_priority_across_sources_and_smiles(self):
        groups = [
            ("a", "train"),
            ("b", "test"),
            ("a", "val"),
            ("b", ""),
            ("a", "pool"),
            ("c", "train"),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prepared.jsonl.gz"
            with gzip.open(path, "wt") as stream:
                for key, role in groups:
                    stream.write(
                        json.dumps([key, "", "", [], [["source", role, 0, [0], None]]])
                        + "\n"
                    )
            partition = runpy.run_path(
                str(
                    Path(__file__).resolve().parents[1]
                    / "scripts/train_solution_shifts.py"
                )
            )["partition"]
            self.assertEqual(partition(path), {"a": "pool", "b": "test", "c": "train"})

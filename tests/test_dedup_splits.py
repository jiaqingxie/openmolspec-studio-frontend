import unittest

import pandas as pd

from openmolspec.datasets.splits import generate
from openmolspec.quality.dedup import analyze, molecule_identity


class DedupSplitTest(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            [
                {"sample_id": "A-1", "source_dataset": "A", "smiles": "CCO"},
                {"sample_id": "A-2", "source_dataset": "B", "smiles": "OCC"},
                {"sample_id": "B-1", "source_dataset": "B", "smiles": "c1ccccc1"},
                {"sample_id": "C-1", "source_dataset": "C", "smiles": "CC(=O)O"},
                {"sample_id": "D-1", "source_dataset": "D", "smiles": "C"},
                {"sample_id": "E-1", "source_dataset": "E", "smiles": "N"},
            ]
        )

    def test_identity_canonicalizes_equivalent_smiles(self):
        left = molecule_identity("CCO")
        right = molecule_identity("OCC")
        self.assertEqual(left["canonical_smiles"], right["canonical_smiles"])
        self.assertEqual(left["inchikey"], right["inchikey"])

    def test_dedup_reports_duplicate_identity(self):
        result = analyze(self.frame)
        self.assertEqual(result["summary"]["records"], 6)
        self.assertEqual(result["summary"]["canonical_smiles_duplicate_records"], 2)
        self.assertEqual(result["summary"]["cross_source_canonical_overlap_records"], 1)

    def test_grouped_splits_have_no_molecule_or_scaffold_leakage(self):
        identity, splits, leakage, _ = generate(self.frame, seed=7)
        for algorithm in ("molecule", "scaffold", "source"):
            report = leakage[algorithm]
            if algorithm == "molecule":
                self.assertEqual(
                    int(report.loc[report.identity_type == "molecule", "overlap_count"].sum()), 0
                )
            if algorithm == "scaffold":
                self.assertEqual(
                    int(report.loc[report.identity_type == "scaffold", "overlap_count"].sum()), 0
                )
        all_indices = [index for split in splits["molecule"].values() for index in split]
        self.assertEqual(sorted(all_indices), list(range(len(self.frame))))


if __name__ == "__main__":
    unittest.main()

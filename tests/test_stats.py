import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from openmolspec.quality import stats


def _core_frame(n=20):
    rows = []
    for index in range(n):
        n_atoms = 5 + (index % 5)
        rows.append(
            {
                "sample_id": f"QM9-{index}",
                "atom": np.arange(n_atoms, dtype=np.int32) + 1,
                "freq": np.linspace(-30.0 if index % 7 == 0 else 50.0, 3000.0, 3 * n_atoms - 6),
                "raman": np.zeros(1024),
                "energy": np.float32(-10.0 - 0.01 * n_atoms),
                "zpve": np.float32(0.1),
                "homo": np.float64(-0.2),
                "lumo": np.float64(-0.05),
                "gap": np.float64(0.15),
                "dipole_total": np.float64(1.0),
            }
        )
    frame = pd.DataFrame(rows)
    frame["sample_id"] = frame["sample_id"].astype(str)
    return frame


class StatsTest(unittest.TestCase):
    def test_scalar_nan_is_not_counted_as_frequency_or_raman(self):
        frame = _core_frame(2)
        frame.at[1, "freq"] = np.nan
        frame.at[1, "raman"] = np.nan
        features = stats.extract_core_features(frame)
        self.assertTrue(np.isnan(features.loc[1, "n_freq"]))
        self.assertFalse(features.loc[1, "raman_present"])

    def test_core_feature_extraction(self):
        manifest = pd.DataFrame(
            {
                "sample_id": [f"QM9-{index}" for index in range(20)],
                "source_dataset": ["QM9"] * 20,
                "inchikey": [f"KEY{index % 3}" for index in range(20)],
                "canonical_smiles": ["c1ccccc1"] * 20,
                "label_status": ["matched"] * 20,
            }
        )
        features = stats.extract_core_features(_core_frame(), manifest=manifest, workers=2)
        self.assertEqual(len(features), 20)
        self.assertEqual(features["source_dataset"].unique().tolist(), ["QM9"])
        self.assertEqual(features["raman_present"].sum(), 20)
        # Every 7th record has an imaginary frequency.
        self.assertEqual(int(features["has_imaginary_frequency"].sum()), 3)
        self.assertIn("energy_per_atom", features.columns)

    def test_convergence_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            report = {
                "input_logs": 10, "logs_with_trajectory": 9, "converged_logs": 8,
                "partial_logs": 1, "failed_logs": 1, "normal_termination_logs": 8,
            }
            (path / "qm9.json").write_text(json.dumps(report), encoding="utf-8")
            trajectory = pd.DataFrame(
                {
                    "sample_id": [f"QM9-{index}" for index in range(9)],
                    "n_steps": list(range(9)),
                    "is_converged": [True] * 8 + [False],
                    "is_final": [True] * 9,
                    "max_force": np.linspace(0.0001, 0.01, 9),
                    "rms_force": np.linspace(0.0001, 0.005, 9),
                    "trajectory_source": ["QM9"] * 9,
                }
            )
            convergence, nsteps = stats.convergence_table(str(path), trajectory)
            self.assertEqual(convergence.iloc[0]["source"], "QM9")
            self.assertAlmostEqual(convergence.iloc[0]["convergence_rate"], 0.8)
            self.assertEqual(nsteps.iloc[0]["count"], 9)

    def test_imaginary_frequency_table(self):
        features = pd.DataFrame(
            {
                "source_dataset": ["QM9", "QM9", "PAH"],
                "n_imaginary": [0, 2, np.nan],
            }
        )
        table, distribution = stats.imaginary_frequency_table(features)
        qm9 = table[table["source"] == "QM9"].iloc[0]
        self.assertEqual(qm9["with_imaginary"], 1)
        self.assertAlmostEqual(qm9["imaginary_fraction"], 0.5)
        self.assertGreaterEqual(distribution["records"].sum(), 2)

    def test_outlier_analysis(self):
        features = pd.DataFrame(
            {
                "sample_id": [f"QM9-{index}" for index in range(11)],
                "source_dataset": ["QM9"] * 11,
                "energy_per_atom": list(np.linspace(-0.5, -0.4, 10)) + [0.0],
                "gap": [1.0] * 10 + [1000.0],
                "n_atoms": [10] * 11,
            }
        )
        trajectory = pd.DataFrame(
            {
                "sample_id": [f"QM9-{index}" for index in range(10)],
                "max_force": [0.001] * 9 + [5.0],
                "rms_force": [0.0005] * 10,
            }
        )
        nmr = pd.DataFrame(
            {
                "sample_id": [f"QM9-{index}" for index in range(10)],
                "nmr_max_abs_isotropic": [150.0] * 9 + [5.0],
                "nmr_min_isotropic": [-20.0] * 10,
                "n_nmr_atoms": [6] * 10,
            }
        )
        stats_table, flagged = stats.outlier_analysis(features, trajectory, nmr)
        gap = stats_table[stats_table["field"] == "gap"].iloc[0]
        self.assertGreaterEqual(gap["flag_count"], 1)
        self.assertIn("gap", set(flagged["field"]))
        self.assertIn("flag_rule", gap.index)

    def test_duplicate_conformer_tables(self):
        features = pd.DataFrame(
            {
                "sample_id": [f"QM9-{index}" for index in range(6)],
                "source_dataset": ["QM9"] * 6,
                "inchikey": ["A", "A", "A", "B", "B", "C"],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            summary_path = Path(directory) / "dedup_summary.json"
            summary_path.write_text(
                json.dumps({"records": 6, "canonical_smiles_duplicate_records": 3,
                            "inchikey_duplicate_records": 3, "scaffold_duplicate_records": 5,
                            "cross_source_canonical_overlap_records": 1,
                            "exact_record_duplicate_records": 0}),
                encoding="utf-8",
            )
            dedup, distribution, by_source = stats.duplicate_conformer_tables(features, str(summary_path))
            self.assertEqual(distribution.loc[distribution["conformers"] == 1, "molecules"].sum(), 1)
            self.assertEqual(distribution.loc[distribution["conformers"] == 2, "molecules"].sum(), 1)
            self.assertEqual(distribution.loc[distribution["conformers"] == 3, "molecules"].sum(), 1)
            self.assertEqual(by_source.iloc[0]["molecules_with_multiple_conformers"], 2)

    def test_element_coverage(self):
        descriptors = pd.DataFrame({"elements": ["C,H", "C,N", "C,C", "C"]})
        coverage = stats.element_coverage(descriptors)
        self.assertEqual(coverage.loc[coverage["element"] == "C", "molecules"].iloc[0], 5)
        self.assertEqual(coverage.loc[coverage["element"] == "H", "molecules"].iloc[0], 1)

    def test_run_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core_frame(20)
            core.to_pickle(root / "core.pickle")
            manifest = pd.DataFrame(
                {
                    "sample_id": [f"QM9-{index}" for index in range(20)],
                    "source_dataset": ["QM9"] * 20,
                    "inchikey": [f"KEY{index % 4}" for index in range(20)],
                    "canonical_smiles": ["c1ccccc1"] * 20,
                    "label_status": ["matched"] * 20,
                }
            )
            manifest.to_parquet(root / "manifest.parquet", index=False)
            nmr = pd.DataFrame(
                {
                    "sample_id": [f"QM9-{index}" for index in range(20)],
                    "isotropic": [np.linspace(-10, 200, 6)] * 20,
                }
            )
            nmr.to_pickle(root / "nmr.pickle")
            trajectory_dir = root / "trajectories"
            trajectory_dir.mkdir()
            trajectory = pd.DataFrame(
                {
                    "sample_id": [f"QM9-{index}" for index in range(20)],
                    "n_steps": list(range(1, 21)),
                    "is_converged": [True] * 20,
                    "is_final": [True] * 20,
                    "max_force": [0.001] * 20,
                    "rms_force": [0.0005] * 20,
                    "energy": [-10.0] * 20,
                    "n_imaginary_frequencies": [0] * 20,
                    "minimum_frequency": [100.0] * 20,
                }
            )
            trajectory.to_pickle(trajectory_dir / "openspec_qm9_opt_trajectories.pickle")
            opt_dir = root / "opt"
            opt_dir.mkdir()
            (opt_dir / "qm9.json").write_text(
                json.dumps({"input_logs": 20, "logs_with_trajectory": 20, "converged_logs": 20,
                            "partial_logs": 0, "failed_logs": 0, "normal_termination_logs": 20}),
                encoding="utf-8",
            )
            descriptors = pd.DataFrame(
                {
                    "inchikey": [f"KEY{index % 4}" for index in range(20)],
                    "molecular_weight": np.linspace(50, 500, 20),
                    "heavy_atom_count": list(range(5, 25)),
                    "atom_count": list(range(8, 28)),
                    "elements": ["C,H"] * 20,
                }
            )
            descriptors.to_parquet(root / "descriptors.parquet", index=False)
            (root / "dedup_summary.json").write_text(
                json.dumps({"records": 20, "exact_record_duplicate_records": 0,
                            "canonical_smiles_duplicate_records": 5, "inchikey_duplicate_records": 5,
                            "scaffold_duplicate_records": 10, "cross_source_canonical_overlap_records": 1}),
                encoding="utf-8",
            )
            source_stats = pd.DataFrame(
                {
                    "source_dataset": ["QM9"], "records": [20], "frequency_success": [20],
                    "frequency_rate": [100.0], "nmr_success": [20], "nmr_rate": [100.0],
                    "tri_modal_records": [20], "tri_modal_rate": [100.0],
                }
            )
            source_stats.to_parquet(root / "source_stats.parquet", index=False)
            record_qc = pd.DataFrame(
                {"sample_id": [f"QM9-{index}" for index in range(20)], "qc_pass": [True] * 20}
            )
            record_qc.to_parquet(root / "record_qc.parquet", index=False)

            output = root / "publication"
            summary = stats.run(
                pickle_path=str(root / "core.pickle"),
                nmr_pickle_path=str(root / "nmr.pickle"),
                manifest_path=str(root / "manifest.parquet"),
                trajectory_dir=str(trajectory_dir),
                descriptors_path=str(root / "descriptors.parquet"),
                opt_reports_dir=str(opt_dir),
                dedup_summary_path=str(root / "dedup_summary.json"),
                source_statistics_path=str(root / "source_stats.parquet"),
                record_qc_path=str(root / "record_qc.parquet"),
                output=str(output),
                cache_dir=str(root / "cache"),
                workers=2,
            )
            self.assertEqual(summary["records"], 20)
            self.assertEqual(summary["raman_records"], 20)
            self.assertTrue((output / "summary.json").exists())
            self.assertTrue((output / "convergence_by_source.csv").exists())
            self.assertTrue((output / "modality_success_by_source.csv").exists())
            self.assertTrue((output / "imaginary_frequency_by_source.csv").exists())
            self.assertTrue((output / "outlier_summary.csv").exists())
            self.assertTrue((output / "conformer_count_distribution.csv").exists())
            self.assertTrue((output / "source_success_anomaly.csv").exists())
            self.assertTrue((output / "element_coverage.csv").exists())
            self.assertTrue((output / "figures" / "fig_outlier_detection.png").exists())


if __name__ == "__main__":
    unittest.main()

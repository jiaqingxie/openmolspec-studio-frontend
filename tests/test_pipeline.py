import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from openmolspec.workflows.frequency import extract_frequency
from openmolspec.io.tasks import load_tasks
from openmolspec.workflows.manifest import build_manifest
from openmolspec.workflows.nmr import extract_nmr


class PipelineTest(unittest.TestCase):
    def test_native_manifest_input_does_not_require_compatibility_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.parquet"
            pd.DataFrame(
                [
                    {
                        "sample_id": "QM9-1",
                        "smiles": "C",
                        "frequency_log_path": "/data/1.log",
                    },
                    {
                        "sample_id": "QM9-2",
                        "smiles": "CC",
                        "frequency_log_path": None,
                    },
                ]
            ).to_parquet(manifest, index=False)

            tasks, smiles = load_tasks(
                manifest_path=str(manifest),
                path_field="frequency_log_path",
            )

            self.assertEqual(tasks, [("QM9-1", "/data/1.log")])
            self.assertEqual(smiles, {"QM9-1": "C"})

    def test_manifest_stage_uses_configurable_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freq_root = root / "freq"
            dataset = freq_root / "qm9"
            log_dir = dataset / "qm9_log"
            log_dir.mkdir(parents=True)
            (log_dir / "1.log").write_text("sample", encoding="utf-8")
            (dataset / "qm9_label.json").write_text(json.dumps({"1": "CCO"}), encoding="utf-8")
            output = root / "datasets"
            summary = build_manifest(
                frequency_root=str(freq_root), nmr_root=str(root / "nmr"),
                output_dir=str(output), datasets=["qm9"], nmr_datasets=[],
                include_nmr=False, hash_files=False,
            )
            self.assertEqual(summary["records"], 1)
            self.assertTrue((output / "openspec_manifest.parquet").exists())

    def test_extract_stage_writes_dataset_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file_path = root / "one.log"
            file_path.write_text("truncated Gaussian output", encoding="utf-8")
            file_map = root / "files.json"
            smiles_map = root / "smiles.json"
            file_map.write_text(json.dumps({"BROKEN-1": str(file_path)}), encoding="utf-8")
            smiles_map.write_text(json.dumps({"BROKEN-1": "CCO"}), encoding="utf-8")
            output = root / "data.pickle"
            summary = extract_frequency(
                file_dict=str(file_map), smiles_dict=str(smiles_map), output=str(output),
                report_dir=str(root / "report"), workers=1,
                frequency_scaling_factor=0.965, ir_broadening_sigma=12,
                raman_broadening_sigma=12,
            )
            self.assertEqual(summary["parsed_records"], 0)
            self.assertTrue(output.exists())
            self.assertTrue((root / "report" / "processing_report.parquet").exists())

    def test_nmr_stage_writes_records_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "nmr.log"
            log_path.write_text(
                "1 C Isotropic = 10.0 Anisotropy = 1.0\n"
                "XX= 10.1 YX= 0.1 ZX= 0.2 XY= 0.1 YY= 9.9 ZY= 0.3 "
                "XZ= 0.2 YZ= 0.3 ZZ= 10.0\n",
                encoding="utf-8",
            )
            file_map = root / "nmr_files.json"
            smiles_map = root / "smiles.json"
            file_map.write_text(json.dumps({"QM9-1": str(log_path)}), encoding="utf-8")
            smiles_map.write_text(json.dumps({"QM9-1": "C"}), encoding="utf-8")
            output = root / "nmr.pickle"
            summary = extract_nmr(
                file_dict=str(file_map), smiles_dict=str(smiles_map),
                output=str(output), report_dir=str(root / "report"), workers=1,
            )
            self.assertEqual(summary["parsed_records"], 1)
            frame = pd.read_pickle(output)
            self.assertEqual(frame.iloc[0]["sample_id"], "QM9-1")
            self.assertEqual(frame.iloc[0]["shielding_tensor"].shape, (1, 3, 3))
            self.assertTrue((root / "report" / "processing_report.parquet").exists())


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors


def load_labels_module():
    path = (
        Path(__file__).parents[1]
        / "src" / "openmolspec" / "workflows" / "manifest_scan.py"
    )
    spec = importlib.util.spec_from_file_location("extract_labels", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtractLabelsTest(unittest.TestCase):
    def test_inchi_label_is_converted_to_smiles(self):
        module = load_labels_module()
        normalized = module.normalize_smiles("InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3")
        self.assertIsNone(normalized["error"])
        self.assertEqual(normalized["canonical_smiles"], "CCO")
        self.assertEqual(normalized["smiles"], "CCO")
        self.assertIsNotNone(normalized["inchikey"])

    def test_standard_peptide_sequence_is_converted_to_smiles(self):
        module = load_labels_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_dir = root / "freq" / "peptide" / "peptide_log"
            log_dir.mkdir(parents=True)
            log_path = log_dir / "A-F-P-L.log"
            log_path.write_text("Gaussian", encoding="utf-8")

            rows, _ = module.collect_collection(
                root / "freq", "peptide", hash_files=False
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["sample_id"], "PEPTIDE-A-F-P-L")
            self.assertEqual(rows[0]["label_status"], "matched")
            self.assertIsNotNone(rows[0]["smiles"])
            self.assertIsNotNone(rows[0]["inchikey"])
            self.assertEqual(rows[0]["frequency_log_path"], str(log_path))
            self.assertEqual(rows[0]["available_modalities"], ["frequency"])

    def test_modified_peptide_smiles_have_expected_formula(self):
        module = load_labels_module()
        expected = {
            "pS": "C3H8NO6P",
            "pT": "C4H10NO6P",
            "pY": "C9H12NO6P",
            "pH1": "C6H10N3O5P",
            "pH2": "C6H10N3O5P",
            "sS": "C3H7NO6S",
            "sT": "C4H9NO6S",
            "sY": "C9H11NO6S",
        }
        for residue, formula in expected.items():
            with self.subTest(residue=residue):
                normalized = module.normalize_peptide_sequence(residue)
                self.assertIsNone(normalized["error"])
                molecule = Chem.MolFromSmiles(normalized["smiles"])
                self.assertEqual(rdMolDescriptors.CalcMolFormula(molecule), formula)

    def test_frequency_and_nmr_merge(self):
        module = load_labels_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freq_dataset = root / "freq" / "qm9"
            freq_logs = freq_dataset / "qm9_log"
            nmr_dataset = root / "nmr" / "qm9_nmr"
            nmr_logs = nmr_dataset / "qm9_nmr_log"
            freq_logs.mkdir(parents=True)
            nmr_logs.mkdir(parents=True)
            (freq_logs / "1.log").write_text("freq", encoding="utf-8")
            (nmr_logs / "1.log").write_text("nmr", encoding="utf-8")
            (freq_dataset / "qm9_label.json").write_text(json.dumps({"1": "CCO"}), encoding="utf-8")
            (nmr_dataset / "qm9_label.json").write_text(json.dumps({"1": "OCC"}), encoding="utf-8")

            freq, _ = module.collect_collection(root / "freq", "qm9", hash_files=False)
            nmr, _ = module.collect_collection(root / "nmr", "qm9", nmr=True, hash_files=False)
            frame, audit = module.merge_records(freq + nmr)

            self.assertEqual(len(frame), 1)
            self.assertEqual(frame.iloc[0]["sample_id"], "QM9-1")
            self.assertEqual(set(frame.iloc[0]["available_modalities"]), {"frequency", "nmr"})
            self.assertEqual(frame.iloc[0]["label_status"], "matched")
            self.assertEqual(len(audit), 0)

    def test_peptide_nmr_reuses_frequency_identity_without_label_json(self):
        module = load_labels_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freq_logs = root / "freq" / "peptide" / "peptide_log"
            nmr_logs = root / "nmr" / "peptide_nmr" / "peptide_nmr_log"
            freq_logs.mkdir(parents=True)
            nmr_logs.mkdir(parents=True)
            (freq_logs / "A-F-P-L.log").write_text("freq", encoding="utf-8")
            nmr_path = nmr_logs / "A-F-P-L.log"
            nmr_path.write_text("nmr", encoding="utf-8")

            freq, _ = module.collect_collection(
                root / "freq", "peptide", hash_files=False
            )
            identity_lookup = {row["sample_id"]: row for row in freq}
            nmr, audit = module.collect_collection(
                root / "nmr",
                "peptide",
                nmr=True,
                hash_files=False,
                identity_lookup=identity_lookup,
                audit_all_records=False,
            )

            self.assertEqual(len(nmr), 1)
            self.assertEqual(nmr[0]["label_status"], "matched")
            self.assertEqual(nmr[0]["nmr_log_path"], str(nmr_path))
            self.assertEqual(nmr[0]["inchikey"], freq[0]["inchikey"])
            self.assertEqual(audit, [])

    def test_both_modality_hashes_survive_merge(self):
        module = load_labels_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freq_dataset = root / "freq" / "qm9"
            nmr_dataset = root / "nmr" / "qm9_nmr"
            freq_logs = freq_dataset / "qm9_log"
            nmr_logs = nmr_dataset / "qm9_nmr_log"
            freq_logs.mkdir(parents=True)
            nmr_logs.mkdir(parents=True)
            (freq_logs / "1.log").write_text("frequency", encoding="utf-8")
            (nmr_logs / "1.log").write_text("nmr", encoding="utf-8")
            labels = json.dumps({"1": "CCO"})
            (freq_dataset / "qm9_label.json").write_text(labels, encoding="utf-8")
            (nmr_dataset / "qm9_label.json").write_text(labels, encoding="utf-8")

            freq, _ = module.collect_collection(root / "freq", "qm9")
            nmr, _ = module.collect_collection(root / "nmr", "qm9", nmr=True)
            frame, _ = module.merge_records(freq + nmr)

            self.assertEqual(
                frame.iloc[0]["frequency_file_hash"],
                module.sha256_file(freq_logs / "1.log"),
            )
            self.assertEqual(
                frame.iloc[0]["nmr_file_hash"],
                module.sha256_file(nmr_logs / "1.log"),
            )

    def test_incremental_cache_reuses_unchanged_logs_and_tracks_deletions(self):
        module = load_labels_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "freq" / "qm9"
            log_dir = dataset / "qm9_log"
            log_dir.mkdir(parents=True)
            log_path = log_dir / "1.log"
            log_path.write_text("first", encoding="utf-8")
            (dataset / "qm9_label.json").write_text(
                json.dumps({"1": "CCO"}), encoding="utf-8"
            )
            cache_path = root / "cache" / "qm9.parquet"
            calls = 0
            original = module.normalize_smiles

            def counted(value):
                nonlocal calls
                calls += 1
                return original(value)

            module.normalize_smiles = counted
            rows, _ = module.collect_collection(
                root / "freq", "qm9", hash_files=False, cache_path=cache_path
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(calls, 1)

            rows, _ = module.collect_collection(
                root / "freq", "qm9", hash_files=False, cache_path=cache_path
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(calls, 1)

            log_path.write_text("changed and longer", encoding="utf-8")
            rows, _ = module.collect_collection(
                root / "freq", "qm9", hash_files=False, cache_path=cache_path
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(calls, 2)

            log_path.unlink()
            rows, _ = module.collect_collection(
                root / "freq", "qm9", hash_files=False, cache_path=cache_path
            )
            self.assertEqual(rows, [])

    def test_recent_source_file_is_skipped(self):
        module = load_labels_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "freq" / "qm9"
            log_dir = dataset / "qm9_log"
            log_dir.mkdir(parents=True)
            log_path = log_dir / "1.log"
            log_path.write_text("still being written", encoding="utf-8")
            os.utime(log_path, None)
            (dataset / "qm9_label.json").write_text(
                json.dumps({"1": "CCO"}), encoding="utf-8"
            )

            rows, audit = module.collect_collection(
                root / "freq",
                "qm9",
                hash_files=False,
                min_file_age_seconds=300,
                audit_all_records=False,
            )

            self.assertEqual(rows, [])
            self.assertEqual(audit[0]["error_type"], "SOURCE_FILE_TOO_RECENT")

    def test_conflicting_modalities_are_reported(self):
        module = load_labels_module()
        base = {
            "sample_id": "QM9-1", "source_dataset": "QM9", "source_id": "1",
            "smiles": "CCO", "canonical_smiles": "CCO", "inchikey": "A",
            "scaffold": "__ACYCLIC__", "label_status": "matched", "label_errors": [],
            "available_modalities": ["frequency"], "frequency_log_path": "freq.log",
            "nmr_log_path": None, "source_file_hash": None,
        }
        conflict = dict(base)
        conflict.update({"canonical_smiles": "CC", "smiles": "CC", "available_modalities": ["nmr"], "frequency_log_path": None, "nmr_log_path": "nmr.log"})
        frame, audit = module.merge_records([base, conflict])
        self.assertEqual(frame.iloc[0]["label_status"], "conflict")
        self.assertEqual(audit[0]["error_type"], "SMILES_MODALITY_MISMATCH")


if __name__ == "__main__":
    unittest.main()

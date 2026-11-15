"""Run existing weights or score existing predictions; never train models."""

import json
import pickle
import sys
from pathlib import Path

import numpy as np

from .data import CpuUnpickler, load_rows, readonly_lmdb, sha256
from .metrics import peak_metrics, regression_metrics, retrieval_metrics


class MissingAsset(FileNotFoundError):
    pass


def require(path):
    path = Path(path)
    if not path.is_file():
        raise MissingAsset(str(path))
    return path


def read_prediction_folds(files):
    """Recover per-molecule atom arrays from padded mask and packed predictions."""
    folds = []
    for file in files:
        with file.open("rb") as stream:
            batches = CpuUnpickler(stream).load()
        predictions = {}
        for batch in batches:
            def array(value):
                return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)
            matids = array(batch["matid"]).reshape(-1)
            selected = array(batch["select_atom"]).reshape(-1)
            predicted = array(batch["predict"]).reshape(-1)
            if not len(matids) or len(selected) % len(matids):
                raise ValueError(f"Inconsistent padded atom mask in {file}")
            stride = len(selected) // len(matids)
            offset = 0
            for index, matid in enumerate(matids):
                count = int(selected[index * stride:(index + 1) * stride].sum())
                predictions.setdefault(int(matid), []).append(predicted[offset:offset + count])
                offset += count
            if offset != len(predicted):
                raise ValueError(f"Atom prediction count does not match mask in {file}")
        folds.append({key: np.concatenate(value) for key, value in predictions.items()})
    return folds


class Runner:
    def __init__(self, args):
        self.args = args
        self.models = {}
        self.encoded = {}
        self.hashes = {}
        self.service = None

    def artifact(self, path):
        path = require(path).resolve()
        if path not in self.hashes:
            self.hashes[path] = sha256(path)
        return {"path": str(path), "sha256": self.hashes[path]}

    def model(self, stage):
        import torch
        from spec2struct_fork.model import ModelConfig, SpectrumToSmiles

        path = self.args.alignment_checkpoint if stage == "align" else self.args.generation_checkpoint
        path = require(path)
        if stage not in self.models:
            payload = torch.load(path, map_location="cpu", weights_only=True)
            if payload.get("training_stage") != stage:
                raise ValueError(f"Expected {stage} checkpoint, got {payload.get('training_stage')}")
            model = SpectrumToSmiles(ModelConfig(**payload["config"]))
            model.load_state_dict(payload["model"])
            self.models[stage] = model.to(self.args.device).eval()
        return self.models[stage], path

    def nmr(self, task, dataset):
        import torch
        from spec2struct_fork.train import make_collate, evaluate_generation

        path = require(self.args.workspace / "data/align_eval" / dataset / "test.jsonl")
        parts = task.id.split(".")
        view = parts[2]
        stage = "generate" if task.backend == "spec2struct_generation" else "align"
        model, checkpoint = self.model(stage)
        capacity = model.config.max_target - 2 if stage == "align" and model.config.molecule_tokenizer == "byte" else None
        rows, selection = load_rows(path, view, self.args.limit, max_smiles_bytes=capacity)
        provenance = {"dataset": self.artifact(path), "selection": selection,
                      "sample_ids": [row["smiles"] for row in rows],
                      "sampling": "first_distinct_canonical_structures_in_file_order",
                      "domain_verification": "legacy_dataset_source_not_independently_reaudited",
                      "split_leakage_audit": "not_performed_by_this_smoke_run"}
        if task.backend == "spec2struct_generation":
            if any(not row["formula"] for row in rows):
                raise ValueError("Generation requires an explicitly supplied formula on every row")
            # The existing evaluator streams a file. Use normalized rows, preserving their order.
            import tempfile
            with tempfile.TemporaryDirectory(prefix="openmolspec-eval-") as directory:
                selected = Path(directory) / "test.jsonl"
                selected.write_text("".join(json.dumps(row) + "\n" for row in rows))
                metrics = evaluate_generation(model, selected, len(rows), self.args.beam_size,
                                              batch_size=self.args.batch_size)
            return {"metrics": metrics, "checkpoint": self.artifact(checkpoint),
                    "given_formula": True, "beam_size": self.args.beam_size, **provenance}
        key = (dataset, view)
        if key not in self.encoded:
            if len(rows) < 2:
                raise ValueError("Retrieval needs at least two distinct candidate structures")
            spectra, molecules = [], []
            collate = make_collate(model.config, include_formula=False)
            with torch.inference_mode():
                for start in range(0, len(rows), self.args.batch_size):
                    source, target, _ = collate(rows[start:start + self.args.batch_size])
                    s, m = model.alignment_embeddings(source.to(self.args.device), target.to(self.args.device))
                    spectra.append(s.cpu())
                    molecules.append(m.cpu())
            s = torch.cat(spectra)
            m = torch.cat(molecules)
            self.encoded[key] = (s @ m.T).numpy()
        scores = self.encoded[key]
        if parts[3] == "m2s":
            scores = scores.T
        ids = [row["smiles"] for row in rows]
        return {"metrics": retrieval_metrics(scores, ids, ids), "given_formula": False,
                "checkpoint": self.artifact(checkpoint), **provenance}

    def forward(self, task, dataset):
        """Score trusted local NMRNet batch-packed output, retaining molecule order."""
        from spec2struct_fork.structured import parse_nmr_record, SHIFT, SHIFT_PRESENT
        import lmdb

        symbol = "H" if task.modalities == ("1H",) else "C"
        path = require(self.args.workspace / "data/align_eval" / dataset / "test.jsonl")
        rows, selection = load_rows(path, symbol.lower(), self.args.limit)
        reference = {}
        for row in rows:
            peaks = [features[SHIFT] for record in row[f"{symbol.lower()}_nmr"]
                     for features in parse_nmr_record(record, symbol.lower()) if features[SHIFT_PRESENT]]
            if peaks:
                reference[row["smiles"]] = peaks
        results = []
        from rdkit import Chem
        for backend in ("nmrnet", "nmrnetpp"):
            root = self.args.models_root / backend
            meta = self.args.models_root / "nmrnetpp/data_ours" / f"{dataset}_{symbol}" / "valid.lmdb"
            files = sorted((root / "results" / f"{dataset}_{symbol}").glob("*/*.out.pkl"))
            if not meta.is_file() or not files:
                continue
            env = readonly_lmdb(meta)
            with env.begin() as transaction:
                smis = [pickle.loads(value)["smiles"] for _, value in transaction.cursor()]
            env.close()
            folds = read_prediction_folds(files)
            predicted, expected, identities, covered = [], [], [], set()
            for index in sorted(set.intersection(*(set(fold) for fold in folds))):
                if not 0 <= index < len(smis):
                    raise ValueError("Prediction matid outside metadata index")
                molecule = Chem.MolFromSmiles(smis[index])
                identity = Chem.MolToSmiles(molecule, isomericSmiles=True) if molecule else ""
                if identity not in reference or identity in covered:
                    continue
                values = [fold[index] for fold in folds]
                if len({value.shape for value in values}) != 1:
                    raise ValueError("Fold predictions have inconsistent atom shapes")
                predicted.append(np.mean(np.stack(values), axis=0))
                expected.append(reference[identity])
                identities.append(identity)
                covered.add(identity)
            if predicted:
                results.append({"model": backend, "metrics": peak_metrics(predicted, expected),
                                "inference_mode": "score_existing_predictions",
                                "selected_references": len(reference), "covered_references": len(predicted),
                                "sample_ids": identities, "folds": len(files),
                                "prediction_files": [self.artifact(file) for file in files],
                                "metadata": self.artifact(meta)})
        if not results:
            raise MissingAsset("No existing NMRNet/NMRNet++ predictions matched the selected references")
        return {"models": results, "dataset": self.artifact(path), "selection": selection,
                "solvent_filter": "none; retain recorded reference peaks",
                "domain_verification": "legacy_dataset_source_not_independently_reaudited",
                "split_leakage_audit": "not_performed_by_this_smoke_run"}

    def hetero(self, task):
        symbol = {"19F": "F", "31P": "P"}[task.modalities[0]]
        meta = require(self.args.models_root / "nmrnetpp" / f"pool_{symbol}" / "valid.lmdb")
        files = sorted((self.args.models_root / "nmrnet/results_solid" / symbol).glob("*/*.out.pkl"))
        if not files:
            raise MissingAsset(f"No existing solid-state NMRNet {symbol} prediction files")
        env = readonly_lmdb(meta)
        try:
            with env.begin() as transaction:
                rows = [pickle.loads(value) for _, value in transaction.cursor()]
        finally:
            env.close()
        folds = read_prediction_folds(files)
        errors, ids = [], []
        for index in sorted(set.intersection(*(set(fold) for fold in folds))):
            if not 0 <= index < len(rows):
                raise ValueError("Heteronucleus matid outside metadata index")
            row = rows[index]
            mask = np.asarray(row["atoms_target_mask"], dtype=bool)
            atoms = np.asarray(row["atoms"])
            if mask.sum() != 1 or not np.all(atoms[mask] == symbol):
                raise ValueError("Heteronucleus diagnostic requires exactly one labeled atom of the selected nucleus")
            target = np.asarray(row["atoms_target"])[mask]
            predicted = [fold[index] for fold in folds]
            if any(value.shape != target.shape for value in predicted):
                raise ValueError("Heteronucleus prediction/label atom shapes differ")
            error = float((np.mean(np.stack(predicted), axis=0) - target).item())
            if not np.isfinite(error):
                raise ValueError("Nonfinite heteronucleus prediction or label")
            errors.append(error)
            ids.append(row["smiles"])
            if len(ids) >= self.args.limit:
                break
        if not errors:
            raise ValueError("No paired heteronucleus predictions")
        return {"metrics": {"mae_ppm": float(np.mean(np.abs(errors))),
                            "rmse_ppm": float(np.sqrt(np.mean(np.square(errors)))), "examples": len(errors)},
                "dataset_name": f"pooled_nmrexp_wanjuan_{symbol}_valid", "dataset": self.artifact(meta),
                "prediction_files": [self.artifact(file) for file in files], "folds": len(files),
                "sample_ids": ids, "inference_mode": "score_existing_predictions",
                "model_domain": "solid_state", "evaluation_domain": "experimental_solution",
                "purpose": "cross_domain_pipeline_diagnostic", "atom_selection": "one_labeled_atom_of_selected_nucleus",
                "split_leakage_audit": "not_performed_by_this_smoke_run"}

    def gap(self, task):
        from openmolspec_ui.config import discover_assets
        from openmolspec_ui.inference import OpenMolSpecService
        from openmolspec_ui.spectra import SpectralInput
        import lmdb

        if self.service is None:
            self.service = OpenMolSpecService(discover_assets(self.args.portable_root), device=self.args.device)
        path = require(self.args.gap_lmdb or self.service.assets.spectrum_lmdb or Path("missing.lmdb"))
        if self.service.assets.gap_checkpoint is None:
            raise MissingAsset("No spectrum-to-gap checkpoint")
        view = task.id.split(".")[-1]
        predicted, expected, ids = [], [], []
        env = readonly_lmdb(path)
        try:
            with env.begin() as transaction:
                for key, value in transaction.cursor():
                    row = pickle.loads(value)
                    target = row.get("gap")
                    if target is None:
                        continue
                    inputs = SpectralInput(ir=np.asarray(row["ir"], dtype=np.float32) if view != "raman" else None,
                                           raman=np.asarray(row["raman"], dtype=np.float32) if view != "ir" else None)
                    predicted.append(self.service.predict_gap(inputs)["gap_ev"])
                    unit = row.get("units", {}).get("gap") or self.args.gap_unit
                    if unit == "auto":
                        if self.args.gap_lmdb is not None:
                            raise ValueError("Custom gap LMDB must specify units.gap or --gap-unit")
                        unit = "hartree"  # The bundled Vib2Mol LMDB retains Gaussian atomic units.
                    if unit not in ("hartree", "eV"):
                        raise ValueError(f"Unsupported gap unit: {unit}")
                    expected.append(float(target) * (27.211386245988 if unit == "hartree" else 1))
                    ids.append(str(row.get("sample_id", key.decode())))
                    if len(ids) >= self.args.limit:
                        break
        finally:
            env.close()
        if not ids:
            raise MissingAsset("LMDB has no gap reference labels; provide --gap-lmdb with gap in eV")
        return {"metrics": regression_metrics(predicted, expected), "sample_ids": ids,
                "dataset": self.artifact(path), "checkpoint": self.artifact(self.service.assets.gap_checkpoint),
                "given_nmr": False, "unit": "eV", "input_gap_unit": unit,
                "sampling": "first_labeled_records_in_lmdb_order"}

    def vibrational(self, task):
        """Evaluate Vib2Mol directly on a bounded candidate pool, without fallback."""
        from openmolspec_ui.config import discover_assets
        from openmolspec_ui.inference import OpenMolSpecService
        from openmolspec_ui.spectra import SpectralInput
        import torch
        import torch.nn.functional as functional
        from rdkit import Chem

        if self.service is None:
            self.service = OpenMolSpecService(discover_assets(self.args.portable_root), device=self.args.device)
        path = require(self.service.assets.spectrum_lmdb or Path("missing.lmdb"))
        phase = 2 if task.backend == "vib2mol_generation" else 1
        model, tokenizer, device = self.service._load_vib2mol(phase)
        from benchmarks.models.vib2mol.evaluate_multimodal import encode_spectra, rerank_candidates
        rows, ids, strings, inputs, seen = [], [], [], [], set()
        env = readonly_lmdb(path)
        try:
            with env.begin() as transaction:
                for key, value in transaction.cursor():
                    row = pickle.loads(value)
                    molecule = Chem.MolFromSmiles(row["kekule_smiles"])
                    if molecule is None:
                        raise ValueError(f"Invalid reference structure at {key!r}")
                    identity = Chem.MolToSmiles(molecule, isomericSmiles=True)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    rows.append(row)
                    ids.append(identity)
                    strings.append(Chem.MolToSmiles(molecule, isomericSmiles=True, kekuleSmiles=True))
                    inputs.append(self.service._vib2mol_input(SpectralInput(
                        ir=np.asarray(row["ir"], dtype=np.float32),
                        raman=np.asarray(row["raman"], dtype=np.float32)), device))
                    if len(rows) >= self.args.limit:
                        break
        finally:
            env.close()
        if not rows:
            raise ValueError("Empty vibrational test pool")
        provenance = {"dataset": self.artifact(path), "sample_ids": ids, "given_nmr": False,
                      "given_formula": False, "inference_mode": "direct_checkpoint",
                      "sampling": "first_distinct_canonical_structures_in_lmdb_order"}
        tokens = tokenizer(strings, padding=True, truncation=False, return_tensors="pt")
        if tokens["input_ids"].shape[1] > tokenizer.model_max_length or (tokens["input_ids"] == tokenizer.unk_token_id).any():
            raise ValueError("Reference structures exceed tokenizer capacity or contain unknown tokens")
        checkpoint = self.service.assets.generation_checkpoint if phase == 2 else self.service.assets.retrieval_checkpoint
        provenance["checkpoint"] = self.artifact(checkpoint)
        if phase == 2:
            predictions, valid, exact = [], 0, 0
            with torch.inference_mode():
                for identity, data in zip(ids, inputs):
                    sequences = model.beam_infer_lm(data, beam_size=self.args.beam_size, max_len=300)["pred_ids"][0]
                    raw = tokenizer.decode(sequences[0], skip_special_tokens=True).replace(" ", "")
                    molecule = Chem.MolFromSmiles(raw)
                    canonical = Chem.MolToSmiles(molecule, isomericSmiles=True) if molecule and molecule.GetNumAtoms() else None
                    valid += int(canonical is not None)
                    exact += int(canonical == identity)
                    predictions.append({"reference": identity, "raw_top_1": raw, "canonical_top_1": canonical})
            return {**provenance, "metrics": {"valid_rate": valid / len(rows), "exact_rate": exact / len(rows),
                                               "examples": len(rows)}, "beam_size": self.args.beam_size,
                    "ranking": "raw_beam_top_1_without_reranking", "predictions": predictions}
        if len(rows) < 2:
            raise ValueError("Vibrational retrieval/reranking needs at least two candidates")
        if task.backend == "vib2mol_reranking":
            scores = np.empty((len(rows), len(rows)))
            with torch.inference_mode():
                for index, data in enumerate(inputs):
                    order, ranked = rerank_candidates(model, tokenizer, data, strings, self.args.batch_size)
                    scores[index, order] = ranked
            metrics = retrieval_metrics(scores, ids, ids)
            metrics["top_1_hit_rate"] = metrics["recall_at_1"]
            return {**provenance, "metrics": metrics, "ranking": "itm_positive_probability"}
        with torch.inference_mode():
            molecule_ids = tokens["input_ids"].to(device)
            mask = tokens["attention_mask"].to(device)
            mask = torch.cat((mask.new_ones((len(mask), 1)), mask), dim=1)
            molecular = functional.normalize(model.molecular_encoder(
                model.molecular_encoding(molecule_ids, use_cls_token=True), mask=mask)["proj_output"], dim=-1)
            spectral = functional.normalize(torch.cat([encode_spectra(model, data)["proj_output"] for data in inputs]), dim=-1)
            scores = (spectral @ molecular.T).cpu().numpy()
        return {**provenance, "metrics": retrieval_metrics(scores, ids, ids),
                "reverse_metrics": retrieval_metrics(scores.T, ids, ids)}

    def run(self, task, dataset):
        if task.backend.startswith("spec2struct"):
            return self.nmr(task, dataset)
        if task.backend == "nmrnet_predictions":
            return self.forward(task, dataset)
        if task.backend == "nmrnet_hetero_predictions":
            return self.hetero(task)
        if task.backend == "studio_gap":
            return self.gap(task)
        if task.backend.startswith("vib2mol_"):
            return self.vibrational(task)
        raise MissingAsset(task.note)

"""Run existing weights or score existing predictions; never train models."""

import json
import pickle
import sys
from pathlib import Path

import numpy as np

from .data import CpuUnpickler, load_rows, readonly_lmdb, select_vibrational_rows, sha256
from .metrics import peak_metrics, regression_metrics, retrieval_metrics


class MissingAsset(FileNotFoundError):
    pass


def require(path):
    path = Path(path)
    if not path.is_file():
        raise MissingAsset(str(path))
    return path


def read_prediction_folds(files, field="predict"):
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
            predicted = array(batch[field]).reshape(-1)
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
                                              batch_size=self.args.batch_size, record_predictions=True)
            predictions = metrics.pop("predictions")
            return {"metrics": metrics, "checkpoint": self.artifact(checkpoint),
                    "given_formula": True, "beam_size": self.args.beam_size,
                    "predictions": predictions, **provenance}
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
                "examples": [{"query": rows[i], "direction": parts[3],
                              "ranked_candidates": [{"smiles": ids[j], "score": float(scores[i,j]),
                                                      "reference_match": ids[j] == ids[i]}
                                                     for j in np.argsort(-scores[i], kind="stable")[:10]]}
                             for i in range(min(3, len(rows)))],
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
                                "examples": [{"smiles": identity, "reference_ppm": list(ref),
                                              "prediction_ppm": pred.tolist()}
                                             for identity, ref, pred in list(zip(identities, expected, predicted))[:3]],
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
        fresh = self.args.fp_inference_root
        meta = require(fresh / f"{symbol}.lmdb" if fresh else self.args.models_root / "nmrnetpp" / f"pool_{symbol}" / "valid.lmdb")
        prediction_root = fresh / symbol if fresh else self.args.models_root / "nmrnet/results_solid" / symbol
        files = sorted(prediction_root.glob("*/*.out.pkl"))
        if not files:
            raise MissingAsset(f"No existing solid-state NMRNet {symbol} prediction files")
        env = readonly_lmdb(meta)
        try:
            with env.begin() as transaction:
                rows = [pickle.loads(value) for _, value in transaction.cursor()]
        finally:
            env.close()
        folds = read_prediction_folds(files)
        logged_targets = read_prediction_folds(files, field="target")
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
            for logged in logged_targets:
                if index not in logged or logged[index].shape != target.shape or not np.allclose(logged[index], target, atol=0.1, rtol=1e-4):
                    raise MissingAsset("Existing F/P predictions do not match the current LMDB reference labels; rerun frozen inference against this exact LMDB before scoring. Earlier scores are invalidated.")
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
        if not self.args.allow_cross_domain_diagnostic:
            raise MissingAsset("F/P prediction-label alignment is verified, but the available solid-state checkpoint has no verified solution-shift reference. A compatible released checkpoint or documented reference conversion is required; no training or fitted calibration is performed. Use --allow-cross-domain-diagnostic only for a labeled diagnostic report.")
        return {"metrics": {"mae_ppm": float(np.mean(np.abs(errors))),
                            "rmse_ppm": float(np.sqrt(np.mean(np.square(errors)))), "examples": len(errors)},
                "dataset_name": f"pooled_nmrexp_wanjuan_{symbol}_valid", "dataset": self.artifact(meta),
                "prediction_files": [self.artifact(file) for file in files], "folds": len(files),
                "sample_ids": ids, "inference_mode": "score_existing_predictions",
                "model_domain": "solid_state", "evaluation_domain": "experimental_solution",
                "purpose": "cross_domain_pipeline_diagnostic", "atom_selection": "one_labeled_atom_of_selected_nucleus",
                "reference_convention_verified": False, "publication_scope": "diagnostic_only_not_primary_solution_benchmark",
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
        include_nmr = view == "ir_raman_hc"
        predicted, expected, ids = [], [], []
        env = readonly_lmdb(path)
        try:
            selected_rows, selection = select_vibrational_rows(env, self.args.limit, self.args.sampling, self.args.seed, require_gap=True)
            for row in selected_rows:
                    target = row["gap"]
                    inputs = SpectralInput(ir=np.asarray(row["ir"], dtype=np.float32) if view != "raman" else None,
                                           raman=np.asarray(row["raman"], dtype=np.float32) if view != "ir" else None,
                                           nmr_h=np.asarray(row["nmr_h_shifts_ppm"], dtype=np.float32) if include_nmr else None,
                                           nmr_c=np.asarray(row["nmr_c_shifts_ppm"], dtype=np.float32) if include_nmr else None)
                    if include_nmr:
                        _, checkpoint_payload = self.service._load_gap()
                        expected_ref = checkpoint_payload["model_metadata"]["nmr_normalization"]["reference_id"]
                        if row.get("nmr_reference_id") != expected_ref:
                            raise ValueError("Gap input/checkpoint NMR reference mismatch")
                    predicted.append(self.service.predict_gap(inputs)["gap_ev"])
                    unit = row.get("units", {}).get("gap") or self.args.gap_unit
                    if unit == "auto":
                        if self.args.gap_lmdb is not None:
                            raise ValueError("Custom gap LMDB must specify units.gap or --gap-unit")
                        unit = "hartree"  # The bundled Vib2Mol LMDB retains Gaussian atomic units.
                    if unit not in ("hartree", "eV"):
                        raise ValueError(f"Unsupported gap unit: {unit}")
                    expected.append(float(target) * (27.211386245988 if unit == "hartree" else 1))
                    ids.append(str(row.get("sample_id", row["_lmdb_key"])))
        finally:
            env.close()
        if not ids:
            raise MissingAsset("LMDB has no gap reference labels; provide --gap-lmdb with gap in eV")
        _, checkpoint_payload = self.service._load_gap()
        train_mean = float(checkpoint_payload["normalizer"]["mean"]["gap"])
        return {"metrics": regression_metrics(predicted, expected), "sample_ids": ids,
                "dataset": self.artifact(path), "checkpoint": self.artifact(self.service.assets.gap_checkpoint),
                "given_nmr": include_nmr, "unit": "eV", "input_gap_unit": unit,
                "training_mean_baseline": {"constant_ev": train_mean, **regression_metrics([train_mean] * len(expected), expected)},
                "reference_gap_ev": expected, "predicted_gap_ev": predicted,
                "sampling": self.args.sampling, "seed": self.args.seed, "selection": selection,
                "source_counts": dict(__import__('collections').Counter(row.get('source_dataset','unknown') for row in selected_rows))}

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
        include_nmr = task.id.endswith(".hc")
        rows, ids, strings, inputs, seen = [], [], [], [], set()
        env = readonly_lmdb(path)
        try:
            selected_rows, selection = select_vibrational_rows(env, self.args.limit, self.args.sampling, self.args.seed)
            for row in selected_rows:
                    molecule = Chem.MolFromSmiles(row["kekule_smiles"])
                    if molecule is None:
                        raise ValueError("Invalid reference structure")
                    identity = Chem.MolToSmiles(molecule, isomericSmiles=True)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    rows.append(row)
                    ids.append(identity)
                    strings.append(Chem.MolToSmiles(molecule, isomericSmiles=True, kekuleSmiles=True))
                    inputs.append(self.service._vib2mol_input(SpectralInput(
                        ir=np.asarray(row["ir"], dtype=np.float32),
                        raman=np.asarray(row["raman"], dtype=np.float32),
                        nmr_h=np.asarray(row["nmr_h_shifts_ppm"], dtype=np.float32) if include_nmr else None,
                        nmr_c=np.asarray(row["nmr_c_shifts_ppm"], dtype=np.float32) if include_nmr else None), device))
                    if include_nmr:
                        expected_ref = json.loads(self.service.assets.nmr_normalizer.read_text())["reference_id"]
                        if row.get("nmr_reference_id") != expected_ref:
                            raise ValueError("Vib2Mol input/checkpoint NMR reference mismatch")
        finally:
            env.close()
        if not rows:
            raise ValueError("Empty vibrational test pool")
        provenance = {"dataset": self.artifact(path), "sample_ids": ids, "given_nmr": include_nmr,
                      "given_formula": False, "inference_mode": "direct_checkpoint",
                      "sampling": self.args.sampling, "seed": self.args.seed, "selection": selection,
                      "source_counts": dict(__import__('collections').Counter(row.get('source_dataset','unknown') for row in rows)),
                      "record_ids": [row.get('sample_id',row['_lmdb_key']) for row in rows]}
        tokens = tokenizer(strings, padding=True, truncation=False, return_tensors="pt")
        if tokens["input_ids"].shape[1] > tokenizer.model_max_length or (tokens["input_ids"] == tokenizer.unk_token_id).any():
            raise ValueError("Reference structures exceed tokenizer capacity or contain unknown tokens")
        checkpoint = self.service.assets.generation_checkpoint if phase == 2 else self.service.assets.retrieval_checkpoint
        provenance["checkpoint"] = self.artifact(checkpoint)
        if phase == 2:
            if include_nmr:
                from benchmarks.models.vib2mol.evaluate_multimodal import canonical, unique_candidates
                rank_model, rank_tokenizer, _ = self.service._load_vib2mol(1)
                for key in ("center", "scale"):
                    if not torch.equal(getattr(rank_model.spectral_encoding, key), getattr(model.spectral_encoding, key)):
                        raise ValueError("Generation/reranking checkpoint NMR normalization differs")
                beam = self.args.vib_beam_size
                hits, reranked_hits = ({k: 0 for k in (1, 3, 5, 10)} for _ in range(2))
                valid_beams, total_beams, duplicates, predictions = 0, 0, 0, []
                with torch.inference_mode():
                    for row, data in zip(rows, inputs):
                        sequences = model.beam_infer_lm(data, beam_size=beam, max_len=300)["pred_ids"][0]
                        raw = [tokenizer.decode(sequence, skip_special_tokens=True).replace(" ", "") for sequence in sequences]
                        candidates = unique_candidates(raw)
                        valid_count = sum(canonical(value) is not None for value in raw)
                        valid_beams += valid_count
                        total_beams += len(raw)
                        duplicates += valid_count - len(candidates)
                        order, probabilities = rerank_candidates(rank_model, rank_tokenizer, data, candidates[:10], self.args.batch_size)
                        ranked = [candidates[index] for index in order] + candidates[10:]
                        target = canonical(row["kekule_smiles"])
                        for k in hits:
                            hits[k] += int(target in candidates[:k])
                            reranked_hits[k] += int(target in ranked[:k])
                        predictions.append({"target": target, "raw_beams": raw, "unique_candidates": candidates,
                                            "reranked": ranked, "positive_probabilities": probabilities})
                return {**provenance, "metrics": {**{f"exact_canonical_top{k}": count / len(rows) for k, count in hits.items()},
                                                  "valid_smiles_fraction": valid_beams / max(total_beams, 1),
                                                  "duplicate_valid_beams": duplicates, "examples": len(rows)},
                        "reranked_metrics": {f"exact_canonical_top{k}": count / len(rows) for k, count in reranked_hits.items()},
                        "ranking": "Xinyu canonical valid unique beams, then ITM positive probability top10 reranking",
                        "beam_size": beam, "max_length": 300, "rank_checkpoint": self.artifact(self.service.assets.retrieval_checkpoint),
                        "predictions": predictions}
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
        def ranked_examples(scores):
            return [{"sample_id": rows[i].get("sample_id", rows[i]["_lmdb_key"]),
                     "input": {"ir": np.asarray(rows[i]["ir"]).tolist(),
                               "raman": np.asarray(rows[i]["raman"]).tolist(),
                               "nmr_h_shifts_ppm": np.asarray(rows[i]["nmr_h_shifts_ppm"]).tolist() if include_nmr else [],
                               "nmr_c_shifts_ppm": np.asarray(rows[i]["nmr_c_shifts_ppm"]).tolist() if include_nmr else []},
                     "reference_smiles": ids[i],
                     "ranked_candidates": [{"smiles": ids[j], "score": float(scores[i,j]), "reference_match": ids[j]==ids[i]}
                                           for j in np.argsort(-scores[i], kind="stable")[:10]]}
                    for i in range(min(3,len(rows)))]
        if task.backend == "vib2mol_reranking":
            scores = np.empty((len(rows), len(rows)))
            with torch.inference_mode():
                for index, data in enumerate(inputs):
                    order, ranked = rerank_candidates(model, tokenizer, data, strings, self.args.batch_size)
                    scores[index, order] = ranked
            metrics = retrieval_metrics(scores, ids, ids)
            metrics["top_1_hit_rate"] = metrics["recall_at_1"]
            return {**provenance, "metrics": metrics, "ranking": "itm_positive_probability", "examples": ranked_examples(scores)}
        with torch.inference_mode():
            molecule_ids = tokens["input_ids"].to(device)
            mask = tokens["attention_mask"].to(device)
            mask = torch.cat((mask.new_ones((len(mask), 1)), mask), dim=1)
            molecular = functional.normalize(model.molecular_encoder(
                model.molecular_encoding(molecule_ids, use_cls_token=True), mask=mask)["proj_output"], dim=-1)
            spectral = functional.normalize(torch.cat([encode_spectra(model, data)["proj_output"] for data in inputs]), dim=-1)
            scores = (spectral @ molecular.T).cpu().numpy()
        return {**provenance, "metrics": retrieval_metrics(scores, ids, ids),
                "examples": ranked_examples(scores),
                "reverse_metrics": retrieval_metrics(scores.T, ids, ids)}

    def vibrational_forward(self):
        from openmolspec_ui.config import discover_assets
        from openmolspec_ui.inference import OpenMolSpecService
        from openmolspec_ui.chemistry import molecule_from_xyz
        from openmolspec_ui.spectra import minmax
        from rdkit import Chem

        if self.service is None:
            self.service = OpenMolSpecService(discover_assets(self.args.portable_root), device=self.args.device)
        self.service._add_project_paths()
        from openmolspec.parsing.gaussian import GaussianLogParser
        paths = self.args.forward_logs or sorted((Path(__file__).resolve().parents[1] / "tests/fixtures").glob("*.log"))
        if not paths:
            raise MissingAsset("No paired Gaussian geometry/spectrum logs")
        records = []
        for path in paths[:self.args.limit]:
            require(path)
            parser = GaussianLogParser(str(path), path.stem)
            if parser.error_type is not None:
                raise ValueError(f"Cannot parse paired Gaussian log {path}: {parser.error_message}")
            row = parser.properties
            coordinates = np.asarray(row["coordinate"]).reshape(-1, 3)
            numbers = np.asarray(row["atom"])
            xyz = [str(len(numbers)), "Exact source Gaussian coordinates, Angstrom"]
            for number, position in zip(numbers, coordinates):
                xyz.append(Chem.GetPeriodicTable().GetElementSymbol(int(number)) + " " + " ".join(f"{value:.12f}" for value in position))
            molecule = molecule_from_xyz("\n".join(xyz) + "\n")
            if not np.allclose(np.asarray(molecule.mol.GetConformer().GetPositions()), coordinates, atol=1e-7):
                raise ValueError("Geometry changed while preparing the paired forward input")
            prediction = self.service.predict_spectra(molecule)
            metrics = {}
            for channel in ("ir", "raman"):
                target = minmax(np.asarray(row[channel], dtype=np.float32))
                output = np.asarray(prediction[channel], dtype=np.float32)
                denominator = float(np.linalg.norm(output) * np.linalg.norm(target))
                metrics[f"{channel}_cosine_similarity"] = float(output @ target / denominator) if denominator else 0.
                metrics[f"{channel}_mae"] = float(np.mean(np.abs(output - target)))
            records.append({"sample_id": path.stem, "input": self.artifact(path), "atoms": len(numbers),
                            "metrics": metrics, "wavenumber_cm1": prediction["wavenumber"].tolist(),
                            "predicted_ir": prediction["ir"].tolist(), "predicted_raman": prediction["raman"].tolist(),
                            "reference_ir": minmax(np.asarray(row["ir"], dtype=np.float32)).tolist(),
                            "reference_raman": minmax(np.asarray(row["raman"], dtype=np.float32)).tolist()})
        return {"metrics": {name: float(np.mean([row["metrics"][name] for row in records])) for name in records[0]["metrics"]},
                "examples": len(records), "records": records, "geometry": "exact_paired_Gaussian_geometry_no_conformer_generation",
                "dataset_scope": "two_existing_real_log_examples_by_default_not_an_audited_held_out_benchmark",
                "checkpoints": {name: self.artifact(getattr(self.service.assets, name)) for name in
                                ("hessian_hi_checkpoint", "hessian_hij_checkpoint", "dedipole_checkpoint", "depolar_checkpoint")}}

    def run(self, task, dataset):
        if not task.enabled:
            raise MissingAsset("Deferred by the user's explicit scope change; no inference requested")
        if task.backend.startswith("spec2struct"):
            return self.nmr(task, dataset)
        if task.backend == "nmrnet_predictions":
            return self.forward(task, dataset)
        if task.backend == "nmrnet_hetero_predictions":
            return self.hetero(task)
        if task.backend == "transpeaknet":
            if self.args.transpeaknet_source is None:
                raise MissingAsset('Supply --transpeaknet-source with the author 2dNMR checkout')
            from .hsqc_evaluation import run
            return run(self)
        if task.backend == "nmrnet_atom_assignment":
            import subprocess
            import tempfile
            path = require(self.args.workspace / "data/align_eval" / dataset / "test.jsonl")
            with tempfile.TemporaryDirectory(prefix="openmolspec-assignment-run-") as directory:
                output = Path(directory)/"result.json"
                command = [self.args.nmr_python, "-m", "openmolspec_bench.assignment",
                           "--models-root", str(self.args.models_root), "--dataset-jsonl", str(path),
                           "--nucleus", self.args.assignment_nucleus, "--limit", str(self.args.limit),
                           "--output", str(output)]
                done = subprocess.run(command, cwd=Path(__file__).resolve().parents[1])
                if done.returncode or not output.is_file():
                    raise RuntimeError("Frozen atom assignment did not complete")
                result = json.loads(output.read_text())
                if not result.get("completed"):
                    raise RuntimeError("Incomplete atom assignment report")
                return result
        if task.backend == "nmr_solvent_reference":
            from .solvent_transfer import evaluate
            library_path = require(self.args.solvent_library)
            library = json.loads(library_path.read_text())
            result = evaluate(library, self.args.limit, self.args.seed)
            result['library'] = self.artifact(library_path)
            return result
        if task.backend == "nmrnet_bsi_diagnostic":
            import subprocess
            import tempfile
            if 'bsi_diagnostic' not in self.encoded:
                with tempfile.TemporaryDirectory(prefix="openmolspec-bsi-run-") as directory:
                    destination = Path(directory)/'run'
                    root = Path(__file__).resolve().parents[1]
                    command = [self.args.nmr_python, str(root/'scripts/run_frozen_bsi_diagnostic.py'),
                               '--models-root', str(self.args.models_root), '--output', str(destination),
                               '--limit', str(self.args.limit)]
                    done = subprocess.run(command, cwd=root)
                    if done.returncode or not (destination/'result.json').is_file():
                        raise RuntimeError('B/Si frozen inference did not complete')
                    payload = json.loads((destination/'result.json').read_text())
                    if not payload.get('completed'):
                        raise RuntimeError('Incomplete B/Si diagnostic')
                    self.encoded['bsi_diagnostic'] = payload
            payload = self.encoded['bsi_diagnostic']
            symbol = {'11B':'B','29Si':'Si'}[task.modalities[0]]
            row = payload['nuclei'][symbol]
            return {'metrics': {k: row[k] for k in ('mae_ppm','rmse_ppm')},
                    'molecules':row['molecules'], 'records':row['records'],
                    'score_scope':'diagnostic_only', 'primary_score_eligible':False,
                    'checkpoint_sha256':payload['checkpoint_sha256'], 'checkpoint':payload['checkpoint'],
                    'manifest':row['manifest'], 'limitations':payload['limitations']}
        if task.backend == "studio_gap":
            return self.gap(task)
        if task.backend == "studio_vibrational_forward":
            return self.vibrational_forward()
        if task.backend.startswith("vib2mol_"):
            return self.vibrational(task)
        if task.backend.startswith("ms_pretrained_") or task.backend == "magma_algorithm":
            import subprocess
            import tempfile
            import os
            module = "openmolspec_bench.magma" if task.backend == "magma_algorithm" else "openmolspec_bench.ms"
            parent = self.args.workspace.parent
            csv_path = self.args.ms_input_csv or parent / "MassSpecGym-MAGMA-annotation/data/MassSpecGym_test_full.csv"
            metadata = self.args.ms_metadata_tsv or parent / "MassSpecGym-MAGMA-annotation/data/MassSpecGym1.5.tsv"
            require(csv_path)
            require(metadata)
            with tempfile.TemporaryDirectory(prefix="openmolspec-ms-eval-") as directory:
                output = Path(directory) / "result.json"
                command = [self.args.ms_python, "-m", module, "--input-csv", str(csv_path), "--metadata-tsv", str(metadata),
                           "--limit", str(self.args.limit), "--output", str(output)]
                if task.backend == "magma_algorithm":
                    command.extend(["--source", str(self.args.magma_source or parent / "MassSpecGym-MAGMA-annotation")])
                else:
                    command.extend(["--model", task.id.split(".")[-1], "--source", str(self.args.ms_source or parent / "ms-pred-repro"),
                                    "--weights", str(self.args.ms_weights or parent / "mspred"), "--device", self.args.device])
                environment = dict(os.environ, MPLCONFIGDIR="/tmp/openmolspec-mpl", NUMBA_CACHE_DIR="/tmp/openmolspec-numba",
                                   OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS=str(self.args.threads))
                completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=environment)
                if completed.returncode or not output.is_file():
                    raise RuntimeError(f"Frozen MS adapter failed with exit code {completed.returncode}")
                result = json.loads(output.read_text())
                if not result.get("completed") or result.get("counts", {}).get("failed"):
                    raise RuntimeError("MS adapter has incomplete/failed records")
                return result
        raise MissingAsset(task.note)

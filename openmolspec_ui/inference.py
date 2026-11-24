from __future__ import annotations

import json
import os
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lmdb
import numpy as np
from rdkit import Chem

from .chemistry import MoleculeInput, molecule_to_pyg
from .config import ModelAssets
from .spectra import SpectralInput
from .theoretical import reconstruct_spectra


class ModelUnavailable(RuntimeError):
    pass


def resolve_device(device: str | None = None) -> str:
    requested = device or os.environ.get("OPENMOLSPEC_DEVICE", "auto")
    if requested == "auto":
        import torch

        return "cuda:0" if torch.cuda.is_available() else "cpu"
    return requested


@dataclass
class _DatasetIndex:
    ir: np.ndarray
    raman: np.ndarray
    nmr_h: list[np.ndarray]
    nmr_c: list[np.ndarray]
    records: list[dict[str, Any]]


class OpenMolSpecService:
    """Local inference facade over the adjacent OpenMolSpec workspace."""

    def __init__(self, assets: ModelAssets, device: str | None = None):
        self.assets = assets
        self.device = resolve_device(device)
        self._gap_bundle: tuple[Any, dict[str, Any]] | None = None
        self._tensor_bundles: dict[str, Any] = {}
        self._qm9s_profile = None
        self._nmr_bundle: tuple[Any, dict[str, Any]] | None = None
        self._dataset: _DatasetIndex | None = None
        self._vib2mol_bundles: dict[int, tuple[Any, Any, str]] = {}
        self._molecular_embeddings: Any | None = None

    def preload(self) -> dict[str, str]:
        """Load every production model before the first page is served.

        Models without available checkpoints are skipped so the UI can still
        start in demo mode (capability_status() reflects what is missing).
        """
        import torch

        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(
                f"OPENMOLSPEC_DEVICE={self.device}, but CUDA is unavailable. "
                "Set OPENMOLSPEC_DEVICE=auto or cpu."
            )
        loaded: dict[str, str] = {}
        optional_loaders = {
            "theoretical_hessian_hi": lambda: self._load_tensor_model("Hi"),
            "theoretical_hessian_hij": lambda: self._load_tensor_model("Hij"),
            "theoretical_dedipole": lambda: self._load_tensor_model("dedipole"),
            "theoretical_depolar": lambda: self._load_tensor_model("depolar"),
            "structure_to_nmr": self._load_nmr,
            "spectrum_to_gap": self._load_gap,
        }
        for name, loader in optional_loaders.items():
            try:
                loader()
            except ModelUnavailable:
                continue
            loaded[name] = self.device
        if self._direct_vib2mol_enabled():
            try:
                self._load_vib2mol(1)
                self._load_vib2mol(2)
            except ModelUnavailable:
                pass
            else:
                loaded.update(
                    {
                        "vib2mol_retrieval": self.device,
                        "vib2mol_generation": self.device,
                    }
                )
        return loaded

    def _add_project_paths(self) -> None:
        # Resolve the running SDK first. Portable bundles also contain an SDK
        # snapshot, alongside the upstream model implementations we need here.
        for path in (self.assets.root / "src", self.assets.root):
            value = str(path)
            if value not in sys.path:
                sys.path.append(value)

    def _load_gap(self):
        if self._gap_bundle is not None:
            return self._gap_bundle
        if self.assets.gap_checkpoint is None:
            raise ModelUnavailable("没有发现 HOMO–LUMO gap checkpoint。")
        self._add_project_paths()
        import torch
        from benchmarks.models.vib2conf.model import SpectralPropsModel

        payload = torch.load(
            self.assets.gap_checkpoint, map_location="cpu", weights_only=False
        )
        metadata = payload["model_metadata"]
        model = SpectralPropsModel(
            property_targets=tuple(metadata["targets"]),
            modality=metadata["modality"],
            **metadata["parameters"],
        )
        model.load_state_dict(payload["state_dict"])
        payload.pop("state_dict")
        model.to(self.device).eval()
        self._gap_bundle = (model, payload)
        return self._gap_bundle

    @staticmethod
    def _spectrum_tensor(values: np.ndarray | None):
        import torch

        if values is None:
            return torch.zeros((1, 1024), dtype=torch.float32)
        return torch.as_tensor(values, dtype=torch.float32).reshape(1, 1024)

    def predict_gap(self, inputs: SpectralInput) -> dict[str, Any]:
        inputs.require_vibrational_spectrum()
        import torch

        if all(v is None or not len(v) for v in (inputs.nmr_h, inputs.nmr_c)):
            from .gap_partial import predict
            return predict(inputs.ir, inputs.raman)
        model, payload = self._load_gap()
        batch: dict[str, Any] = {
            "ir": self._spectrum_tensor(inputs.ir).to(self.device),
            "raman": self._spectrum_tensor(inputs.raman).to(self.device),
        }
        for label, values in (("h", inputs.nmr_h), ("c", inputs.nmr_c)):
            if values is None:
                continue
            tensor = torch.as_tensor(
                values, dtype=torch.float32, device=self.device
            ).reshape(1, -1)
            batch[f"nmr_{label}_shifts_ppm"] = tensor
            batch[f"nmr_{label}_mask"] = torch.ones_like(tensor, dtype=torch.bool)
        with torch.inference_mode():
            normalized = model(batch)["gap"]
        mean = float(payload["normalizer"]["mean"]["gap"])
        std = float(payload["normalizer"]["std"]["gap"])
        prediction = float(normalized.item() * std + mean)
        return {
            "gap_ev": prediction,
            "unit": "eV",
            "input_modalities": [label for label, value in (("IR", inputs.ir), ("Raman", inputs.raman),
                                                            ("1H", inputs.nmr_h), ("13C", inputs.nmr_c)) if value is not None and len(value)],
            "training_modality": payload["model_metadata"]["modality"],
        }

    def _load_tensor_model(self, target: str):
        if target in self._tensor_bundles:
            return self._tensor_bundles[target]
        checkpoints = {
            "Hi": self.assets.hessian_hi_checkpoint,
            "Hij": self.assets.hessian_hij_checkpoint,
            "dedipole": self.assets.dedipole_checkpoint,
            "depolar": self.assets.depolar_checkpoint,
        }
        checkpoint = checkpoints[target]
        if checkpoint is None:
            raise ModelUnavailable(f"没有发现理论谱 {target} checkpoint。")
        self._add_project_paths()
        import torch
        import yaml
        from benchmarks.models.equiformer_v3.hessian import DirectHessianModel

        config_path = checkpoint.parent.parent / "resolved_config.yaml"
        if not config_path.is_file():
            raise ModelUnavailable(f"理论谱 checkpoint 缺少训练配置：{config_path}")
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if config["task"]["targets"] != [target]:
            raise ModelUnavailable(f"理论谱 checkpoint target 与 {target} 不一致。")
        parameters = config["model"].get("parameters", {})
        model = DirectHessianModel((target,), parameters)
        payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
        model.load_state_dict(payload["state_dict"])
        model.to(self.device).eval()
        self._tensor_bundles[target] = model
        return model

    def _load_theoretical_models(self) -> dict[str, Any]:
        return {
            target: self._load_tensor_model(target)
            for target in ("Hi", "Hij", "dedipole", "depolar")
        }

    @staticmethod
    def _radius_graph(molecule: MoleculeInput, cutoff: float = 5.0):
        import torch

        data = molecule_to_pyg(molecule)
        distances = torch.cdist(data.pos, data.pos)
        connected = (distances > 0) & (distances < cutoff)
        data.edge_index = connected.nonzero(as_tuple=False).T.contiguous()
        if data.edge_index.shape[1] == 0:
            raise ValueError("该构象在 5 Å 截断内没有原子邻接边。")
        return data

    def predict_spectra(self, molecule: MoleculeInput, *, include_nmr: bool = True, reference_profile: str = "openspec",
                        include_qm9s_modes: bool = False) -> dict[str, Any]:
        import torch
        from torch_geometric.data import Batch

        if reference_profile not in ("openspec", "qm9s"):
            raise ValueError("Unknown IR/Raman reference profile")
        if reference_profile == "qm9s":
            from importlib.resources import files
            from openmolspec_bench.vibrational_profile import apply_profile, checkpoint_hashes
            if (molecule.mol.GetNumHeavyAtoms() > 9 or
                    any(a.GetSymbol() not in {"H", "C", "N", "O", "F"} for a in molecule.mol.GetAtoms())):
                raise ValueError("The QM9S convention covers H/C/N/O/F molecules with up to nine heavy atoms")
            if self._qm9s_profile is None:
                with files("openmolspec").joinpath("assets/qm9s-profile.json").open() as f:
                    profile = json.load(f)
                if checkpoint_hashes(self.assets) != profile["checkpoints"]:
                    raise ValueError("QM9S profile and tensor checkpoints differ")
                self._qm9s_profile = profile
        models = self._load_theoretical_models()
        from benchmarks.engines.hessian_physics import assemble

        data = self._radius_graph(molecule)
        positions = data.pos.numpy()
        atomic_numbers = data.atomic_numbers.numpy()
        edges = data.edge_index.numpy()
        batch = Batch.from_data_list([data]).to(self.device)
        with torch.inference_mode():
            tensors = {
                target: model(batch)[target].cpu().numpy()
                for target, model in models.items()
            }
        hessian = assemble(tensors["Hi"], tensors["Hij"], edges)
        result = reconstruct_spectra(
            hessian,
            positions,
            atomic_numbers,
            tensors["dedipole"],
            tensors["depolar"],
            qm9s_modes=include_qm9s_modes or reference_profile == "qm9s",
        )
        if reference_profile == "qm9s":
            result.update(apply_profile(result, self._qm9s_profile["profile"], self._qm9s_profile.get("sources")))
            result["reference_profile"] = "qm9s"
        if include_nmr:
            result.update(self.predict_nmr(molecule))
        return result

    def _load_nmr(self):
        if self._nmr_bundle is not None:
            return self._nmr_bundle
        if self.assets.nmr_checkpoint is None:
            raise ModelUnavailable("没有发现结构到 H/C NMR 的 Equiformer checkpoint。")
        self._add_project_paths()
        import torch
        from benchmarks.models.equiformer_v3.nmr import AtomNMRModel

        payload = torch.load(
            self.assets.nmr_checkpoint, map_location="cpu", weights_only=False
        )
        metadata = payload["model_metadata"]
        model = AtomNMRModel(
            targets=tuple(metadata.get("targets", ("H", "C"))),
            backbone=metadata.get("backbone"),
        )
        model.load_state_dict(payload["state_dict"])
        payload.pop("state_dict")
        model.to(self.device).eval()
        self._nmr_bundle = (model, payload)
        return self._nmr_bundle

    def predict_nmr(self, molecule: MoleculeInput) -> dict[str, np.ndarray]:
        import torch
        from torch_geometric.data import Batch

        model, payload = self._load_nmr()
        data = self._radius_graph(molecule)
        batch = Batch.from_data_list([data]).to(self.device)
        with torch.inference_mode():
            output = model(batch)
        result: dict[str, np.ndarray] = {}
        for label in ("H", "C"):
            atomic_number = 1 if label == "H" else 6
            mask = batch.atomic_numbers == atomic_number
            normalized = output[label].squeeze(-1)[mask]
            prediction = (
                normalized * float(payload["normalizer"]["std"][label])
                + float(payload["normalizer"]["mean"][label])
            )
            result[f"nmr_{label.lower()}"] = np.sort(
                prediction.cpu().numpy().astype(np.float32)
            )
        return result

    def _load_dataset(self) -> _DatasetIndex:
        if self._dataset is not None:
            return self._dataset
        if self.assets.spectrum_lmdb is None:
            raise ModelUnavailable("没有发现用于检索的 OpenMolSpec test LMDB。")
        from openmolspec_bench.data import readonly_lmdb
        environment = readonly_lmdb(self.assets.spectrum_lmdb)
        ir, raman, nmr_h, nmr_c, records = [], [], [], [], []
        with environment.begin() as transaction:
            for key, value in transaction.cursor():
                item = pickle.loads(value)
                ir.append(np.asarray(item["ir"], dtype=np.float16))
                raman.append(np.asarray(item["raman"], dtype=np.float16))
                nmr_h.append(
                    np.asarray(item.get("nmr_h_shifts_ppm", []), dtype=np.float32)
                )
                nmr_c.append(
                    np.asarray(item.get("nmr_c_shifts_ppm", []), dtype=np.float32)
                )
                records.append(
                    {
                        "sample_id": item.get("sample_id", key.decode()),
                        "smiles": item["kekule_smiles"],
                        "inchikey": item.get("inchikey", ""),
                        "source": item.get("source_dataset", ""),
                    }
                )
        environment.close()
        self._dataset = _DatasetIndex(
            ir=np.stack(ir),
            raman=np.stack(raman),
            nmr_h=nmr_h,
            nmr_c=nmr_c,
            records=records,
        )
        return self._dataset

    @staticmethod
    def _cosine_scores(matrix: np.ndarray, query: np.ndarray) -> np.ndarray:
        query = np.asarray(query, dtype=np.float32)
        query_norm = max(float(np.linalg.norm(query)), 1e-8)
        scores = np.empty(matrix.shape[0], dtype=np.float32)
        for start in range(0, matrix.shape[0], 2048):
            chunk = matrix[start : start + 2048].astype(np.float32)
            norms = np.maximum(np.linalg.norm(chunk, axis=1), 1e-8)
            scores[start : start + len(chunk)] = (chunk @ query) / (
                norms * query_norm
            )
        return scores

    def nearest_indices(self, inputs: SpectralInput, limit: int = 8):
        inputs.require_vibrational_spectrum()
        dataset = self._load_dataset()
        channels = []
        if inputs.ir is not None:
            channels.append(self._cosine_scores(dataset.ir, inputs.ir))
        if inputs.raman is not None:
            channels.append(self._cosine_scores(dataset.raman, inputs.raman))
        if inputs.nmr_h is not None and len(inputs.nmr_h):
            channels.append(
                self._nmr_scores(dataset.nmr_h, inputs.nmr_h, tolerance=0.20)
            )
        if inputs.nmr_c is not None and len(inputs.nmr_c):
            channels.append(
                self._nmr_scores(dataset.nmr_c, inputs.nmr_c, tolerance=2.0)
            )
        scores = np.mean(np.stack(channels), axis=0)
        limit = min(max(int(limit), 1), len(scores))
        selected = np.argpartition(scores, -limit)[-limit:]
        selected = selected[np.argsort(scores[selected])[::-1]]
        return dataset, selected, scores

    @staticmethod
    def _nmr_scores(
        candidates: list[np.ndarray], query: np.ndarray, tolerance: float
    ) -> np.ndarray:
        """Score unassigned peak sets with a symmetric Gaussian Chamfer match."""
        query = np.asarray(query, dtype=np.float32)
        scores = np.zeros(len(candidates), dtype=np.float32)
        for index, candidate in enumerate(candidates):
            if len(candidate) == 0:
                continue
            distances = np.abs(query[:, None] - candidate[None, :])
            query_match = np.exp(-0.5 * (distances.min(axis=1) / tolerance) ** 2)
            candidate_match = np.exp(-0.5 * (distances.min(axis=0) / tolerance) ** 2)
            scores[index] = 0.5 * (query_match.mean() + candidate_match.mean())
        return scores

    def retrieve(self, inputs: SpectralInput, limit: int = 8) -> list[dict[str, Any]]:
        return self._retrieve_vib2mol(inputs, limit)

    def _direct_vib2mol_enabled(self) -> bool:
        return True

    def _load_vib2mol(self, phase: int):
        if phase in self._vib2mol_bundles:
            return self._vib2mol_bundles[phase]
        checkpoint = (
            self.assets.retrieval_checkpoint
            if phase == 1
            else self.assets.generation_checkpoint
        )
        if checkpoint is None or self.assets.nmr_normalizer is None:
            raise ModelUnavailable("Vib2Mol checkpoint 或 NMR normalizer 不完整。")
        self._add_project_paths()
        upstream = self.assets.root / "benchmarks/models/vib2mol/upstream"
        if str(upstream) not in sys.path:
            sys.path.insert(0, str(upstream))
        import torch
        from transformers import AutoTokenizer
        from benchmarks.models.vib2mol.train_entry import install_adapters
        from models import build_model

        normalizer = json.loads(self.assets.nmr_normalizer.read_text())
        install_adapters("ir-raman-nmr", normalizer)
        model = build_model("vib2mol", phase=phase)
        try:
            state = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
        except (RuntimeError, OSError) as error:
            if "mmap" not in str(error).lower() and "no such device" not in str(error).lower():
                raise
            state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        state = {key.removeprefix("module."): value for key, value in state.items()}
        model.load_state_dict(state, strict=True, assign=True)
        device = self.device
        model.to(device).eval()
        tokenizer = AutoTokenizer.from_pretrained(
            upstream / "models/MolTokenizer", local_files_only=True
        )
        self._vib2mol_bundles[phase] = (model, tokenizer, device)
        return self._vib2mol_bundles[phase]

    @staticmethod
    def _vib2mol_input(inputs: SpectralInput, device: str) -> dict[str, Any]:
        import torch

        result: dict[str, Any] = {
            "ir": OpenMolSpecService._spectrum_tensor(inputs.ir).to(device),
            "raman": OpenMolSpecService._spectrum_tensor(inputs.raman).to(device),
        }
        for label, values in (("c", inputs.nmr_c), ("h", inputs.nmr_h)):
            array = np.asarray(values if values is not None else [], dtype=np.float32)
            tensor = torch.as_tensor(array, dtype=torch.float32, device=device).reshape(1, -1)
            result[f"nmr_{label}_shifts_ppm"] = tensor
            result[f"nmr_{label}_mask"] = torch.ones_like(tensor, dtype=torch.bool)
        return result

    def _retrieve_vib2mol(
        self, inputs: SpectralInput, limit: int
    ) -> list[dict[str, Any]]:
        inputs.require_vibrational_spectrum()
        import torch
        import torch.nn.functional as functional

        model, tokenizer, device = self._load_vib2mol(1)
        from benchmarks.models.vib2mol.evaluate_multimodal import encode_spectra

        dataset = self._load_dataset()
        if self._molecular_embeddings is None:
            batches = []
            with torch.inference_mode():
                for start in range(0, len(dataset.records), 128):
                    smiles = [
                        item["smiles"] for item in dataset.records[start : start + 128]
                    ]
                    tokens = tokenizer(
                        smiles, padding=True, truncation=False, return_tensors="pt"
                    )
                    ids = tokens["input_ids"].to(device)
                    mask = tokens["attention_mask"].to(device)
                    mask = torch.cat((mask.new_ones((len(mask), 1)), mask), dim=1)
                    output = model.molecular_encoder(
                        model.molecular_encoding(ids, use_cls_token=True), mask=mask
                    )["proj_output"]
                    batches.append(functional.normalize(output, dim=-1).cpu())
            self._molecular_embeddings = torch.cat(batches)
        data = self._vib2mol_input(inputs, device)
        with torch.inference_mode():
            query = functional.normalize(
                encode_spectra(model, data)["proj_output"], dim=-1
            ).cpu()
        scores = (query @ self._molecular_embeddings.T).squeeze(0)
        values, indices = scores.topk(min(limit, len(dataset.records)))
        return [
            {
                **dataset.records[int(index)],
                "similarity": float(score),
                "backend": "vib2mol-embedding",
            }
            for index, score in zip(indices.tolist(), values.tolist())
        ]

    def generate(self, inputs: SpectralInput, limit: int = 5, *, ranking="beam",
                 estimate_missing_nmr=True) -> dict[str, Any]:
        from .vib_shift_adapter import supports, with_estimated_shifts

        adapted = estimate_missing_nmr and supports(inputs)
        effective = with_estimated_shifts(inputs) if adapted else inputs
        result = self._generate_vib2mol(effective, max(int(limit), 1), ranking=ranking)
        if adapted:
            result.update(
                input_modalities=["IR", "Raman"],
                estimated_shifts_ppm={"1H": effective.nmr_h.tolist(), "13C": effective.nmr_c.tolist()},
                inference_mode="vibrational_shift_estimation_then_frozen_decoder",
            )
        return result

    def _generate_vib2mol(self, inputs: SpectralInput, limit: int, *, ranking="beam") -> dict[str, Any]:
        inputs.require_vibrational_spectrum()
        if ranking not in ("beam", "itm"):
            raise ValueError("Expected beam or itm ranking")
        import torch

        model, tokenizer, device = self._load_vib2mol(2)
        from benchmarks.models.vib2mol.evaluate_multimodal import unique_candidates

        data = self._vib2mol_input(inputs, device)
        if not 1 <= limit <= 10:
            raise ValueError("Xinyu beam=10 protocol supports 1–10 displayed candidates")
        rank_model, rank_tokenizer, _ = self._load_vib2mol(1)
        for key in ("center", "scale"):
            if not torch.equal(getattr(rank_model.spectral_encoding, key), getattr(model.spectral_encoding, key)):
                raise ValueError("Generation/reranking checkpoint NMR normalization differs")
        beam_size = 10
        with torch.inference_mode():
            sequences = model.beam_infer_lm(
                data, beam_size=beam_size, max_len=300
            )["pred_ids"][0]
        raw = [
            tokenizer.decode(item, skip_special_tokens=True).replace(" ", "")
            for item in sequences
        ]
        candidates = unique_candidates(raw)[:beam_size]
        from .vib_ranking import itm_order, score_generated_candidates

        records = score_generated_candidates(rank_model, rank_tokenizer, data, candidates, 32)
        if ranking == "itm":
            records = itm_order(records)
        return {
            "anchor": None,
            "anchor_similarity": None,
            "anchors_used": 0,
            "beam_size": beam_size,
            "ranking": "canonical_beam_order" if ranking == "beam" else "itm_positive_probability",
            "score_kind": "itm_positive_probability",
            "input_modalities": [name for name, value in (("IR", inputs.ir), ("Raman", inputs.raman),
                                                          ("1H", inputs.nmr_h), ("13C", inputs.nmr_c))
                                 if value is not None and len(value)],
            "candidates": [dict(row, rank=rank) for rank, row in enumerate(records[:limit], 1)],
            "mode": "Canonical beam=10 candidates; score is the ITM positive probability",
        }

    def sample_spectrum(self) -> tuple[SpectralInput, dict[str, Any]]:
        if self.assets.spectrum_lmdb is None:
            raise ModelUnavailable("没有发现 OpenMolSpec 示例数据。")
        from openmolspec_bench.data import readonly_lmdb
        environment = readonly_lmdb(self.assets.spectrum_lmdb)
        with environment.begin() as transaction:
            selected = None
            for key, value in transaction.cursor():
                item = pickle.loads(value)
                if selected is None:
                    selected = (key, item)
                # Use a computed ZINCV2 example so an experimental-database
                # provenance label cannot be mistaken for an experimental spectrum.
                if item.get("source_dataset") == "ZINCV2":
                    selected = (key, item)
                    break
            if selected is None:
                raise ModelUnavailable("OpenMolSpec theoretical test set 为空。")
            key, item = selected
        environment.close()
        record = {
            "sample_id": item.get("sample_id", key.decode()),
            "smiles": item["kekule_smiles"],
            "inchikey": item.get("inchikey", ""),
            "source": item.get("source_dataset", ""),
        }
        return (
            SpectralInput(
                ir=np.asarray(item["ir"], dtype=np.float32),
                raman=np.asarray(item["raman"], dtype=np.float32),
                nmr_h=np.asarray(item.get("nmr_h_shifts_ppm", []), dtype=np.float32),
                nmr_c=np.asarray(item.get("nmr_c_shifts_ppm", []), dtype=np.float32),
            ),
            record,
        )

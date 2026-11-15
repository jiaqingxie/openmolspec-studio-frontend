"""Lazy experimental H/C NMR inference using the existing checkpoints."""

import os
from pathlib import Path


class NMRService:
    def __init__(self, device="cpu"):
        self.device = device
        self.root = Path(os.environ.get("OPENMOLSPEC_BENCH_ROOT", Path(__file__).resolve().parents[2]))
        self.models = {}

    def _load(self, stage):
        from spec2struct_fork.model import ModelConfig, SpectrumToSmiles
        import torch

        defaults = {"align": "f90bd7f743574d18a7f72ae72ce95e59", "generate": "bebaecf2bca248f1a47eaa01f403002a"}
        name = "OPENMOLSPEC_ALIGN_CHECKPOINT" if stage == "align" else "OPENMOLSPEC_GENERATE_CHECKPOINT"
        path = Path(os.environ.get(name, self.root / "runs" / defaults[stage] / "best.pt"))
        if stage not in self.models:
            if not path.is_file():
                raise FileNotFoundError(f"请配置 {name}，未找到 {path}")
            payload = torch.load(path, map_location="cpu", weights_only=True)
            if payload.get("training_stage") != stage:
                raise ValueError(f"{path} 不是 {stage} checkpoint")
            model = SpectrumToSmiles(ModelConfig(**payload["config"]))
            model.load_state_dict(payload["model"])
            self.models[stage] = model.to(self.device).eval()
        return self.models[stage]

    @staticmethod
    def row(h, c, formula=""):
        if not h.strip() and not c.strip():
            raise ValueError("请至少提供一种 NMR 谱峰。")
        return {"formula": formula.strip(),
                "h_nmr": [{"type": "1H NMR", "chemical_shift": h.strip()}] if h.strip() else [],
                "c_nmr": [{"type": "13C NMR", "chemical_shift": c.strip()}] if c.strip() else [],
                "modality_mask": [int(bool(h.strip())), int(bool(c.strip()))]}

    def generate(self, h, c, formula, beam_size=5):
        if not formula.strip():
            raise ValueError("该生成模型需要已知分子式。")
        from spec2struct_fork.model import encode_source
        from spec2struct_fork.structured import encode_structured_source
        from spec2struct_fork.train import rank_candidates

        model = self._load("generate")
        row = self.row(h, c, formula)
        encoder = encode_structured_source if model.config.input_representation == "structured" else encode_source
        source = encoder(row["formula"], row["h_nmr"], row["c_nmr"], row["modality_mask"], model.config.max_source)
        return rank_candidates(model.beam_search(source, beam_size), formula)

    def retrieve(self, h, c, candidates, limit=10):
        import torch
        from rdkit import Chem
        from spec2struct_fork.train import make_collate

        model = self._load("align")
        row = self.row(h, c)
        identities = []
        for candidate in candidates:
            molecule = Chem.MolFromSmiles(candidate.strip())
            if molecule is None or not molecule.GetNumAtoms():
                raise ValueError(f"无效候选 SMILES: {candidate}")
            identity = Chem.MolToSmiles(molecule, isomericSmiles=True)
            if identity not in identities:
                identities.append(identity)
        if not identities:
            raise ValueError("请提供候选 SMILES，每行一个。")
        collate = make_collate(model.config, include_formula=False)
        values = []
        with torch.inference_mode():
            for start in range(0, len(identities), 32):
                chunk = identities[start:start + 32]
                source, target, _ = collate([{**row, "smiles": value} for value in chunk])
                spectra, molecules = model.alignment_embeddings(source.to(self.device), target.to(self.device))
                values.extend((molecules @ spectra[0]).cpu().tolist())
        order = sorted(range(len(values)), key=lambda index: -values[index])[:limit]
        return [{"rank": rank, "smiles": identities[index], "cosine_similarity": values[index],
                 "candidate_pool": len(identities)} for rank, index in enumerate(order, 1)]

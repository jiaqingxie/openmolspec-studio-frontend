"""Xinyu Lu's published two-channel Vib2Mol models for VB-Mols spectra."""

from pathlib import Path
import sys


def native_model(root, gen, device):
    import torch
    from transformers import AutoTokenizer

    sys.path.insert(0, str(root))
    from models import build_model

    with torch.device("meta"):
        model = build_model("vib2mol_mmm", spectral_channel=2)
    folder = "ir-raman-kekule_smiles-formula" if gen else "ir-raman-kekule_smiles"
    run = "2025-12-19-05-56-1b87e2" if gen else "2025-12-16-10-57-6c9c5d"
    path = root / "checkpoints/mols" / folder / "vib2mol_mmm" / run / "epoch999.pth"
    if not path.is_file():
        raise FileNotFoundError(f"Missing released Vib2Mol checkpoint at {path}")
    state = torch.load(path, map_location="cpu", weights_only=True)
    model.load_state_dict(
        {k.removeprefix("module."): v for k, v in state.items()},
        strict=True,
        assign=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(
        root / "models/MolTokenizer", local_files_only=True
    )
    return model.to(device).eval(), tokenizer, path


def generate(inputs, formula, root, limit=10, device="cpu"):
    """Decode valid candidates using IR, Raman and an independently supplied formula."""
    import torch
    from rdkit import Chem, rdBase
    from rdkit.Chem import rdMolDescriptors
    from transformers import AutoTokenizer
    from openmolspec_bench.data import sha256

    if not isinstance(formula, str) or not formula.strip() or not 1 <= limit <= 10:
        raise ValueError("Provide a molecular formula and a candidate limit of 1–10")
    if set(inputs) != {"ir", "raman"}:
        raise ValueError("Provide one IR and one Raman spectrum")
    root = Path(root).resolve()
    data = {}
    for name, values in inputs.items():
        values = torch.as_tensor(values, dtype=torch.float32, device=device)
        if values.shape != (1024,) or not torch.isfinite(values).all():
            raise ValueError(f"{name} requires 1024 finite intensity values")
        if values.min() < 0 or values.max() <= 0:
            raise ValueError(
                f"{name} requires nonnegative intensities and a positive peak"
            )
        data[name] = (values / values.max()).reshape(1, 1, 1024)
    model, tokenizer, path = native_model(root, True, device)
    ft = AutoTokenizer.from_pretrained(
        root / "models/FormulaTokenizer", local_files_only=True
    )
    ids = ft([formula.strip()], return_tensors="pt")
    if (ids.input_ids == ft.unk_token_id).any():
        raise ValueError("The formula contains an unknown token")
    data["formula"] = ids.to(device)
    with torch.inference_mode():
        seq = model.beam_infer_lm(data, beam_size=10, max_len=150, temperature=3.5)[
            "pred_ids"
        ][0]
    candidates = []
    seen = set()
    with rdBase.BlockLogs():
        for item in seq:
            mol = Chem.MolFromSmiles(
                tokenizer.decode(item, skip_special_tokens=True).replace(" ", "")
            )
            if mol is None or not mol.GetNumAtoms():
                continue
            smiles = Chem.MolToSmiles(mol, isomericSmiles=False)
            if smiles in seen:
                continue
            seen.add(smiles)
            candidates.append(
                {
                    "smiles": smiles,
                    "beam_rank": len(candidates) + 1,
                    "formula_match": rdMolDescriptors.CalcMolFormula(mol)
                    == formula.strip(),
                }
            )
    return {
        "model": "Vib2Mol-MMM VB-Mols",
        "given_formula": formula.strip(),
        "input_modalities": ["IR", "Raman"],
        "checkpoint_sha256": sha256(path),
        "ranking": "canonical_beam_order",
        "candidates": candidates[:limit],
    }

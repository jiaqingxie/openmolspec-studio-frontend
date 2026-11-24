"""Combine the author's formula-free IR and Raman decoders with the dual-spectrum matcher."""

import argparse
import gc
import json
from pathlib import Path
import pickle
import sys
import numpy as np
import torch
from transformers import AutoTokenizer
from rdkit import Chem
from .data import readonly_lmdb, sha256
from .expanded_vib import native_model
from .vib_generation_check import canonical, select


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("portable", "native", "legacy", "output", "cache"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--limit", type=int, default=24)
    p.add_argument("--exclude-panel", type=Path)
    a = p.parse_args()
    from filelock import FileLock

    with FileLock(str(a.output.with_name("." + a.output.name + ".lock"))):
        evaluate(a)


def evaluate(a):
    from openmolspec_ui.config import discover_assets

    env = readonly_lmdb(discover_assets(a.portable).spectrum_lmdb)
    excluded = {
        canonical(s)
        for r in json.loads(a.legacy.read_text())["results"]
        for s in r.get("sample_ids", [])
    }
    excluded_keys = set()
    if a.exclude_panel:
        for row in json.loads(a.exclude_panel.read_text())["records"]:
            mol = Chem.MolFromSmiles(row["target"])
            excluded_keys.add(Chem.MolToInchiKey(mol).split("-")[0])
    with env.begin() as tx:
        rows = select(
            (pickle.loads(v) for _, v in tx.cursor()), excluded, a.limit, excluded_keys
        )
    env.close()
    root = a.native.resolve()
    sys.path.insert(0, str(root))
    from models import build_model

    a.cache.mkdir(parents=True, exist_ok=True)
    tok = AutoTokenizer.from_pretrained(
        root / "models/MolTokenizer", local_files_only=True
    )
    labels = [canonical(r["kekule_smiles"]) for r in rows]
    beams = {}
    hashes = {}
    for channel, run in (
        ("ir", "2025-07-10-07-42-dde12a"),
        ("raman", "2025-07-10-07-46-68d484"),
    ):
        path = (
            root
            / "checkpoints/mols"
            / (channel + "-kekule_smiles")
            / "vib2mol"
            / run
            / "epoch999.pth"
        )
        hashes[channel] = sha256(path)
        cache = a.cache / (channel + ".json")
        data = (
            json.loads(cache.read_text())
            if cache.exists()
            else {"checkpoint": hashes[channel], "targets": labels, "beams": []}
        )
        if data["targets"] != labels or data["checkpoint"] != hashes[channel]:
            raise ValueError("Cached protocol differs")
        if len(data["beams"]) < len(rows):
            with torch.device("meta"):
                model = build_model("vib2mol", spectral_channel=1)
            state = torch.load(path, map_location="cpu", weights_only=True)
            model.load_state_dict(
                {k.removeprefix("module."): v for k, v in state.items()},
                strict=True,
                assign=True,
            )
            del state
            model.eval()
            with torch.inference_mode():
                for r in rows[len(data["beams"]) :]:
                    inp = {
                        channel: torch.tensor(
                            np.asarray(r[channel]), dtype=torch.float32
                        ).reshape(1, 1, 1024)
                    }
                    ids = model.beam_infer_lm(
                        inp, beam_size=10, max_len=150, temperature=3.5
                    )["pred_ids"][0]
                    candidates = [
                        canonical(
                            tok.decode(seq, skip_special_tokens=True).replace(" ", "")
                        )
                        for seq in ids
                    ]
                    data["beams"].append(
                        list(dict.fromkeys(s for s in candidates if s))
                    )
                    temp = cache.with_suffix(".tmp")
                    temp.write_text(json.dumps(data))
                    temp.replace(cache)
            del model
            gc.collect()
        beams[channel] = data["beams"]
    rank, tok, path = native_model(root, False, "cpu")
    hashes["dual_itm"] = sha256(path)
    report = dict(
        checkpoints=hashes,
        source="Xinyu VB-Mols modality-specific generators",
        given_formula=False,
        method="Union of two canonical beam-10 lists, ranked by the author's native IR+Raman matching head.",
        records=[],
    )
    with torch.inference_mode():
        for i, r in enumerate(rows):
            pool = list(dict.fromkeys(beams["ir"][i] + beams["raman"][i]))
            scores = []
            for start in range(0, len(pool), 8):
                chunk = pool[start : start + 8]
                text = [
                    Chem.MolToSmiles(
                        Chem.MolFromSmiles(s), kekuleSmiles=True, isomericSmiles=False
                    )
                    for s in chunk
                ]
                inp = {
                    k: torch.tensor(np.asarray(r[k]), dtype=torch.float32)
                    .reshape(1, 1, 1024)
                    .expand(len(chunk), -1, -1)
                    for k in ("ir", "raman")
                }
                inp["smiles"] = tok(text, padding=True, return_tensors="pt")
                scores.extend(rank.matching(inp).softmax(-1)[:, 1].tolist())
            order = sorted(range(len(scores)), key=lambda j: -scores[j])
            report["records"].append(
                dict(target=labels[i], candidates=[pool[j] for j in order])
            )
    report["counts"] = {
        f"top{k}": sum(r["target"] in r["candidates"][:k] for r in report["records"])
        for k in (1, 3, 5, 10)
    }
    report["complete"] = len(report["records"]) == len(rows)
    temp = a.output.with_suffix(".tmp")
    temp.write_text(json.dumps(report, indent=2) + "\n")
    temp.replace(a.output)


if __name__ == "__main__":
    main()

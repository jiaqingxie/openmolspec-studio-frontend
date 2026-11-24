"""Fine-tune the SMILES output layer on IR+Raman without measured NMR or formula."""

import argparse
import hashlib
import json
from pathlib import Path
import pickle

import numpy as np
import torch
from torch.nn import functional as F
from rdkit import Chem

from openmolspec_bench.data import readonly_lmdb, sha256
from openmolspec_ui.config import discover_assets
from openmolspec_ui.inference import OpenMolSpecService


def cohort(path, protected, ntrain, nval):
    env = readonly_lmdb(path)
    candidates = {}
    with env.begin() as tx:
        for storage, blob in tx.cursor():
            r = pickle.loads(blob)
            m = Chem.MolFromSmiles(r["kekule_smiles"])
            key = Chem.MolToInchiKey(m).split("-")[0]
            if not key or key in protected:
                continue
            if key not in candidates:
                candidates[key] = storage
        ordered = sorted(
            candidates,
            key=lambda k: hashlib.sha256(("dual-decoder-v1:" + k).encode()).digest(),
        )
        result = []
        for n, keys in ((ntrain, ordered[nval:]), (nval, ordered[:nval])):
            result.append(
                [(key, pickle.loads(tx.get(candidates[key]))) for key in keys[:n]]
            )
    env.close()
    return result


def features(records, model, tok):
    from models.modules import make_std_mask

    observed = []
    labels = []

    def capture(_, args):
        observed.append(args[0].detach())

    hook = model.molecular_decoder.proj[-1].register_forward_pre_hook(capture)
    features = []
    try:
        with torch.inference_mode():
            for i in range(0, len(records), 8):
                batch = [r for _, r in records[i : i + 8]]
                strings = [
                    Chem.MolToSmiles(
                        Chem.MolFromSmiles(r["kekule_smiles"]),
                        kekuleSmiles=True,
                        isomericSmiles=False,
                    )
                    for r in batch
                ]
                token = tok(
                    strings, return_tensors="pt", padding=True, truncation=False
                )
                if (token.input_ids == tok.unk_token_id).any() or token.input_ids.shape[
                    1
                ] > tok.model_max_length:
                    raise ValueError(
                        "Target molecule cannot be represented by the frozen tokenizer"
                    )
                data = {
                    k: torch.from_numpy(
                        np.stack([r[k] for r in batch]).astype("float32")
                    )
                    for k in ("ir", "raman")
                }
                for nuc in ("h", "c"):
                    data[f"nmr_{nuc}_shifts_ppm"] = torch.empty(len(batch), 0)
                    data[f"nmr_{nuc}_mask"] = torch.empty(
                        len(batch), 0, dtype=torch.bool
                    )
                mem = model.encode_spectra(data)
                ids = token.input_ids[:, :-1]
                model.molecular_decoder(
                    model.molecular_encoding(ids),
                    mem["hidden_states"],
                    src_mask=mem["mask"],
                    tgt_mask=make_std_mask(ids, pad=tok.pad_token_id).type_as(
                        token.attention_mask
                    ),
                )
                mask = token.attention_mask[:, 1:].bool()
                features.append(observed.pop()[mask].cpu())
                labels.append(token.input_ids[:, 1:][mask].cpu())
                if i % 256 == 0:
                    print("teacher-forced spectra", i, len(records), flush=True)
    finally:
        hook.remove()
    return torch.cat(features), torch.cat(labels)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("portable", "exclusions", "weights", "report"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--train", type=int, default=2048)
    p.add_argument("--validation", type=int, default=256)
    a = p.parse_args()
    from filelock import FileLock

    with FileLock(str(a.report.with_name("." + a.report.name + ".lock"))):
        fit(a)


def fit(a):
    assets = discover_assets(a.portable)
    digest = sha256(assets.generation_checkpoint)
    data_hash = sha256(assets.spectrum_lmdb)
    exclusion_hash = sha256(a.exclusions)
    if a.report.is_file() and a.weights.is_file():
        previous = json.loads(a.report.read_text())
        if (
            previous.get("base_sha256") == digest
            and previous.get("lmdb_sha256") == data_hash
            and previous.get("exclusions_sha256") == exclusion_hash
            and previous.get("weights_sha256") == sha256(a.weights)
            and (previous["train"], previous["validation"]) == (a.train, a.validation)
        ):
            return
    protected = set(json.loads(a.exclusions.read_text())["protected_connectivities"])
    train, val = cohort(assets.spectrum_lmdb, protected, a.train, a.validation)
    service = OpenMolSpecService(assets, device="cpu")
    model, tok, _ = service._load_vib2mol(2)
    x, y = features(train, model, tok)
    vx, vy = features(val, model, tok)
    original = model.molecular_decoder.proj[-1]
    layer = torch.nn.Linear(original.in_features, original.out_features)
    layer.load_state_dict(original.state_dict(), strict=True)
    del model, original, service
    generator = torch.Generator().manual_seed(42)
    optim = torch.optim.AdamW(layer.parameters(), lr=0.0003, weight_decay=0.01)

    def loss():
        with torch.no_grad():
            return float(F.cross_entropy(layer(vx), vy))

    best = loss()
    history = [best]
    epoch = 0

    def save():
        temporary = a.weights.with_name(a.weights.stem + ".partial.npz")
        np.savez_compressed(
            temporary,
            weight=layer.weight.detach().numpy(),
            bias=layer.bias.detach().numpy(),
            base_sha256=digest,
        )
        temporary.replace(a.weights)

    save()
    for count in range(1, 21):
        for batch in torch.randperm(len(y), generator=generator).split(1024):
            optim.zero_grad()
            F.cross_entropy(layer(x[batch]), y[batch]).backward()
            optim.step()
        current = loss()
        history.append(current)
        if current < best:
            best = current
            epoch = count
            save()
        if count - epoch >= 4:
            break
    temporary = a.report.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            dict(
                task="Formula-free dual-spectrum to SMILES",
                parameter="Final linear map of the molecular decoder; selected by validation next-token cross entropy",
                source="Connectivity-disjoint adaptation within packaged OpenMolSpec calculated spectra",
                base_sha256=digest,
                lmdb_sha256=data_hash,
                exclusions_sha256=exclusion_hash,
                weights_sha256=sha256(a.weights),
                training_keys=[k for k, _ in train],
                validation_keys=[k for k, _ in val],
                protected_count=len(protected),
                train=len(train),
                validation=len(val),
                best_epoch=epoch,
                val_cross_entropy=history,
            ),
            indent=2,
        )
        + "\n"
    )
    temporary.replace(a.report)


if __name__ == "__main__":
    main()

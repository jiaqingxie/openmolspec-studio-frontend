"""Matched, formula-enriched candidate-library benchmark for Vib2Mol checkpoints."""

import argparse
import hashlib
import os
import tempfile
from collections import defaultdict
import json
from pathlib import Path
import pickle
import random
import numpy as np
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
import torch
import torch.nn.functional as F
from .data import readonly_lmdb, sha256
from openmolspec_ui.vib_native import native_model


def choose(path, n, q, seed, excluded_queries=()):
    env = readonly_lmdb(path)
    universe = {}
    by_formula = defaultdict(list)
    with env.begin() as tx:
        for key, blob in tx.cursor():
            row = pickle.loads(blob)
            mol = Chem.MolFromSmiles(row["kekule_smiles"])
            identity = Chem.MolToSmiles(mol, isomericSmiles=False)
            if identity in universe:
                continue
            formula = rdMolDescriptors.CalcMolFormula(mol)
            by_formula[formula].append(identity)
            universe[identity] = (key, formula)
        rng = random.Random(seed)
        keys = sorted(universe)
        if n > len(keys):
            raise ValueError(
                f"Requested {n} candidates from {len(keys)} distinct structures"
            )
        eligible = [s for s in keys if Chem.MolToInchiKey(Chem.MolFromSmiles(s)).split("-")[0] not in excluded_queries] if excluded_queries else keys
        queries = rng.sample(eligible, q)
        pool = set(queries)
        for s in queries:
            siblings = sorted(set(by_formula[universe[s][1]]) - pool)
            pool.update(rng.sample(siblings, min(4, len(siblings), n - len(pool))))
        pool.update(rng.sample(sorted(set(keys) - pool), n - len(pool)))
        pool = sorted(pool)
        rng.shuffle(pool)
        rows = [pickle.loads(tx.get(universe[s][0])) for s in queries]
    env.close()
    return queries, pool, rows, {s: universe[s][1] for s in pool}


def tokens(tokenizer, strings, device):
    t = tokenizer(strings, padding=True, truncation=False, return_tensors="pt").to(
        device
    )
    if (t.input_ids == tokenizer.unk_token_id).any() or t.input_ids.shape[
        1
    ] > tokenizer.model_max_length:
        raise ValueError("Candidate cannot be represented by the model vocabulary")
    mask = torch.cat((torch.ones_like(t.attention_mask[:, :1]), t.attention_mask), 1)
    return t.input_ids, mask


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--portable", type=Path, required=True)
    p.add_argument("--native", type=Path)
    p.add_argument("--native-weights",type=Path,help="Fine-tuned dual-channel matching checkpoint")
    p.add_argument(
        "--without-nmr",
        action="store_true",
        help="Use only IR and Raman with the project checkpoint",
    )
    p.add_argument("--single", choices=("ir", "raman"), help="Evaluate one vibrational input with the remaining channels missing")
    p.add_argument("--bank-cache", type=Path, help="Reuse normalized candidate embeddings with identical encoder, tokenization, pool and device")
    p.add_argument("--embedding-only", action="store_true", help="Only compute embedding retrieval, without ITM ranks")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--pool", type=int, default=1024)
    p.add_argument("--queries", type=int, default=96)
    p.add_argument("--panel-queries", type=int, help="Construct the original fixed panel with this many queries before scoring its first --queries records")
    p.add_argument("--shortlist", type=int, default=16)
    p.add_argument("--exhaustive", type=int, default=2)
    p.add_argument("--seed", type=int, default=913)
    p.add_argument("--device", default="cpu")
    p.add_argument("--fit-index", type=Path, help="Exclude adapter training and validation connectivities from all queries")
    p.add_argument("--shift-adapter", type=Path, help="Estimate H/C from IR and Raman for the frozen four-channel encoder")
    a = p.parse_args()
    if a.native_weights and not a.native:
        p.error("--native-weights requires --native")
    if not (
        1 <= a.queries <= a.pool
        and 1 <= a.shortlist <= a.pool
        and 0 <= a.exhaustive <= a.queries
    ):
        p.error(
            "Require 1 ≤ queries and shortlist ≤ pool, and 0 ≤ exhaustive ≤ queries"
        )
    panel_size = a.queries if a.panel_queries is None else a.panel_queries
    if not a.queries <= panel_size <= a.pool:
        p.error("The panel must contain all scored queries and fit inside the library")
    if a.embedding_only and a.exhaustive:
        p.error("--embedding-only requires --exhaustive 0")
    if a.single:
        if a.native or a.shift_adapter:
            p.error("Single vibrational input requires the project checkpoint without shift estimation")
        a.without_nmr = True
    if a.native and a.without_nmr:
        p.error("Choose the native dual-spectrum model or the project model")
    if a.shift_adapter and (a.native or not a.without_nmr or not a.fit_index):
        p.error("Estimated shifts require --without-nmr and --fit-index")
    excluded = set()
    if a.fit_index:
        index = json.loads(a.fit_index.read_text())
        excluded.update(index["train"])
        excluded.update(index["val"])
    if a.shift_adapter:
        from openmolspec_ui.vib_shift_adapter import estimate_shifts
        if sha256(a.shift_adapter) != index["weights_sha256"]:
            raise ValueError("Fit index does not describe these adapter weights")
        with np.load(a.shift_adapter, allow_pickle=False) as saved:
            adapter = dict(saved)
    from openmolspec_ui.config import discover_assets

    assets = discover_assets(a.portable)
    queries, pool, rows, formula = choose(
        assets.spectrum_lmdb, a.pool, panel_size, a.seed, excluded
    )
    queries, rows = queries[:a.queries], rows[:a.queries]
    if a.native:
        model, tok, path = native_model(a.native.resolve(), False, a.device)

        if a.native_weights:
            path = a.native_weights
            model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True), strict=True)

        def encode(r):
            data = {
                k: torch.tensor(np.asarray(r[k]), device=a.device)
                .reshape(1, 1, 1024)
                .float()
                for k in ("ir", "raman")
            }
            out = model.get_spectral_embeddings(data)
            out["mask"] = torch.ones(
                out["hidden_states"].shape[:2], device=a.device, dtype=torch.bool
            )
            return out
    else:
        from openmolspec_ui.inference import OpenMolSpecService
        from openmolspec_ui.spectra import SpectralInput

        service = OpenMolSpecService(assets, device=a.device)
        reference = json.loads(assets.nmr_normalizer.read_text())["reference_id"]
        if not a.without_nmr and any(r.get("nmr_reference_id") != reference for r in rows):
            raise ValueError("Query NMR shift reference differs from the trained model")
        model, tok, _ = service._load_vib2mol(1)
        path = assets.retrieval_checkpoint
        from benchmarks.models.vib2mol.evaluate_multimodal import encode_spectra

        def encode(r):
            h, c = (None, None) if a.without_nmr else (r["nmr_h_shifts_ppm"], r["nmr_c_shifts_ppm"])
            if a.shift_adapter:
                h, c = estimate_shifts(r["ir"], r["raman"], adapter)
            data = SpectralInput(
                ir=None if a.single == "raman" else r["ir"],
                raman=None if a.single == "ir" else r["raman"],
                nmr_h=h, nmr_c=c,
            )
            return encode_spectra(model, service._vib2mol_input(data, a.device))

    strings = [
        Chem.MolToSmiles(Chem.MolFromSmiles(s), kekuleSmiles=True, isomericSmiles=False)
        for s in pool
    ]
    report = dict(
        checkpoint_sha256=sha256(path),
        dataset_sha256=sha256(assets.spectrum_lmdb),
        given_formula=False,
        channels=a.single or ("ir_raman" if a.native or a.without_nmr else "ir_raman_hc"),
        pool=pool,
        candidate_identity="canonical SMILES ignoring stereochemistry",
        seed=a.seed,
        shortlist=a.shortlist,
        records=[],
    )
    report["fit_index_sha256"] = sha256(a.fit_index) if a.fit_index else None
    report["shift_adapter_sha256"] = sha256(a.shift_adapter) if a.shift_adapter else None
    report["exhaustive_queries"] = a.exhaustive
    report["query_targets"] = queries
    if a.output.exists():
        old = json.loads(a.output.read_text())
        for name in (
            "checkpoint_sha256",
            "dataset_sha256",
            "channels",
            "pool",
            "query_targets",
            "shortlist",
            "exhaustive_queries",
            "fit_index_sha256",
            "shift_adapter_sha256",
        ):
            if old.get(name) != report[name]:
                raise ValueError(f"Cannot resume a different protocol: {name}")
        if bool(old.get("embedding_only")) != a.embedding_only:
            raise ValueError("Different ranking protocol")
        report = old
        if report.get("complete"):
            return

    report["embedding_only"] = a.embedding_only

    def save():
        for field in ("embedding_rank", "shortlist_itm_rank", "exhaustive_itm_rank"):
            ranks = np.array(
                [x[field] for x in report["records"] if x[field] is not None]
            )
            report[field] = dict(
                queries=len(ranks),
                mrr=float(np.mean(1 / ranks)) if len(ranks) else None,
                **{f"top{k}_hits": int((ranks <= k).sum()) for k in (1, 5, 10)},
            )
        report["complete"] = len(report["records"]) == len(queries)
        temp = a.output.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        temp.replace(a.output)

    with torch.inference_mode():
        def encode_bank():
            embeds = []
            for i in range(0, len(pool), 16):
                ids, mask = tokens(tok, strings[i:i+16], a.device)
                embeds.append(model.molecular_encoder(
                    model.molecular_encoding(ids, use_cls_token=True), mask=mask
                )["proj_output"])
            return F.normalize(torch.cat(embeds))
        if a.bank_cache:
            fingerprint = hashlib.sha256(json.dumps([report["checkpoint_sha256"], strings, tok.get_vocab(),
                                                      a.device, torch.__version__],sort_keys=True).encode()).hexdigest()
            a.bank_cache.mkdir(exist_ok=True, parents=True)
            cachefile=a.bank_cache/(fingerprint+".npy")
            if cachefile.exists():
                bank=torch.from_numpy(np.load(cachefile,allow_pickle=False)).to(a.device)
            else:
                bank=encode_bank()
                with tempfile.NamedTemporaryFile(dir=a.bank_cache,delete=False) as buf:
                    np.save(buf,bank.cpu().numpy(),allow_pickle=False)
                os.replace(buf.name,cachefile)
        else:
            bank=encode_bank()
        for qi, (s, r) in enumerate(zip(queries, rows)):
            if qi < len(report["records"]):
                continue
            spec = encode(r)
            scores = (
                (F.normalize(spec["proj_output"]) @ bank.T).reshape(-1).cpu().numpy()
            )
            order = list(map(int, np.argsort(-scores, kind="stable")))
            target = pool.index(s)
            all_pairs = qi < a.exhaustive
            selected = [] if a.embedding_only else order if all_pairs else order[: a.shortlist]
            itm = {}
            for j in range(0, len(selected), 16):
                batch = selected[j : j + 16]
                ids, mask = tokens(tok, [strings[i] for i in batch], a.device)
                hidden = spec["hidden_states"].expand(len(ids), -1, -1)
                src_mask = spec["mask"].expand(len(ids), -1)
                out = model.molecular_encoder(
                    model.molecular_encoding(ids, use_cls_token=True),
                    memory=hidden,
                    src_mask=src_mask,
                    tgt_mask=mask,
                    multimodal=True,
                )["proj_output"]
                itm.update(zip(batch, out.softmax(-1)[:, 1].cpu().tolist()))
            top = (
                sorted(order[: a.shortlist], key=lambda i: -itm[i])
                + order[a.shortlist :]
            ) if selected else []
            report["records"].append(
                dict(
                    target=s,
                    sample_id=r["sample_id"],
                    embedding_rank=order.index(target) + 1,
                    shortlist_itm_rank=top.index(target) + 1 if top else None,
                    exhaustive_itm_rank=sorted(selected, key=lambda i: -itm[i]).index(
                        target
                    )
                    + 1
                    if all_pairs
                    else None,
                    same_formula_decoys=sum(formula[x] == formula[s] for x in pool) - 1,
                )
            )
            save()
            if qi % 8 == 0:
                print(qi + 1, len(queries), flush=True)


if __name__ == "__main__":
    main()

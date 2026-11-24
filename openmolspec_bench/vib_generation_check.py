"""Compare beam and matching orders on a second structure-disjoint test panel."""

import argparse
import hashlib
import heapq
import json
from pathlib import Path
import pickle
import numpy as np
from rdkit import Chem, rdBase
from rdkit.Chem import rdMolDescriptors
import torch
from .data import readonly_lmdb, sha256
from .expanded_vib import native_model


def canonical(s):
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(s)
    if mol and mol.GetNumAtoms():
        return Chem.MolToSmiles(mol, isomericSmiles=False)


def select(rows, excluded, n, excluded_keys=()):
    seen = set()
    chosen = []
    for r in rows:
        s = canonical(r["kekule_smiles"])
        if not s or s in seen or s in excluded:
            continue
        if (
            excluded_keys
            and Chem.MolToInchiKey(Chem.MolFromSmiles(s)).split("-")[0] in excluded_keys
        ):
            continue
        seen.add(s)
        digest = int.from_bytes(
            hashlib.sha256(("vib-gen-check-v1:" + s).encode()).digest(), "big"
        )
        item = (-digest, s, r)
        if len(chosen) < n:
            heapq.heappush(chosen, item)
        elif item[0] > chosen[0][0]:
            heapq.heapreplace(chosen, item)
    return [item[2] for item in sorted(chosen, reverse=True)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("portable", "legacy", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--native", type=Path)
    p.add_argument("--spectra-only", action="store_true")
    p.add_argument("--adapter", type=Path)
    p.add_argument("--decoder-head", type=Path)
    p.add_argument("--native-test", type=Path)
    p.add_argument(
        "--exclude-panel",
        type=Path,
        help="Exclude every connectivity in a previous panel",
    )
    p.add_argument("--limit", type=int, default=24)
    a = p.parse_args()
    if (a.adapter and not a.spectra_only) or (a.spectra_only and a.native):
        p.error(
            "The shift adapter requires --spectra-only with the OpenMolSpec generator"
        )
    if a.decoder_head and (a.native or not a.spectra_only):
        p.error("--decoder-head requires the dual-spectrum OpenMolSpec generator")
    from filelock import FileLock

    with FileLock(str(a.output.with_name("." + a.output.name + ".lock"))):
        evaluate(a)


def evaluate(a):
    from openmolspec_ui.config import discover_assets

    assets = discover_assets(a.portable)
    previous = json.loads(a.legacy.read_text())["results"]
    excluded = {canonical(s) for r in previous for s in r.get("sample_ids", [])}
    excluded_keys = set()
    if a.exclude_panel:
        for row in json.loads(a.exclude_panel.read_text())["records"]:
            excluded_keys.add(
                Chem.MolToInchiKey(Chem.MolFromSmiles(row["target"])).split("-")[0]
            )
    if a.native_test:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(a.native_test)

        def rows():
            names = pf.schema_arrow.names
            cols = [
                k
                for k in (
                    "ir",
                    "raman",
                    "kekule_smiles",
                    "smiles",
                    "formula",
                    "sample_id",
                )
                if k in names
            ]
            for batch in pf.iter_batches(columns=cols, batch_size=256):
                for r in batch.to_pylist():
                    if "kekule_smiles" not in r:
                        r["kekule_smiles"] = r["smiles"]
                    yield r

        selected = select(rows(), excluded, a.limit, excluded_keys)
    else:
        env = readonly_lmdb(assets.spectrum_lmdb)
        with env.begin() as tx:
            selected = select(
                (pickle.loads(b) for _, b in tx.cursor()),
                excluded,
                a.limit,
                excluded_keys,
            )
        env.close()
    report = dict(
        domain="VB-Mols native test"
        if a.native_test
        else "OpenMolSpec calculated spectra",
        dataset_sha256=sha256(a.native_test or assets.spectrum_lmdb),
        matching_identity="canonical nonisomeric SMILES",
        selection="First distinct structures by SHA256(vib-gen-check-v1 + nonisomeric SMILES), excluding legacy panel structures.",
        given_formula=bool(a.native),
        beam=10,
        records=[],
    )
    if a.exclude_panel:
        report["excluded_panel_sha256"] = sha256(a.exclude_panel)
    if a.native:
        from transformers import AutoTokenizer

        model, tok, path = native_model(a.native.resolve(), True, "cpu")
        ftok = AutoTokenizer.from_pretrained(
            a.native.resolve() / "models/FormulaTokenizer", local_files_only=True
        )
        report.update(
            checkpoint_sha256=sha256(path),
            temperature=3.5,
            input="IR + Raman + supplied reference molecular formula",
        )
    else:
        from openmolspec_ui.inference import OpenMolSpecService
        from openmolspec_ui.spectra import SpectralInput

        service = OpenMolSpecService(assets, device="cpu")
        report.update(
            checkpoint_sha256=sha256(assets.generation_checkpoint),
            input="IR + Raman" if a.spectra_only else "IR + Raman + H + C",
        )
        if a.adapter:
            from openmolspec_ui.vib_shift_adapter import estimate_shifts

            with np.load(a.adapter, allow_pickle=False) as saved:
                adapter = dict(saved)
            report.update(
                shift_adapter_sha256=sha256(a.adapter), used_measured_nmr=False
            )
    if a.decoder_head:
        net, _, _ = service._load_vib2mol(2)
        with np.load(a.decoder_head, allow_pickle=False) as head:
            if str(head["base_sha256"]) != report["checkpoint_sha256"]:
                raise ValueError("Decoder checkpoint mismatch")
            net.molecular_decoder.proj[-1].load_state_dict(
                {k: torch.tensor(head[k]) for k in ("weight", "bias")}, strict=True
            )
        report["decoder_head_sha256"] = sha256(a.decoder_head)
    if a.output.exists():
        previous = json.loads(a.output.read_text())
        if any(
            previous[k] != v
            for k, v in report.items()
            if k != "records" and k in previous
        ):
            raise ValueError("Existing report protocol differs")
        completed = [r["target"] for r in previous["records"]]
        if completed != [
            canonical(r["kekule_smiles"]) for r in selected[: len(completed)]
        ]:
            raise ValueError("Existing report cohort differs")
        report = {**report, **previous}
        if report.get("complete"):
            return
    for r in selected[len(report["records"]) :]:
        s = canonical(r["kekule_smiles"])
        if a.native:
            formula = r.get("formula") or rdMolDescriptors.CalcMolFormula(
                Chem.MolFromSmiles(r["kekule_smiles"])
            )
            data = {
                k: torch.as_tensor(
                    np.asarray(r[k]).copy(), dtype=torch.float32
                ).reshape(1, 1, 1024)
                for k in ("ir", "raman")
            }
            data["formula"] = ftok([formula], return_tensors="pt")
            with torch.inference_mode():
                ids = model.beam_infer_lm(
                    data, beam_size=10, max_len=150, temperature=3.5
                )["pred_ids"][0]
            raw = [
                tok.decode(x, skip_special_tokens=True).replace(" ", "") for x in ids
            ]
            beam = list(dict.fromkeys(v for v in map(canonical, raw) if v))
            # Known formula filters beams only; no reference SMILES is passed to generation.
            ranked = [
                v
                for v in beam
                if rdMolDescriptors.CalcMolFormula(Chem.MolFromSmiles(v)) == formula
            ]
            record = dict(
                target=s, formula=formula, beam=beam, formula_consistent=ranked
            )
        else:
            h, c = (
                (None, None)
                if a.spectra_only
                else (r["nmr_h_shifts_ppm"], r["nmr_c_shifts_ppm"])
            )
            if a.adapter:
                h, c = estimate_shifts(r["ir"], r["raman"], adapter)
            inputs = SpectralInput(ir=r["ir"], raman=r["raman"], nmr_h=h, nmr_c=c)
            result = service._generate_vib2mol(inputs, 10)
            ranked = result["candidates"]
            record = dict(
                target=s,
                unscored_by_itm=[
                    {"smiles": i["smiles"], "reason": i["itm_status"]}
                    for i in ranked
                    if i["itm_rank"] is None
                ],
                canonical_beam_order=[canonical(i["smiles"]) for i in ranked],
                itm=[
                    canonical(i["smiles"])
                    for i in sorted(
                        ranked,
                        key=lambda i: (
                            i["itm_rank"] is None,
                            i["itm_rank"] or i["beam_rank"],
                        ),
                    )
                ],
            )
        report["records"].append(record)
        fields = (
            ["beam", "formula_consistent"]
            if a.native
            else ["canonical_beam_order", "itm"]
        )
        report["counts"] = {
            k: {
                f"top{t}": sum(row["target"] in row[k][:t] for row in report["records"])
                for t in (1, 3, 5, 10)
            }
            for k in fields
        }
        report["complete"] = len(report["records"]) == len(selected)
        temp = a.output.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(a.output)
        print(len(report["records"]), len(selected), report["counts"], flush=True)


if __name__ == "__main__":
    main()

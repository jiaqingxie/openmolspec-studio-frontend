"""Pair silver HSQC annotations with frozen TransPeakNet outputs in verified atom order."""

import argparse
import csv
import gzip
import json
from collections import defaultdict, Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
import numpy as np
import pyarrow.parquet as pq
from rdkit import Chem
import torch
from torch_geometric.data import Batch
from openmolspec_bench.transpeaknet import (
    graph,
    load_model,
    predict_sites,
    SOLVENT_CLASS,
)
from openmolspec_bench.data import sha256


@torch.inference_mode()
def vectorized(model, batch):
    features = model.node_encoder(batch)
    atomic = batch.x[:, 0]
    sender, receiver = batch.edge_index
    mask = (atomic[sender] == 5) & (atomic[receiver] == 0)
    carbon, h = sender[mask], receiver[mask]
    sites, inverse, counts = torch.unique(
        carbon, sorted=True, return_inverse=True, return_counts=True
    )
    conditions = model.solvent_embedding(batch.solvent_class)[batch.batch[h]]
    vectors = torch.cat([conditions, features[h]], dim=1)
    hmean = (
        vectors.new_zeros((len(sites), vectors.shape[1])).index_add_(
            0, inverse, vectors
        )
        / counts[:, None]
    )
    values = (
        torch.cat(
            [model.lin_out(features[sites]) * 200, model.lin_out_h(hmean) * 10], dim=1
        )
        .cpu()
        .numpy()
    )
    return sites.cpu().numpy(), values


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "data", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--threads", type=int, default=2)
    a = p.parse_args()
    torch.set_num_threads(a.threads)
    base = a.source / "data_csv" / "2dnmr"
    metadata = defaultdict(set)
    with (base / "nmr_smile_solventclass_filtered4_3dgnn_trainval.csv").open() as f:
        for row in csv.DictReader(f):
            metadata[(row["File_name"].split(".")[0], int(row["solvent_class"]))].add(
                row["SMILES"]
            )
    with (base / "all_files_testdata_solvent_mw.csv").open() as f:
        gold = {
            Chem.MolToInchiKey(Chem.MolFromSmiles(r["SMILES"])).split("-")[0]
            for r in csv.DictReader(f)
        }
    solvents = {code: name for name, code in SOLVENT_CLASS.items()}
    model = load_model(a.source)
    counts = Counter()
    out = a.output.with_suffix(".partial")
    with gzip.open(out, "wt", compresslevel=2) as stream:
        for batch in pq.ParquetFile(a.data).iter_batches(batch_size=24):
            graphs, data = [], []
            for row in batch.to_pylist():
                counts["input"] += 1
                g = row["graph_data"]
                sol = g["solvent_class"]
                smiles = metadata[(row["filename"], sol)]
                if len(smiles) != 1:
                    counts["ambiguous_or_missing_smiles"] += 1
                    continue
                smi = next(iter(smiles))
                mol = Chem.MolFromSmiles(smi)
                key = Chem.MolToInchiKey(mol).split("-")[0]
                if key in gold:
                    counts["gold_connectivity_excluded"] += 1
                    continue
                mol = Chem.AddHs(mol)
                gr = graph(mol, solvents[sol])
                if not all(
                    np.array_equal(g[k], gr[k].numpy())
                    for k in ("x", "edge_index", "edge_attr")
                ):
                    counts["graph_order_mismatch"] += 1
                    continue
                targets = np.concatenate(
                    [np.array(row["c_peaks"]) * 200, np.array(row["h_peaks"]) * 10],
                    axis=1,
                )
                ids = [
                    a.GetIdx()
                    for a in mol.GetAtoms()
                    if a.GetAtomicNum() == 6
                    and any(n.GetAtomicNum() == 1 for n in a.GetNeighbors())
                ]
                if len(ids) != len(targets) or not np.isfinite(targets).all():
                    counts["invalid_target_cardinality"] += 1
                    continue
                graphs.append(gr.to_data_list()[0])
                data.append((key, smi, row["filename"], sol, ids, targets, mol))
            if not graphs:
                continue
            pack = Batch.from_data_list(graphs)
            sites, values = vectorized(model, pack)
            for i, (key, smi, file, sol, ids, truth, mol) in enumerate(data):
                lo, hi = int(pack.ptr[i]), int(pack.ptr[i + 1])
                mask = (sites >= lo) & (sites < hi)
                np.testing.assert_array_equal(sites[mask] - lo, ids)
                predicted = values[mask]
                if counts["written"] < 3:
                    idx, c, h = predict_sites(model, mol, solvents[sol])
                    np.testing.assert_array_equal(idx, ids)
                    np.testing.assert_allclose(
                        predicted, np.column_stack([c, h]), atol=0.002
                    )
                stream.write(
                    json.dumps(
                        [key, smi, file, sol, ids, predicted.tolist(), truth.tolist()],
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                counts["written"] += 1
            if counts["input"] % 2400 < 24:
                print(dict(counts), flush=True)
    out.replace(a.output)
    a.output.with_suffix(".manifest.json").write_text(
        json.dumps(
            dict(
                counts=counts,
                input_sha256=sha256(a.data),
                checkpoint_sha256=sha256(a.source / "ckpt/model_2dnmr.pt"),
                gold_identities=len(gold),
                output_sha256=sha256(a.output),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

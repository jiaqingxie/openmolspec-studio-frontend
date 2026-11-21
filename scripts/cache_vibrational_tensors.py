"""Evaluate one frozen tensor network at a time on the recorded QM9S geometries."""

import argparse
from pathlib import Path
import pickle
import sys
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from rdkit import Chem
from openmolspec_ui.chemistry import molecule_from_xyz
from openmolspec_ui.config import discover_assets
from openmolspec_ui.inference import OpenMolSpecService
from openmolspec_ui.theoretical import reconstruct_spectra
from openmolspec_bench.vibrational_profile import mode_spectra

TARGETS = ("Hi", "Hij", "dedipole", "depolar")


def graph(service, row):
    geom = row["geom"]
    xyz = [str(len(geom)), "QM9S optimized coordinates"]
    for z, x, y, w in geom:
        symbol = Chem.GetPeriodicTable().GetElementSymbol(int(z))
        xyz.append(f"{symbol} {x:.9f} {y:.9f} {w:.9f}")
    molecule = molecule_from_xyz("\n".join(xyz) + "\n")
    np.testing.assert_allclose(
        molecule.mol.GetConformer().GetPositions(),
        np.array(geom)[:, 1:],
        atol=1e-7,
        rtol=0,
    )
    return service._radius_graph(molecule)


def read_spectra(path):
    spectra = {}
    if path.exists():
        with path.open("rb") as stream:
            while stream.peek(1):
                key, pred = pickle.load(stream)
                spectra[key] = pred
    return spectra


def atomic_array(path, values):
    with NamedTemporaryFile(dir=path.parent, suffix=".partial", delete=False) as stream:
        tmp = Path(stream.name)
        try:
            np.save(stream, values, allow_pickle=False)
            stream.flush()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def evaluate(args, service, records, complete):
    import torch
    from torch_geometric.data import Batch

    model = service._load_tensor_model(args.target)
    directory = args.tensors / args.target
    directory.mkdir(parents=True, exist_ok=True)
    needed = [
        r
        for r in records
        if (r["key"] not in complete or r is records[0])
        and not (directory / (r["key"] + ".npy")).exists()
    ]
    if args.max_items:
        needed = needed[: args.max_items]
    for offset in range(0, len(needed), args.batch_size):
        rows = needed[offset : offset + args.batch_size]
        graphs = [graph(service, r) for r in rows]
        with torch.inference_mode():
            values = model(Batch.from_data_list(graphs))[args.target].cpu().numpy()
        counts = [
            g.edge_index.shape[1] if args.target == "Hij" else len(g.pos)
            for g in graphs
        ]
        if sum(counts) != len(values) or not np.isfinite(values).all():
            raise ValueError("Invalid batched tensor dimensions or values")
        chunks = np.split(values, np.cumsum(counts)[:-1])
        if offset == 0 and len(graphs) > 1:
            with torch.inference_mode():
                single = (
                    model(Batch.from_data_list(graphs[:1]))[args.target].cpu().numpy()
                )
            np.testing.assert_allclose(chunks[0], single, rtol=0.002, atol=0.001)
        for row, value in zip(rows, chunks):
            atomic_array(directory / (row["key"] + ".npy"), value)
        if offset % (25 * args.batch_size) == 0:
            print(args.target, offset + len(rows), "/", len(needed), flush=True)


def assemble_predictions(args, service, records, completed):
    service._add_project_paths()
    from benchmarks.engines.hessian_physics import assemble

    grid = np.linspace(500.0, 4000.0, 997)
    for row in records:
        key = row["key"]
        if key in completed and row is not records[0]:
            continue
        data = graph(service, row)
        tensors = {
            target: np.load(args.tensors / target / (key + ".npy"), allow_pickle=False)
            for target in TARGETS
        }
        hessian = assemble(tensors["Hi"], tensors["Hij"], data.edge_index.numpy())
        result = reconstruct_spectra(
            hessian,
            data.pos.numpy(),
            data.atomic_numbers.numpy(),
            tensors["dedipole"],
            tensors["depolar"],
            qm9s_modes=True,
        )
        channels = {
            c: np.interp(grid, result["wavenumber"], result[c]).astype("f")
            for c in ("ir", "raman")
        }
        channels.update(
            {"mode_" + c: v.astype("f") for c, v in mode_spectra(result, grid).items()}
        )
        if key in completed:
            for c in ("ir", "raman"):
                observed = channels[c]
                np.testing.assert_allclose(
                    observed, completed[key][c], atol=0.004, rtol=0.005
                )
            if all(field in completed[key] for field in channels):
                continue
        with args.cache.open("ab") as stream:
            pickle.dump((key, channels), stream)


def main():
    import torch

    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("input", "portable", "tensors", "cache"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--target", choices=(*TARGETS, "assemble"), required=True)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument(
        "--max-items", type=int, help="Maximum new molecules to cache in this process"
    )
    args = p.parse_args()
    if args.batch_size < 1:
        p.error("batch size must be positive")
    torch.set_num_threads(1)
    torch.manual_seed(2607)
    with args.input.open("rb") as stream:
        records = pickle.load(stream)
    complete = read_spectra(args.cache)
    service = OpenMolSpecService(discover_assets(args.portable.resolve()), device="cpu")
    if args.target == "assemble":
        assemble_predictions(args, service, records, complete)
    else:
        evaluate(args, service, records, complete)


if __name__ == "__main__":
    main()

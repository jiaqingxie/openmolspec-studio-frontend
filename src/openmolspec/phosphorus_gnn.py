"""Bond-conditioned message passing from a molecular graph to a phosphorus shift."""

from pathlib import Path
import gzip
import json

import numpy as np
import torch
from torch import nn

from .solution_shifts import analyte, solvent_id, site_features, root_estimate

DEPTH = 4
ATOM_DIMS = (119, 15, 13, 9, 8, 2, 2, 5, 4)
BOND_DIM = 64


class GraphIndex:
    """Share identical message-passing computations across atoms, without trainable ID tables."""

    def __init__(self):
        self.layers = [{} for _ in range(DEPTH + 1)]

    def add(self, mol, roots):
        atoms = list(mol.GetAtoms())
        table = self.layers[0]
        states = []
        for atom in atoms:
            feat = (
                atom.GetAtomicNum(),
                min(atom.GetDegree(), 14),
                max(0, min(atom.GetFormalCharge() + 6, 12)),
                min(atom.GetTotalNumHs(), 8),
                min(int(atom.GetHybridization()), 7),
                int(atom.GetIsAromatic()),
                int(atom.IsInRing()),
                min(atom.GetNumRadicalElectrons(), 4),
                {"R": 1, "S": 2}.get(atom.GetProp("_CIPCode"), 3)
                if atom.HasProp("_CIPCode")
                else 0,
            )
            states.append(table.setdefault(feat, len(table)))
        nbrs = [[] for _ in atoms]
        for bond in mol.GetBonds():
            i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
            kind = {1.0: 0, 2.0: 1, 3.0: 2, 1.5: 3}.get(bond.GetBondTypeAsDouble(), 4)
            bond_id = (
                kind
                + 5 * int(bond.GetIsConjugated())
                + 10 * int(bond.IsInRing())
                + 20
                * (
                    1
                    if str(bond.GetStereo()) in ("STEREOZ", "STEREOCIS")
                    else 2
                    if str(bond.GetStereo()) in ("STEREOE", "STEREOTRANS")
                    else 0
                )
            )
            nbrs[i].append((bond_id, j))
            nbrs[j].append((bond_id, i))
        for table in self.layers[1:]:
            states = [
                table.setdefault(
                    (center, tuple(sorted((b, states[j]) for b, j in neighbors))),
                    len(table),
                )
                for center, neighbors in zip(states, nbrs)
            ]
        size = max(len(atoms), 1)
        global_features = [
            np.log1p(size) / 4,
            mol.GetRingInfo().NumRings() / 5,
            sum(a.GetIsAromatic() for a in atoms) / size,
            sum(a.GetFormalCharge() for a in atoms) / 3,
            sum(a.GetAtomicNum() == 15 for a in atoms) / 3,
        ]
        return [states[i] for i in roots], global_features

    def arrays(self):
        arrays = [np.array(list(self.layers[0]), dtype=np.int32)]
        for table in self.layers[1:]:
            width = max((len(n) for _, n in table), default=0)
            neighbors = np.full((len(table), width), -1, dtype=np.int32)
            bond = np.zeros_like(neighbors)
            center = np.empty(len(table), dtype=np.int32)
            for (prev, group), i in table.items():
                center[i] = prev
                for k, (b, j) in enumerate(group):
                    neighbors[i, k] = j
                    bond[i, k] = b
            arrays.append((center, neighbors, bond))
        return arrays


def index_tensor(values):
    return torch.from_numpy(np.asarray(values, dtype=np.int64))


def graph_batch(arrays, roots):
    """Gather the exact dependency graph needed for these root embeddings."""
    steps = []
    selected, target = np.unique(roots, return_inverse=True)
    for centers, neighbors, bonds in reversed(arrays[1:]):
        adj = neighbors[selected]
        dst, slot = np.nonzero(adj >= 0)
        below, ids = np.unique(
            np.concatenate([centers[selected], adj[dst, slot]]), return_inverse=True
        )
        split = len(selected)
        steps.append(
            tuple(
                index_tensor(x)
                for x in (ids[:split], dst, ids[split:], bonds[selected][dst, slot])
            )
        )
        selected = below
    return (
        index_tensor(arrays[0][selected]),
        list(reversed(steps)),
        index_tensor(target),
    )


class PhosphorusGNN(nn.Module):
    def __init__(self, width=64):
        super().__init__()
        self.width = width
        self.atom = nn.Embedding(sum(ATOM_DIMS), width)
        self.register_buffer("offsets", torch.tensor(np.cumsum([0, *ATOM_DIMS[:-1]])))
        self.bond = nn.ModuleList(
            nn.Embedding(BOND_DIM, 2 * width) for _ in range(DEPTH)
        )
        self.update = nn.ModuleList(
            nn.Sequential(
                nn.Linear(2 * width, width),
                nn.SiLU(),
                nn.Linear(width, width),
                nn.LayerNorm(width),
            )
            for _ in range(DEPTH)
        )
        self.solvent = nn.Embedding(12, 8)
        self.head = nn.Sequential(
            nn.Linear(width + 13, width), nn.SiLU(), nn.Linear(width, 1)
        )

    def forward(self, graph, conditions, solvent):
        labels, steps, target = graph
        h = self.atom(labels + self.offsets).sum(dim=1) / 3
        for encoder, update, (center, dst, src, bond) in zip(
            self.bond, self.update, steps
        ):
            root = h[center]
            gate, bias = encoder(bond).chunk(2, dim=1)
            message = h[src] * torch.sigmoid(gate) + bias
            aggregate = torch.zeros_like(root).index_add_(0, dst, message)
            h = root + update(torch.cat([root, aggregate], dim=1))
        return self.head(
            torch.cat([h[target], conditions, self.solvent(solvent)], dim=1)
        ).flatten()


class PhosphorusGNNPredictor:
    def __init__(self, directory):
        from openmolspec_bench.data import sha256

        directory = Path(directory)
        cfg = json.loads((directory / "model.json").read_text())
        self.config = cfg
        for name, field in [
            ("gnn.pt", "gnn_sha256"),
            ("environments.json.gz", "environments_sha256"),
        ]:
            if sha256(directory / name) != cfg[field]:
                raise ValueError(f"Invalid 31P artifact digest for {name}")
        ckpt = torch.load(directory / "gnn.pt", map_location="cpu", weights_only=True)
        self.model = PhosphorusGNN(ckpt["width"])
        self.model.load_state_dict(ckpt["state"])
        self.model.eval()
        self.center, self.scale = ckpt["center"], ckpt["scale"]
        with gzip.open(directory / "environments.json.gz", "rt") as f:
            self.tables = json.load(f)
        self.nucleus = "31P"

    @torch.inference_mode()
    def predict(self, smiles, solvent=None):
        mol, original = analyte(smiles, "31P")
        sites = site_features(mol, "31P")
        graph = GraphIndex()
        roots, conditions = graph.add(mol, [s[0][0] for s in sites])
        batch = graph_batch(graph.arrays(), roots)
        pred = self.model(
            batch,
            torch.tensor([conditions] * len(roots), dtype=torch.float32),
            torch.full((len(roots),), solvent_id(solvent), dtype=torch.long),
        )
        values = pred.numpy() * self.scale + self.center
        envs = []
        for (members, codes, _), estimate in zip(sites, values):
            local = root_estimate(self.tables, codes)
            weight = self.config["environment_weight"] if local is not None else 0.0
            shift = (1 - weight) * float(estimate) + weight * (local or 0.0)
            envs.append(
                dict(
                    atom_indices=sorted(original[idx] for idx in members),
                    prediction_ppm=shift,
                )
            )
        rows = sorted((i, e["prediction_ppm"]) for e in envs for i in e["atom_indices"])
        return dict(
            smiles=smiles,
            nucleus="31P",
            solvent=solvent,
            unit="ppm",
            environments=envs,
            atom_indices=[i for i, _ in rows],
            prediction_ppm=[v for _, v in rows],
            atom_index_basis="zero-based RDKit input SMILES atom order",
        )

"""Graph batching and ordinary SDK behavior across molecule and atom order."""

import unittest

import numpy as np
from rdkit import Chem
import torch

from openmolspec.phosphorus_gnn import PhosphorusGNN, GraphIndex, graph_batch


class GraphPredictions(unittest.TestCase):
    def test_bond_messages_are_invariant_to_atom_and_batch_order(self):
        torch.set_num_threads(1)
        torch.manual_seed(11)
        model = PhosphorusGNN().eval()

        def predict(smiles):
            graph = GraphIndex()
            ids, desc = [], []
            for s in smiles:
                mol = Chem.MolFromSmiles(s)
                root = next(
                    a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 15
                )
                targets, g = graph.add(mol, [root])
                ids.extend(targets)
                desc.append(g)
            with torch.inference_mode():
                return model(
                    graph_batch(graph.arrays(), ids),
                    torch.tensor(desc, dtype=torch.float32),
                    torch.zeros(len(ids), dtype=torch.long),
                ).numpy()

        expected = predict(["OP(=O)(O)O"])
        observed = predict(["CP(C)C", "O=P(O)(O)O"])
        np.testing.assert_allclose(expected, observed[1:], atol=1e-5)
        self.assertGreater(abs(observed[0] - observed[1]), 1e-5)

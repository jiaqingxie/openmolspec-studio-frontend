"""Atom-centred chemical-shift prediction for experimental solution NMR."""

from functools import lru_cache
from pathlib import Path
import gzip
import json


NUCLEI = {"31P": 15, "19F": 9, "11B": 5, "29Si": 14}
BINS = 1536
SOLVENTS = (
    "unknown",
    "cdcl3",
    "dmso",
    "d2o",
    "methanol",
    "benzene",
    "acetone",
    "acetonitrile",
    "thf",
    "dichloromethane",
    "toluene",
    "other",
)


def solvent_id(value):
    """Encode common deuterated solvents. Mixtures and other recorded solvents share a category."""
    text = str(value or "").lower().replace(" ", "").replace("−", "-")
    aliases = {
        "cdcl3": "cdcl3",
        "chloroform-d": "cdcl3",
        "chloroform-d1": "cdcl3",
        "dmso-d6": "dmso",
        "(cd3)2so": "dmso",
        "d2o": "d2o",
        "cd3od": "methanol",
        "methanol-d4": "methanol",
        "c6d6": "benzene",
        "benzene-d6": "benzene",
        "acetone-d6": "acetone",
        "(cd3)2co": "acetone",
        "cd3cn": "acetonitrile",
        "acetonitrile-d3": "acetonitrile",
        "thf-d8": "thf",
        "cd2cl2": "dichloromethane",
        "dichloromethane-d2": "dichloromethane",
        "toluene-d8": "toluene",
    }
    if text in ("", "na", "nan", "none", "unknown", "notavailable"):
        return 0
    return SOLVENTS.index(aliases.get(text, "other"))


@lru_cache(maxsize=1)
def _generator():
    from rdkit.Chem import rdFingerprintGenerator

    return rdFingerprintGenerator.GetMorganGenerator(
        radius=5, includeChirality=True, includeRedundantEnvironments=True
    )


def analyte(smiles, nucleus):
    """Extract the target-bearing component when all other components are simple counterions."""
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None or any(a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
        raise ValueError("invalid_structure")
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    fragments = Chem.GetMolFrags(mol)
    target = [
        frag
        for frag in fragments
        if any(mol.GetAtomWithIdx(i).GetAtomicNum() == NUCLEI[nucleus] for i in frag)
    ]
    if not target:
        raise ValueError("missing_target")
    if len(target) != 1:
        raise ValueError("multiple_target_components")
    group = target[0]
    if len(fragments) == 1:
        return mol, group
    for frag in fragments:
        if frag == group:
            continue
        atom = mol.GetAtomWithIdx(frag[0])
        if (
            len(frag) != 1
            or not atom.GetFormalCharge()
            or atom.GetAtomicNum() not in (3, 9, 11, 12, 17, 19, 20, 35, 53)
        ):
            raise ValueError("unsupported_cofragment")
    mapping = []
    parts = Chem.GetMolFrags(mol, asMols=True, fragsMolAtomMapping=mapping)
    return parts[mapping.index(group)], group


def site_features(mol, nucleus, target_atoms=None):
    """Return symmetry classes, nested rooted environments and sparse shell descriptors."""
    from collections import Counter
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator

    atoms = list(mol.GetAtoms())
    targets = list(target_atoms) if target_atoms is not None else [a.GetIdx() for a in atoms if a.GetAtomicNum() == NUCLEI[nucleus]]
    if not targets:
        raise ValueError("The structure contains no atom of the requested nucleus")
    classes = {}
    if len(targets) == 1:
        classes[0] = targets
    else:
        ranks = Chem.CanonicalRankAtoms(mol, breakTies=False, includeChirality=True)
        for idx in targets:
            classes.setdefault(ranks[idx], []).append(idx)
    output = rdFingerprintGenerator.AdditionalOutput()
    output.AllocateBitInfoMap()
    _generator().GetSparseCountFingerprint(mol, additionalOutput=output)
    codes = [[0] * 6 for _ in atoms]
    for code, occurrences in output.GetBitInfoMap().items():
        for idx, radius in occurrences:
            codes[idx][radius] = code
    neighbors = [[a.GetIdx() for a in atom.GetNeighbors()] for atom in atoms]
    global_counts = [
        mol.GetNumHeavyAtoms(),
        mol.GetRingInfo().NumRings(),
        sum(a.GetIsAromatic() for a in atoms),
        Chem.GetFormalCharge(mol),
        len(targets),
        len(classes),
    ]
    result = []
    for group in classes.values():
        root = group[0]
        features = Counter({1 + i: v for i, v in enumerate(global_counts) if v})
        front, visited = {root}, {root}
        for distance in range(5):
            for idx in front:
                atom = atoms[idx]
                for radius in range(3):
                    code = codes[idx][radius]
                    token = (
                        (code ^ (distance * 2246822519) ^ (radius * 3266489917))
                        * 2654435761
                    ) & 0xFFFFFFFF
                    features[32 + token % BINS] += 1
                # Explicit element counts in each shell complement folded circular features.
                features[32 + BINS + 119 * distance + atom.GetAtomicNum()] += 1
            front = {j for idx in front for j in neighbors[idx]} - visited
            visited.update(front)
        result.append((group, codes[root], sorted(features.items())))
    return result


N_FEATURES = 32 + BINS + 5 * 119


def root_estimate(tables, codes):
    """Use the most specific local environment supported by at least two training observations."""
    for radius in (5, 4, 3):
        stat = tables[radius].get(str(codes[radius]))
        if stat and stat[1] >= 2:
            return stat[0]
    return None


def feature_matrix(rows):
    """Build a CSR matrix. Column zero is the optional solvent category."""
    from array import array
    import numpy as np
    from scipy.sparse import csr_matrix

    indptr = array("i", [0])
    indices = array("i")
    data = array("f")
    for features, solvent in rows:
        if solvent:
            indices.append(0)
            data.append(solvent)
        for idx, value in features:
            indices.append(idx)
            data.append(value)
        indptr.append(len(indices))
    return csr_matrix(
        (
            np.frombuffer(data, np.float32),
            np.frombuffer(indices, np.int32),
            np.frombuffer(indptr, np.int32),
        ),
        shape=(len(indptr) - 1, N_FEATURES),
    )


class SolutionShiftPredictor:
    """Load a fitted OpenMolSpec solution model and predict shifts in input SMILES atom order."""

    def __init__(self, model_dir):
        root = Path(model_dir)
        self.config = json.loads((root / "model.json").read_text())
        if self.config["feature_schema"] != 1:
            raise ValueError("Unsupported solution-shift feature schema")
        self._graph_model = None
        self.components = []
        if self.config.get("engine") == "solution_ensemble":
            from openmolspec_bench.data import sha256

            self.nucleus = self.config["nucleus"]
            names = set()
            for item in self.config["components"]:
                name = item["name"]
                if not name or name in (".", "..") or name != Path(name).name or name in names:
                    raise ValueError("Invalid solution ensemble component name")
                names.add(name)
                path = root / name
                if sha256(path / "model.json") != item["sha256"]:
                    raise ValueError("Solution ensemble component digest mismatch")
                model = SolutionShiftPredictor(path)
                if model.nucleus != self.nucleus or not 0 < item["weight"] <= 1:
                    raise ValueError("Invalid solution ensemble component")
                self.components.append((model, item["weight"]))
            if abs(sum(weight for _, weight in self.components) - 1) > 1e-9:
                raise ValueError("Solution ensemble weights must sum to one")
            return
        if self.config.get("engine") in ("phosphorus_gnn", "solution_gnn"):
            from .phosphorus_gnn import PhosphorusGNNPredictor
            self._graph_model = PhosphorusGNNPredictor(root)
            self.nucleus = self._graph_model.nucleus
            return
        import lightgbm as lgb
        from openmolspec_bench.data import sha256

        for file, field in [
            ("booster.txt", "booster_sha256"),
            ("environments.json.gz", "environments_sha256"),
        ]:
            if sha256(root / file) != self.config[field]:
                raise ValueError(f"Solution-shift artifact digest mismatch for {file}")
        self.nucleus = self.config["nucleus"]
        self.booster = lgb.Booster(model_file=str(root / "booster.txt"))
        with gzip.open(root / "environments.json.gz", "rt") as stream:
            self.tables = json.load(stream)

    def predict(self, smiles, solvent=None):
        """Predict ppm for every target atom of one connected molecule, optionally in a named solvent."""
        if getattr(self, "components", None):
            outputs = [(m.predict(smiles, solvent), w) for m, w in self.components]
            result = outputs[0][0]
            if any(len(p["environments"]) != len(result["environments"]) for p, _ in outputs):
                raise ValueError("Solution ensemble environment counts differ")
            for i, env in enumerate(result["environments"]):
                if any(p["environments"][i]["atom_indices"] != env["atom_indices"] for p, _ in outputs):
                    raise ValueError("Solution ensemble atom indices differ")
                env["prediction_ppm"] = sum(p["environments"][i]["prediction_ppm"] * w for p, w in outputs)
            by_atom = {i: env["prediction_ppm"] for env in result["environments"] for i in env["atom_indices"]}
            result["prediction_ppm"] = [by_atom[i] for i in result["atom_indices"]]
            return result
        if getattr(self, "_graph_model", None) is not None:
            return self._graph_model.predict(smiles, solvent)
        mol, original_indices = analyte(smiles, self.nucleus)
        sites = site_features(mol, self.nucleus)
        X = feature_matrix((features, solvent_id(solvent)) for _, _, features in sites)
        base = self.booster.predict(X, num_threads=1)
        rows = []
        environments = []
        alpha = self.config["environment_weight"]
        for (group, codes, _), estimate in zip(sites, base):
            local = root_estimate(self.tables, codes)
            shift = float(
                estimate if local is None else (1 - alpha) * estimate + alpha * local
            )
            indices = sorted(original_indices[idx] for idx in group)
            rows.extend((idx, shift) for idx in indices)
            environments.append({"atom_indices": indices, "prediction_ppm": shift})
        rows.sort()
        return {
            "smiles": smiles,
            "nucleus": self.nucleus,
            "solvent": solvent,
            "atom_indices": [idx for idx, _ in rows],
            "prediction_ppm": [v for _, v in rows],
            "environments": environments,
            "unit": "ppm",
            "atom_index_basis": "zero-based RDKit input SMILES atom order",
            "training_domain": "experimental chemical shifts; unambiguous single-environment supervision",
        }


def main(argv=None):
    """Predict experimental chemical shifts from a SMILES and an optional solvent."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        required=True,
        type=Path,
        help="Fitted solution-shift model directory",
    )
    parser.add_argument("--smiles", required=True)
    parser.add_argument(
        "--solvent", help="Recorded NMR solvent, for example CDCl3 or DMSO-d6"
    )
    args = parser.parse_args(argv)
    try:
        result = SolutionShiftPredictor(args.model_dir).predict(
            args.smiles, args.solvent
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

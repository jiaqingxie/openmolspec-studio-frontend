"""Extract measured atom-assigned H/C spectra, excluding program-generated spectra and external test structures."""

import argparse
import ast
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from rdkit import Chem, RDLogger
from openmolspec.solution_shifts import solvent_id
from openmolspec_bench.data import sha256

EXTERNAL = ("nmrspec_test", "patent_test_10k", "nmrexp_exp_10k", "nmrgym_test")


def metadata(value):
    return {
        int(i): v.strip()
        for i, v in re.findall(r"(?:^|\s)(\d+):(.+?)(?=\s+\d+:|$)", value)
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("sdf", "external", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    occupied = set()
    for dataset in EXTERNAL:
        with (a.external / dataset / "test.jsonl").open() as f:
            for line in f:
                smi = json.loads(line)["smiles"]
                m = Chem.MolFromSmiles(smi)
                if m is not None:
                    occupied.add(Chem.MolToInchiKey(m).split("-")[0])
    counts = Counter()
    temp = a.output.with_suffix(".partial")
    with gzip.open(temp, "wt", compresslevel=2) as out:
        for mol in Chem.ForwardSDMolSupplier(
            str(a.sdf), removeHs=False, strictParsing=False
        ):
            counts["input"] += 1
            if mol is None or len(Chem.GetMolFrags(mol)) != 1:
                counts["invalid_or_multicomponent"] += 1
                continue
            key = Chem.MolToInchiKey(mol).split("-")[0]
            if not key or key in occupied:
                counts["external_or_missing_connectivity"] += 1
                continue
            for atom in mol.GetAtoms():
                atom.SetIntProp("_source_atom", atom.GetIdx())
            heavy = Chem.RemoveHs(mol)
            smiles = Chem.MolToSmiles(heavy, canonical=True)
            order = ast.literal_eval(heavy.GetProp("_smilesAtomOutputOrder"))
            index = {
                heavy.GetAtomWithIdx(old).GetIntProp("_source_atom"): new
                for new, old in enumerate(order)
            }
            seeds = hashlib.sha256(("assigned-hc-v1:" + key).encode()).digest()
            bucket = int.from_bytes(seeds[:4], "big") % 100
            role = "train" if bucket < 80 else "val" if bucket < 90 else "test"
            program = metadata(mol.GetProp("Program")) if mol.HasProp("Program") else {}
            solvents = (
                metadata(mol.GetProp("Solvent")) if mol.HasProp("Solvent") else {}
            )
            for field in mol.GetPropNames():
                match = re.fullmatch(r"Spectrum (13C|1H) (\d+)", field)
                if not match:
                    continue
                nucleus = match[1]
                spec = int(match[2])
                if spec in program:
                    counts["program_generated_" + nucleus] += 1
                    continue
                sites = defaultdict(set)
                for peak in mol.GetProp(field).split("|"):
                    try:
                        value, _, idx = peak.split(";")
                        value = float(value)
                        ix = int(idx)
                        if not 0 <= ix < mol.GetNumAtoms() or not abs(value) < 1e4:
                            continue
                        atom = mol.GetAtomWithIdx(ix)
                        if nucleus == "13C" and atom.GetAtomicNum() != 6:
                            continue
                        if nucleus == "1H" and atom.GetAtomicNum() == 1:
                            if atom.GetDegree() != 1:
                                continue
                            ix = atom.GetNeighbors()[0].GetIdx()
                        elif (
                            nucleus == "1H"
                            and atom.GetTotalNumHs(includeNeighbors=True) == 0
                        ):
                            continue
                        sites[index[ix]].add(value)
                    except (ValueError, KeyError):
                        continue
                if not sites:
                    continue
                solvent = solvents.get(spec, "")
                for name in [
                    "CDCl3",
                    "DMSO-d6",
                    "C6D6",
                    "D2O",
                    "CD3OD",
                    "CD2Cl2",
                    "THF-d8",
                    "CD3CN",
                    "acetone-d6",
                    "toluene-d8",
                ]:
                    if name.lower() in solvent.lower():
                        solvent = name
                        break
                row = [
                    key,
                    role,
                    smiles,
                    nucleus,
                    solvent_id(solvent),
                    [[i, sorted(v)] for i, v in sites.items()],
                ]
                out.write(json.dumps(row, separators=(",", ":")) + "\n")
                counts[role + "/" + nucleus + "/spectra"] += 1
                counts[role + "/" + nucleus + "/sites"] += len(sites)
            if counts["input"] % 5000 == 0:
                print(dict(counts), flush=True)
    temp.replace(a.output)
    a.output.with_suffix(".manifest.json").write_text(
        json.dumps(
            dict(
                counts=counts,
                sdf_sha256=sha256(a.sdf),
                external_unique=len(occupied),
                output_sha256=sha256(a.output),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

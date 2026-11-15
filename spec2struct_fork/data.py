"""Stream WanJuan JSONL into scaffold-separated spectrum/SMILES examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path


_H1 = re.compile(r"(?:^|[^A-Z0-9])(?:1\s*H|H\s*1|PROTON)[\s-]*(?:NMR|RMN)\b")
_C13 = re.compile(r"(?:^|[^A-Z0-9])(?:13\s*C|C\s*13|CARBON(?:-13)?)[\s-]*(?:NMR|RMN|DEPT)\b")
SMILES_BYTES = frozenset(b"#%()*+-./0123456789:=@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]abcdefghijklmnopqrstuvwxyz")


def spectrum_family(raw_type: str) -> str | None:
    """Recognize proton and carbon NMR, including common carbon DEPT labels."""
    value = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(raw_type)).upper().strip())
    h_match = _H1.search(value) or value == "H NMR"
    c_match = _C13.search(value) or value == "C NMR" or value.startswith("DEPT")
    if h_match and c_match:
        return None
    if h_match:
        return "h1"
    if c_match:
        return "c13"
    return None


def clean_text(value: object) -> str:
    return " ".join(str("" if value is None else value).split())


def extract_features(compound: dict) -> dict | None:
    """Keep every nonempty H/C NMR record; either modality can be absent."""
    nmr: dict[str, list[dict[str, str]]] = {"h1": [], "c13": []}
    for spectrum in compound.get("spectra") or []:
        if not isinstance(spectrum, dict):
            continue
        family = spectrum_family(spectrum.get("spectrum_type", ""))
        if family in nmr:
            shift = clean_text(spectrum.get("chemical_shift"))
            if shift:
                record = {"type": clean_text(spectrum.get("spectrum_type")),
                          "chemical_shift": shift}
                for field in ("frequency", "solvent", "source_line"):
                    if spectrum.get(field) is not None:
                        record[field] = spectrum[field]
                nmr[family].append(record)
    if not nmr["h1"] and not nmr["c13"]:
        return None
    return nmr


def modality_mask(features: dict) -> list[int]:
    """Return H/C availability in a stable order used by training and inference."""
    return [int(bool(features["h1"])), int(bool(features["c13"]))]


def assigned_split(group: str, seed: int) -> str:
    """Assign the same scaffold to the same split on every run."""
    digest = hashlib.sha256(f"{seed}:{group}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % 10000
    return "train" if bucket < 8000 else "val" if bucket < 9000 else "test"


def canonical_structure(raw_smiles: str, chem, murcko, descriptors) -> tuple[str, str, str] | None:
    """Return canonical SMILES, scaffold grouping key, and molecular formula."""
    mol = chem.MolFromSmiles(raw_smiles)
    if mol is None:
        return None
    smiles = chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    scaffold = murcko.MurckoScaffoldSmiles(mol=mol, includeChirality=False)
    formula = descriptors.CalcMolFormula(mol)
    return smiles, scaffold or f"acyclic:{smiles}", formula


def prepare(source: Path, output: Path, seed: int, max_patents: int | None,
            max_examples: int | None) -> dict:
    """Write train/val/test JSONL without loading the source dataset into RAM."""
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem.Scaffolds import MurckoScaffold
        from rdkit.Chem import rdMolDescriptors
    except ImportError as exc:
        raise SystemExit("Install rdkit before preparing examples: pip install rdkit") from exc
    RDLogger.DisableLog("rdApp.error")
    if not source.is_file():
        raise FileNotFoundError(source)
    output.mkdir(parents=True, exist_ok=True)
    final = {name: output / f"{name}.jsonl" for name in ("train", "val", "test")}
    if any(path.exists() for path in (*final.values(), output / "summary.json")):
        raise FileExistsError(f"Output files already exist in {output}; choose a new directory")
    partial = {name: output / f"{name}.jsonl.partial" for name in final}
    if any(path.exists() for path in partial.values()):
        raise FileExistsError(f"Incomplete output files exist in {output}")
    counts = Counter()
    started = time.monotonic()
    handles = {name: path.open("x", encoding="utf-8") for name, path in partial.items()}
    try:
        with source.open("r", encoding="utf-8") as stream:
            for patent_index, line in enumerate(stream):
                if max_patents is not None and patent_index >= max_patents:
                    break
                if not line.strip():
                    continue
                patent = json.loads(line)
                counts["patents"] += 1
                meta = patent.get("meta_info") or {}
                patent_id = meta.get("upstream_path") or meta.get("folder_id") or str(patent_index)
                for compound in patent.get("compounds") or []:
                    counts["compounds"] += 1
                    raw_smiles = clean_text(compound.get("smiles"))
                    if not raw_smiles:
                        counts["missing_smiles"] += 1
                        continue
                    features = extract_features(compound)
                    if features is None:
                        counts["missing_nmr"] += 1
                        continue
                    structure = canonical_structure(raw_smiles, Chem, MurckoScaffold,
                                                    rdMolDescriptors)
                    if structure is None:
                        counts["invalid_smiles"] += 1
                        continue
                    smiles, scaffold, formula = structure
                    if len(smiles.encode("utf-8")) > 160:
                        counts["long_smiles"] += 1
                        continue
                    if not set(smiles.encode("utf-8")) <= SMILES_BYTES:
                        counts["unsupported_smiles_char"] += 1
                        continue
                    split = assigned_split(scaffold, seed)
                    mask = modality_mask(features)
                    example = {
                        "smiles": smiles, "formula": formula,
                        "h_nmr": features["h1"], "c_nmr": features["c13"],
                        "modality_mask": mask, "scaffold": scaffold, "patent_id": patent_id,
                        "year": meta.get("year"), "source": meta.get("source"),
                    }
                    handles[split].write(json.dumps(example, ensure_ascii=False) + "\n")
                    counts[split] += 1
                    counts["examples"] += 1
                    category = "h_and_c" if mask == [1, 1] else "h_only" if mask[0] else "c_only"
                    counts[category] += 1
                    counts["h_records"] += len(features["h1"])
                    counts["c_records"] += len(features["c13"])
                    if max_examples is not None and counts["examples"] >= max_examples:
                        break
                if counts["patents"] % 10000 == 0:
                    print(json.dumps({"patents": counts["patents"],
                                      "examples": counts["examples"],
                                      "h_only": counts["h_only"],
                                      "c_only": counts["c_only"],
                                      "h_and_c": counts["h_and_c"],
                                      "elapsed_s": round(time.monotonic() - started)}),
                          flush=True)
                if max_examples is not None and counts["examples"] >= max_examples:
                    break
    except BaseException:
        for handle in handles.values():
            handle.close()
        raise
    for handle in handles.values():
        handle.close()
    summary = {
        "format_version": 2, "source": str(source.resolve()), "seed": seed,
        "split_method": "SHA256(seed:Murcko_scaffold), 80/10/10; acyclic by canonical SMILES",
        "counts": dict(counts),
    }
    for name in final:
        os.replace(partial[name], final[name])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/raw/WanJuan_MolSpectra_v1_0_3.jsonl"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--max-patents", type=int)
    parser.add_argument("--max-examples", type=int)
    args = parser.parse_args()
    if args.max_patents is not None and args.max_patents < 1:
        parser.error("--max-patents must be positive")
    if args.max_examples is not None and args.max_examples < 1:
        parser.error("--max-examples must be positive")
    print(json.dumps(prepare(args.input, args.output_dir, args.seed,
                             args.max_patents, args.max_examples), indent=2))


if __name__ == "__main__":
    main()

"""Prepare measured solution spectra, molecule identities and atom-centred features for F/P."""

import argparse
import ast
from collections import Counter, defaultdict
import csv
import gzip
import json
import math
import os
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from openmolspec.solution_shifts import NUCLEI, analyte, site_features, solvent_id
from openmolspec_bench.data import readonly_lmdb, sha256


def measurements(args):
    import pyarrow.parquet as pq

    nuc = args.nucleus
    symbol = nuc[-1]
    pool = args.pool_root / ("pool_" + symbol) / "valid.lmdb"
    env = readonly_lmdb(pool)
    with env.begin() as txn:
        for i, (_, value) in enumerate(txn.cursor()):
            row = pickle.loads(value)
            target = [
                float(v)
                for v, m in zip(row["atoms_target"], row["atoms_target_mask"])
                if m
            ]
            if len(target) != 1:
                raise ValueError(
                    "Historical evaluation pool needs a single labelled site"
                )
            yield row["smiles"], "legacy", "pool", "", target, i
    env.close()
    for role in ("test", "val", "train"):
        with (args.wanjuan / f"{nuc}-{role}.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                yield (
                    row["smiles"],
                    "WanJuan",
                    role,
                    row.get("solvent"),
                    row["peaks_ppm"],
                    None,
                )
    source = pq.ParquetFile(args.nmrexp / f"nmrexp_{nuc}_usable.parquet")
    for batch in source.iter_batches(
        columns=["SMILES", "NMR_solvent", "NMR_processed"], batch_size=4096
    ):
        for row in batch.to_pylist():
            try:
                raw = ast.literal_eval(row["NMR_processed"])
                values = []
                for peak in raw:
                    position = peak[0]
                    if isinstance(position, (list, tuple)):
                        if len(position) != 2:
                            raise ValueError("Invalid peak range")
                        position = (float(position[0]) + float(position[1])) / 2
                    values.append(float(position))
            except (ValueError, TypeError, IndexError, SyntaxError):
                values = []
            yield row["SMILES"], "NMRexp", "", row["NMR_solvent"], values, None
    if nuc == "31P":
        with args.ilm.open() as stream:
            names = next(
                csv.reader([next(stream)], delimiter=" ", skipinitialspace=True)
            )
            columns = names[: names.index("cansmi") + 1]
            for number, line in enumerate(stream, 1):
                # An unescaped quotation mark occurs in one trailing citation. All
                # structural and experimental fields we use precede that citation.
                fields = next(csv.reader([line], delimiter=" ", skipinitialspace=True))
                if fields[0] != str(number) or len(fields) < len(columns) + 1:
                    raise ValueError("Unexpected Ilm R table prefix")
                row = dict(zip(columns, fields[1:]))
                try:
                    values = [float(row["shift"])]
                except ValueError:
                    values = []
                yield row["cansmi"], "Ilm", "", row["LM"], values, None


def main():
    from rdkit import Chem, RDLogger
    from rdkit.Chem.Scaffolds import MurckoScaffold

    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("wanjuan", "nmrexp", "pool-root", "output"):
        cli.add_argument("--" + name, type=Path, required=True)
    cli.add_argument("--ilm", type=Path, help="Measured Ilm CSV, required for 31P")
    cli.add_argument("--nucleus", choices=NUCLEI, required=True)
    args = cli.parse_args()
    if args.nucleus == "31P" and not args.ilm:
        cli.error("--ilm is required for 31P")
    RDLogger.DisableLog("rdApp.*")
    groups = defaultdict(list)
    counts = Counter()
    for smi, source, role, solvent, values, index in measurements(args):
        counts["raw_" + source] += 1
        if (
            not isinstance(smi, str)
            or not values
            or not all(math.isfinite(x) for x in values)
        ):
            counts["unparsed_or_missing_" + source] += 1
            continue
        groups[smi].append([source, role, solvent_id(solvent), values, index])
    print(args.nucleus, "input SMILES", len(groups), dict(counts), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix(".partial")
    with gzip.open(tmp, "wt", compresslevel=2) as stream:
        for n, (smiles, obs) in enumerate(groups.items()):
            try:
                mol, indices = analyte(smiles, args.nucleus)
            except ValueError as error:
                counts[str(error) + "_records"] += len(obs)
                continue
            key = Chem.MolToInchiKey(mol).split("-")[0]
            if len(key) != 14:
                counts["missing_connectivity_key_records"] += len(obs)
                continue
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
            sites = site_features(mol, args.nucleus)
            row = [key, smiles, scaffold, sites, obs]
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
            counts["written_structures"] += 1
            if n and n % 25000 == 0:
                print(args.nucleus, n, "/", len(groups), flush=True)
    os.replace(tmp, args.output)
    paths = [
        args.wanjuan / f"{args.nucleus}-{r}.jsonl" for r in ("test", "val", "train")
    ]
    paths.extend(
        [
            args.nmrexp / f"nmrexp_{args.nucleus}_usable.parquet",
            args.pool_root / ("pool_" + args.nucleus[-1]) / "valid.lmdb",
        ]
    )
    if args.nucleus == "31P":
        paths.append(args.ilm)
    args.output.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "counts": counts,
                "sources": {str(p): sha256(p) for p in paths},
                "output_sha256": sha256(args.output),
            },
            indent=2,
        )
    )
    print(args.nucleus, "finished", counts, flush=True)


if __name__ == "__main__":
    main()

"""Prepare exact, bounded F/P inference inputs and immutable artifact manifests."""

import argparse
import json
from pathlib import Path
import pickle
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openmolspec_bench.data import readonly_lmdb, sha256


def main():
    import lmdb

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=32)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for symbol in ("F", "P"):
        source = args.models_root / "nmrnetpp" / f"pool_{symbol}" / "valid.lmdb"
        directory = args.output / symbol
        directory.mkdir()
        rows = []
        environment = readonly_lmdb(source)
        with environment.begin() as transaction:
            for key, value in transaction.cursor():
                row = pickle.loads(value)
                rows.append((key, value, row["smiles"]))
                if len(rows) >= args.limit:
                    break
        environment.close()
        local = args.output / f"{symbol}.lmdb"
        # LMDB writers need a local filesystem; copy the completed file afterwards.
        import tempfile, shutil
        with tempfile.TemporaryDirectory(prefix="openmolspec-fp-") as temporary:
            output = Path(temporary) / "valid.lmdb"
            destination = lmdb.open(str(output), subdir=False, map_size=128 * 1024 * 1024)
            with destination.begin(write=True) as transaction:
                for index, (_, value, _) in enumerate(rows):
                    transaction.put(str(index).zfill(6).encode(), value)
            destination.close()
            shutil.copyfile(output, local)
        manifest = {"symbol": symbol, "training_performed": False, "examples": len(rows),
                    "source": {"path": str(source), "sha256": sha256(source)},
                    "input": {"path": str(local), "sha256": sha256(local)},
                    "records": [{"inference_index": index, "source_key": key.decode(), "smiles": smiles}
                                for index, (key, _, smiles) in enumerate(rows)]}
        (directory / "input_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()

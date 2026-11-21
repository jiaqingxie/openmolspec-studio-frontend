"""Package a verified solution-shift ensemble and its SDK for offline inference."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from solution_ensemble_card import model_card

ROOT = Path(__file__).resolve().parents[1]


def digest(content):
    return hashlib.sha256(content).hexdigest()


def package(nucleus, registry, wheel, output):
    model = registry / nucleus
    report = ROOT / "results" / f"forward_selection_{nucleus}.json"
    comparison = json.loads(report.read_text())
    config = json.loads((model / "model.json").read_text())
    payload = {"model/model.json": (model / "model.json").read_bytes()}
    if not comparison.get("test_predictions_verified_with_sdk") or digest(payload["model/model.json"]) != comparison["model_config_sha256"]:
        raise ValueError("Model does not match the held-out comparison")
    for item in config["components"]:
        name = item["name"]
        if Path(name).name != name:
            raise ValueError("Invalid component directory")
        path = model / name
        record = (path / "model.json").read_bytes()
        if digest(record) != item["sha256"]:
            raise ValueError("Component does not match ensemble")
        payload[f"model/{name}/model.json"] = record
        component = json.loads(record)
        weights = ("gnn.pt", "gnn_sha256") if "gnn_sha256" in component else ("booster.txt", "booster_sha256")
        for filename, field in (weights, ("environments.json.gz", "environments_sha256")):
            data = (path / filename).read_bytes()
            if digest(data) != component[field]:
                raise ValueError(f"Checksum differs for {filename}")
            payload[f"model/{name}/{filename}"] = data
    payload[wheel.name] = wheel.read_bytes()
    payload["comparison.json"] = report.read_bytes()
    payload["README.md"] = model_card(nucleus, True).encode()
    payload["README.zh.md"] = model_card(nucleus, False).encode()
    payload["SHA256SUMS"] = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(payload.items())).encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"openmolspec-{nucleus}.zip"
    temporary = archive.with_suffix(".partial")
    with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=7) as stream:
        for name, data in sorted(payload.items()):
            stream.writestr(name, data)
    with ZipFile(temporary) as stream:
        if stream.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
    temporary.replace(archive)
    print(archive.name, digest(archive.read_bytes()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nuclei", nargs="+", choices=("11B", "29Si", "19F"), required=True)
    for arg in ("registry", "wheel", "output"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    for nucleus in args.nuclei:
        package(nucleus, args.registry, args.wheel, args.output)

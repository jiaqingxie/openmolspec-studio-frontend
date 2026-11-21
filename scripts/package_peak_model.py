"""Package the selected H/C spectrum predictor without its training spectra."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from peak_model_card import model_card, ROOT


def digest(b):
    return hashlib.sha256(b).hexdigest()


def build(registry, nucleus, wheel, output):
    report = ROOT / "results" / f"forward_peak_model_{nucleus}.json"
    comparison = json.loads(report.read_text())
    root = registry / nucleus
    if (
        comparison["deployed_model"] != "peak_spectrum"
        or digest((root / "model.json").read_bytes())
        != comparison["selected_config_sha256"]
    ):
        raise ValueError("Configured model differs from the independent comparison")
    names = ["model.json"]
    settings = comparison["model"]
    if settings["peak_learning_weight"] < 1:
        names.extend(
            "assigned/" + f for f in ("model.json", "booster.txt", "lookup.json.gz")
        )
    if settings["peak_learning_weight"] > 0:
        names.append("peak-learning/environments.json.gz")
    payload = {"model/" + n: (root / n).read_bytes() for n in names}
    payload.update(
        {
            wheel.name: wheel.read_bytes(),
            "comparison.json": report.read_bytes(),
            "README.md": model_card(nucleus, True).encode(),
            "README.zh.md": model_card(nucleus, False).encode(),
        }
    )
    payload["SHA256SUMS"] = "".join(
        f"{digest(b)}  {n}\n" for n, b in sorted(payload.items())
    ).encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"openmolspec-{nucleus}.zip"
    temp = archive.with_suffix(".partial")
    with ZipFile(temp, "w", ZIP_DEFLATED, compresslevel=6) as z:
        for n, b in sorted(payload.items()):
            z.writestr(n, b)
    with ZipFile(temp) as z:
        if z.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
    temp.replace(archive)
    print(archive.name, digest(archive.read_bytes()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nucleus", choices=["1H", "13C"], required=True)
    for name in ("registry", "wheel", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args()
    build(a.registry, a.nucleus, a.wheel, a.output)

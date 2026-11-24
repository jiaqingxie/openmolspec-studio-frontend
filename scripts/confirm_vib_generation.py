"""Select on the first panel, then compare the frozen and chosen models on a disjoint panel."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "portable",
        "native",
        "adapter",
        "decoder-head",
        "cache",
        "results",
        "legacy",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    from filelock import FileLock

    with FileLock(str(a.results / ".vib_dual_model_selection.lock")):
        confirm(a)


def confirm(a):
    paired = "openmolspec_bench.vib_generation_check"
    native = "openmolspec_bench.vib_native_beams"
    models = [
        ("frozen", "vib_generation_dual_unadapted24", paired, []),
        (
            "predicted_shifts",
            "vib_generation_dual_adapted24",
            paired,
            ["--adapter", str(a.adapter)],
        ),
        (
            "tuned_decoder",
            "vib_generation_dual_tuned_decoder24",
            paired,
            ["--decoder-head", str(a.decoder_head)],
        ),
        (
            "native_channels",
            "vib_generation_dual_native_noformula",
            native,
            ["--native", str(a.native), "--cache", str(a.cache)],
        ),
    ]
    scores = {}
    development_hashes = {}
    cohort = None
    for name, stem, module, _ in models:
        content = (a.results / (stem + ".json")).read_bytes()
        development_hashes[name] = hashlib.sha256(content).hexdigest()
        report = json.loads(content)
        targets = [r["target"] for r in report["records"]]
        if (
            not report["complete"]
            or len(targets) != 24
            or (cohort is not None and cohort != targets)
        ):
            raise ValueError(f"Incomplete or mismatched development panel for {name}")
        cohort = targets
        scores[name] = (
            report["counts"]
            if module == native
            else report["counts"]["canonical_beam_order"]
        )
    selected = max(models, key=lambda m: (scores[m[0]]["top1"], scores[m[0]]["top5"]))
    decision = dict(
        selection="Exact top-1, then top-5 counts on 24 development structures. Ties favor the earlier entry, starting with the frozen decoder.",
        confirmation_rule="Adopt a development winner only if its pair of (top-1, top-5) counts also strictly improves lexicographically on the separate confirmation panel.",
        development=scores,
        development_sha256=development_hashes,
        selected=selected[0],
    )
    path = a.results / "vib_dual_model_selection.json"
    if path.exists():
        prior = json.loads(path.read_text())
        if (
            prior.get("complete")
            and prior.get("development_sha256") == development_hashes
        ):
            confirmations = prior.get("confirmation_sha256", {})
            if all(
                (a.results / file).is_file()
                and hashlib.sha256((a.results / file).read_bytes()).hexdigest()
                == digest
                for file, digest in confirmations.items()
            ):
                return

    def save():
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(decision, indent=2) + "\n")
        temporary.replace(path)

    if selected[0] == "frozen":
        decision.update(recommended_model="frozen", complete=True)
        save()
        return
    decision["complete"] = False
    save()
    confirmation_targets = None
    for name, _, module, flags in (models[0], selected):
        out = a.results / f"vib_dual_confirm_{name}.json"
        args = [
            sys.executable,
            "-m",
            module,
            "--portable",
            str(a.portable),
            "--legacy",
            str(a.legacy),
            "--exclude-panel",
            str(a.results / (models[0][1] + ".json")),
            "--limit",
            "24",
            "--output",
            str(out),
            *flags,
        ]
        if module == paired:
            args.append("--spectra-only")
        subprocess.run(args, check=True)
        report = json.loads(out.read_text())
        decision.setdefault("confirmation_sha256", {})[out.name] = hashlib.sha256(
            out.read_bytes()
        ).hexdigest()
        targets = [row["target"] for row in report["records"]]
        if not report["complete"] or len(targets) != 24 or set(targets) & set(cohort):
            raise ValueError(f"Incomplete confirmation for {name}")
        if confirmation_targets is not None and confirmation_targets != targets:
            raise ValueError("Confirmation models received different queries")
        confirmation_targets = targets
        decision.setdefault("confirmation", {})[name] = (
            report["counts"]
            if module == native
            else report["counts"]["canonical_beam_order"]
        )
    counts = decision["confirmation"]
    ranks = {k: (v["top1"], v["top5"]) for k, v in counts.items()}
    decision["recommended_model"] = (
        selected[0] if ranks[selected[0]] > ranks["frozen"] else "frozen"
    )
    decision["complete"] = True
    save()


if __name__ == "__main__":
    main()

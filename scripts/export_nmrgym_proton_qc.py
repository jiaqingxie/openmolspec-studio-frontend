"""Write portable, auditable NMRGym proton training views without modifying the official files."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import pickle
import tempfile
import zipfile

from rdkit import RDLogger

from clean_nmrgym_proton import POLICY, reasons
from openmolspec_bench.data import sha256


def export_archive(official, cache, clean, archive):
    qc = json.loads((clean / "cleaning.json").read_text())
    expected = {}
    with (cache / "train.jsonl").open() as f:
        for line in f:
            key, smi, h = json.loads(line)
            expected[smi] = (key, h)
    # The specialist only uses records for which the original feature preparation succeeded.
    import numpy as np

    keys = set(np.load(cache / "train-keys.npy").astype(str))
    quarantine = {
        r["connectivity"]
        for r in map(json.loads, (clean / "audit.jsonl").read_text().splitlines())
        if r["action"] == "quarantine"
    }
    matched = set()
    source_matches = range_mismatches = 0
    output_counts = Counter()
    rule_counts = Counter()
    with official.open("rb") as f:
        records = pickle.load(f)
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4
    ) as z:
        with tempfile.TemporaryDirectory(dir=archive.parent) as tmp:
            kept = Path(tmp) / "retained.jsonl"
            log = Path(tmp) / "audit.jsonl"
            with kept.open("w") as good, log.open("w") as audit:
                for idx, row in enumerate(records):
                    smi = row["smiles"]
                    h = [float(v) for v in row["h_shift"]]
                    c = [float(v) for v in row["c_shift"]]
                    finite = bool(h) and all(map(math.isfinite, h))
                    flags = (
                        reasons(smi, h, c) if finite else ["empty_or_nonfinite_protons"]
                    )
                    rec = dict(official_row=idx, smiles=smi, h_shift=h, c_shift=c)
                    if not flags:
                        good.write(
                            json.dumps(rec, separators=(",", ":"), allow_nan=False)
                            + "\n"
                        )
                    output_counts["quarantined" if flags else "retained"] += 1
                    rule_counts.update(flags)
                    if flags or max(map(abs, h), default=0) > 25:
                        audit.write(
                            json.dumps(
                                dict(
                                    **rec,
                                    action="quarantine"
                                    if flags
                                    else "retain_for_review",
                                    reasons=flags,
                                ),
                                separators=(",", ":"),
                            )
                            + "\n"
                        )
                    if smi in expected:
                        key, benchmark_h = expected[smi]
                        if key in keys and [float(f"{v:g}") for v in h] == benchmark_h:
                            source_matches += 1
                            matched.add(key)
                            range_mismatches += bool(flags) != (key in quarantine)
            z.write(kept, "official/retained.jsonl")
            z.write(log, "official/audit.jsonl")
            if matched != keys or range_mismatches:
                raise ValueError(
                    f"Official/specialist reconciliation: {len(matched)} of {len(keys)} keys, {range_mismatches} policy differences"
                )
            manifest = dict(
                policy=POLICY,
                official_train=dict(
                    source_name=official.name,
                    sha256=sha256(official),
                    original_records=len(records),
                    **output_counts,
                    rule_counts=dict(rule_counts),
                    retained_sha256=sha256(kept),
                    audit_sha256=sha256(log),
                ),
                specialist_training=qc,
                verified_official_to_specialist_connectivities=len(matched),
                source_rows_matching_specialist=source_matches,
                official_and_specialist_quarantine_disagreements=range_mismatches,
                schema=dict(
                    official="official_row (zero-based index in original PKL), smiles, h_shift, c_shift, in original order and precision",
                    specialist="JSON array [connectivity, smiles, proton shift list] consumed by the model",
                    audit="Original peak lists, reason codes and retain_for_review/quarantine decisions",
                ),
            )
            z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        z.write(clean / "train.jsonl", "specialist/train.jsonl")
        z.write(clean / "audit.jsonl", "specialist/audit.jsonl")
        for name in ("clean_nmrgym_proton.py", "export_nmrgym_proton_qc.py"):
            z.write(Path(__file__).parent / name, "scripts/" + name)
    print(json.dumps(manifest["official_train"], indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for option in ("official", "cache", "clean", "archive"):
        p.add_argument("--" + option, type=Path, required=True)
    a = p.parse_args()
    RDLogger.DisableLog("rdApp.*")
    if a.archive.exists():
        raise FileExistsError(a.archive)
    with tempfile.TemporaryDirectory(dir=a.archive.parent) as tmp:
        output = Path(tmp) / a.archive.name
        export_archive(a.official, a.cache, a.clean, output)
        with zipfile.ZipFile(output) as z:
            if z.testzip() is not None:
                raise ValueError("Damaged output archive")
        output.rename(a.archive)

"""Apply frozen exclusions to the released P/F reference archives before sampling."""

import json
from importlib.resources import files


def solution_test_cohort(rows, nucleus, reference_sha256, full_test=False):
    if full_test:
        return rows, "full-test"
    manifest = json.loads(
        files("openmolspec")
        .joinpath("assets/solution-test-exclusions.json")
        .read_text()
    )
    policy = manifest["nuclei"].get(nucleus)
    if not policy or reference_sha256 != policy["reference_sha256"]:
        return rows, "full-test"
    excluded = set(map(str, policy["excluded_record_ids"]))
    retained = [r for r in rows if r["record_id"] not in excluded]
    if len(rows) != policy["total_records"] or len(rows) - len(retained) != len(
        excluded
    ):
        raise ValueError(
            "Reference rows disagree with the frozen P/F exclusion manifest"
        )
    return retained, manifest["name"]

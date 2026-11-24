"""Write manuscript source data from the frozen forward-prediction reports to stdout."""

import csv
import json
from pathlib import Path
import sys

RESULTS = Path(__file__).resolve().parents[1] / "results"


def read(name):
    return json.loads((RESULTS / name).read_text())


def main():
    tasks = read("forward_benchmark_summary.json")["tasks"]
    cosine_file = "forward_cosine_similarity.json"
    profiles = read(cosine_file)["tasks"]
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(
        [
            "task",
            "reference",
            "cohort",
            "metric",
            "value",
            "scored",
            "count_unit",
            "total_observations_or_sampled",
            "evidence_under_results",
        ]
    )
    emitted = set()

    def write(task, reference, cohort, metrics, values, count, unit, total, source):
        emitted.add(task)
        for metric in metrics:
            writer.writerow(
                [
                    task,
                    reference,
                    cohort,
                    metric,
                    values[metric],
                    count,
                    unit,
                    total,
                    source,
                ]
            )

    for nucleus in ("1H", "13C"):
        task = "nmr.forward." + nucleus
        for reference, values in profiles[task]["splits"].items():
            write(
                task,
                reference,
                "audit",
                (
                    "count_penalized_error_ppm",
                    "matched_peak_mae_ppm",
                    "matched_peak_r2",
                    "cosine",
                ),
                values,
                values["molecules"],
                "molecules",
                values["examples"],
                cosine_file,
            )

    for nucleus in ("31P", "19F", "11B", "29Si"):
        task = "nmr.forward." + nucleus
        profile = profiles[task]
        views = {"full_test": profile.get("full_test", profile)}
        if "full_test" in profile:
            views["pf-fixed-99-v1"] = profile
        for cohort, values in views.items():
            write(
                task,
                "measured single-environment solution shifts",
                cohort,
                (
                    "observation_mae_ppm",
                    "molecule_macro_mae_ppm",
                    "molecule_weighted_r2",
                    "cosine",
                ),
                values,
                values["molecules"],
                "connectivities",
                values["observations"],
                cosine_file,
            )

    source = "hsqc_benchmarks/metrics.json"
    for panel, rows in read(source)["panels"].items():
        cohorts = (
            ("all_records", "outside_2d_fitting_pools", "outside_all_listed_pools")
            if panel == "2dnmrgym"
            else ("all_records",)
        )
        for cohort in cohorts:
            values = rows[cohort]
            metrics = ["observed_hit_fraction_micro"]
            if panel == "2dnmrgym":
                metrics.extend(
                    [
                        "cosine",
                        "correct_atom_fraction_of_observed",
                        "carbon_mae_ppm",
                        "proton_mae_ppm",
                    ]
                )
            else:
                metrics.extend(["partial_list_cosine", "candidate_coverage"])
            write(
                "nmr.hsqc.transpeaknet",
                panel,
                cohort,
                metrics,
                values,
                values["spectra"],
                "spectra",
                values["observed"],
                source,
            )

    task = "vibrational.forward"
    values = profiles[task]
    write(
        task,
        "QM9S harmonic calculation",
        "full_test",
        ["ir_cosine", "raman_cosine"],
        values,
        values["molecules"],
        "molecules",
        values["molecules"],
        cosine_file,
    )
    for backend in ("glacier", "iceberg"):
        task = "ms.forward." + backend
        source = "forward_confirmation_" + backend + ".json"
        report = read(source)
        for condition in ("baseline", "candidate"):
            write(
                task,
                "MassSpecGym measured tandem MS",
                "confirmation_" + condition,
                ["cosine_similarity"],
                report[condition],
                report["confirmed_identities"],
                "molecules",
                report["confirmation_sample_size"],
                source,
            )
    if emitted != set(tasks):
        raise ValueError("Exported tasks differ from the released forward catalogue")


if __name__ == "__main__":
    main()

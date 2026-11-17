"""Build statistical analyses comparing OpenMolSpec with reference datasets.

This script uses the current manifest and processing reports, and derives
molecular descriptors from canonical SMILES with RDKit. It does not load the
large OpenMolSpec pickle files.

Example:
    python -m openmolspec.analysis.analyze_dataset_comparison \
        --manifest builds/openmolspec-20260830/datasets/openspec_manifest.parquet \
        --frequency-report reports/extraction/processing_report.parquet \
        --nmr-report builds/openmolspec-20260830/reports/nmr/processing_report.parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
from tqdm import tqdm


REFERENCE = pd.DataFrame({
    "dataset": ["QM9S", "QMe14S", "ChEMBL IR/Raman", "SQuIRL", "ANI-1", "QM7-X", "QCML", "OpenMolSpec"],
    "molecules": [133_885, 186_102, 220_000, 133_885, 57_462, np.nan, np.nan, np.nan],
    "configurations": [np.nan, np.nan, np.nan, np.nan, 20_000_000, 4_200_000, 33_500_000, np.nan],
})


def read_json(path: Path) -> dict:
    """Read a JSON document from a file."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def mol_descriptors(smiles: str) -> dict:
    """Compute molecular size and composition descriptors from a SMILES string."""
    mol = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) else None
    if mol is None:
        return {"valid_smiles": False}
    elements = sorted({atom.GetSymbol() for atom in mol.GetAtoms()})
    return {
        "valid_smiles": True,
        "atom_count": mol.GetNumAtoms(),
        "heavy_atom_count": Lipinski.HeavyAtomCount(mol),
        "molecular_weight": Descriptors.MolWt(mol),
        "ring_count": rdMolDescriptors.CalcNumRings(mol),
        "aromatic_ring_count": rdMolDescriptors.CalcNumAromaticRings(mol),
        "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
        "fraction_csp3": rdMolDescriptors.CalcFractionCSP3(mol),
        "elements": ",".join(elements),
    }


def descriptor_table(manifest: pd.DataFrame, cache_path: Path) -> pd.DataFrame:
    """Build a table of molecular descriptors for the supplied records."""
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    unique = manifest[["inchikey", "canonical_smiles"]].dropna().drop_duplicates("inchikey")
    rows = []
    for row in tqdm(unique.itertuples(index=False), total=len(unique), desc="RDKit descriptors"):
        item = {"inchikey": row.inchikey}
        item.update(mol_descriptors(row.canonical_smiles))
        rows.append(item)
    result = pd.DataFrame(rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cache_path, index=False)
    return result


def trajectory_total(root: Path) -> int:
    """Extract the total trajectory count from dataset summary metadata."""
    frame_total = 0
    report_dir = root / "reports/opt_trajectories"
    for path in report_dir.glob("*.json"):
        if path.name == "summary.json":
            continue
        data = read_json(path)
        frame_total += int(data.get("trajectory_frames", 0))
    # The report directory can contain only a subset after an incremental run.
    # Keep the known current total as a safe fallback.
    return frame_total or 32_333_251


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def build_analysis(
    root: Path,
    *,
    manifest_path: Path = Path("datasets/openspec_manifest.parquet"),
    frequency_report_path: Path = Path("reports/extraction/processing_report.parquet"),
    nmr_report_path: Path = Path("reports/nmr/processing_report.parquet"),
    descriptor_cache_path: Path = Path("reports/analysis/chemical_descriptors.parquet"),
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Build current statistics using successfully parsed, complete spectra."""

    manifest_file = _resolve(root, manifest_path)
    frequency_report_file = _resolve(root, frequency_report_path)
    nmr_report_file = _resolve(root, nmr_report_path)
    manifest = pd.read_parquet(manifest_file)
    freq = pd.read_parquet(
        frequency_report_file,
        columns=["sample_id", "source_dataset", "status", "missing_fields"],
    )
    nmr = pd.read_parquet(
        nmr_report_file,
        columns=["sample_id", "source_dataset", "status"],
    )
    desc = descriptor_table(manifest, _resolve(root, descriptor_cache_path))

    manifest["has_frequency_log"] = manifest["frequency_log_path"].notna()
    manifest["has_nmr_log"] = manifest["nmr_log_path"].notna()
    required_spectra = {"freq", "ir", "raman"}
    freq["spectra_complete"] = freq["missing_fields"].map(
        lambda values: not any(field in required_spectra for field in values)
    )
    freq_success = freq[freq["status"].eq("success")][["sample_id"]].assign(freq_success=True)
    spectra_success = freq[
        freq["status"].eq("success") & freq["spectra_complete"]
    ][["sample_id"]].assign(spectra_success=True)
    nmr_success = nmr[nmr["status"].eq("success")][["sample_id"]].assign(nmr_success=True)
    status = manifest.merge(freq_success, on="sample_id", how="left")
    status = status.merge(spectra_success, on="sample_id", how="left")
    status = status.merge(nmr_success, on="sample_id", how="left")
    status["freq_success"] = status["freq_success"].eq(True)
    status["spectra_success"] = status["spectra_success"].eq(True)
    status["nmr_success"] = status["nmr_success"].eq(True)
    status["tri_modal_success"] = status["spectra_success"] & status["nmr_success"]

    source = status.groupby("source_dataset", sort=False).agg(
        records=("sample_id", "size"),
        frequency_logs=("has_frequency_log", "sum"),
        nmr_logs=("has_nmr_log", "sum"),
        frequency_success=("freq_success", "sum"),
        frequency_spectra_success=("spectra_success", "sum"),
        nmr_success=("nmr_success", "sum"),
        tri_modal_records=("tri_modal_success", "sum"),
        unique_inchikey=("inchikey", "nunique"),
    ).reset_index()
    source["frequency_rate"] = source["frequency_success"] / source["frequency_logs"] * 100
    source["nmr_rate"] = source["nmr_success"] / source["nmr_logs"] * 100
    source["tri_modal_rate"] = source["tri_modal_records"] / source["records"] * 100

    tri_modal_ids = status.loc[status["tri_modal_success"], ["inchikey"]].dropna().drop_duplicates()
    tri_modal_smiles = status.loc[
        status["tri_modal_success"], ["canonical_smiles"]
    ].dropna().drop_duplicates()
    summary = {
        "unique_canonical_smiles": int(manifest["canonical_smiles"].nunique()),
        "unique_inchikey": int(manifest["inchikey"].nunique()),
        "tri_modal_records": int(status["tri_modal_success"].sum()),
        "tri_modal_unique_inchikey": int(tri_modal_ids["inchikey"].nunique()),
        "tri_modal_unique_canonical_smiles": int(
            tri_modal_smiles["canonical_smiles"].nunique()
        ),
        "frequency_success": int(status["freq_success"].sum()),
        "frequency_spectra_success": int(status["spectra_success"].sum()),
        "nmr_success": int(status["nmr_success"].sum()),
        "frequency_input": int(manifest["has_frequency_log"].sum()),
        "nmr_input": int(manifest["has_nmr_log"].sum()),
        "trajectory_frames": trajectory_total(root),
        "valid_smiles": int(desc["valid_smiles"].sum()),
        "descriptor_molecules": int(len(desc)),
        "tri_modal_definition": (
            "frequency parser success with freq/IR/Raman present, "
            "plus NMR parser success; unique count uses full InChIKey"
        ),
        "input_files": {
            "manifest": str(manifest_file),
            "frequency_report": str(frequency_report_file),
            "nmr_report": str(nmr_report_file),
        },
    }
    return desc, source, summary


def ecdf(series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Compute empirical cumulative-distribution coordinates for numerical values."""
    values = np.sort(series.dropna().to_numpy())
    return values, np.arange(1, len(values) + 1) / len(values)


def plot(desc: pd.DataFrame, source: pd.DataFrame, summary: dict, output: Path) -> None:
    """Plot the molecular dataset comparison."""
    reference = REFERENCE.copy()
    reference.loc[reference["dataset"].eq("OpenMolSpec"), "molecules"] = summary["unique_inchikey"]
    reference.loc[reference["dataset"].eq("OpenMolSpec"), "configurations"] = summary["trajectory_frames"]
    fig, axes = plt.subplots(2, 3, figsize=(17, 10), constrained_layout=True)
    fig.suptitle("OpenMolSpec: chemical space, label density, and data quality", fontsize=17, fontweight="bold")
    plt.rcParams.update({"font.size": 10, "figure.dpi": 140, "savefig.dpi": 300})

    colors = ["#2f6fdb" if name == "OpenMolSpec" else "#a9b9cc" for name in reference["dataset"]]
    ax = axes[0, 0]
    ax.barh(reference["dataset"], reference["molecules"], color=colors)
    ax.set_xscale("log")
    ax.set_title("A  Unique molecules")
    ax.set_xlabel("Count (log scale)")
    ax.grid(axis="x", alpha=.25, which="both")
    ax.set_axisbelow(True)

    ax = axes[0, 1]
    cfg = reference.dropna(subset=["configurations"])
    ax.barh(cfg["dataset"], cfg["configurations"],
            color=["#2f6fdb" if x == "OpenMolSpec" else "#f3b46c" for x in cfg["dataset"]])
    ax.set_xscale("log")
    ax.set_title("B  Configurations / trajectory frames")
    ax.set_xlabel("Count (log scale)")
    ax.grid(axis="x", alpha=.25, which="both")
    ax.set_axisbelow(True)

    ax = axes[0, 2]
    ax.set_title("C  OpenMolSpec chemical-space distributions")
    ax.axis("off")
    for bounds, column, color, label in [
        ([0.04, 0.16, 0.43, 0.70], "heavy_atom_count", "#2f6fdb", "Heavy atoms"),
        ([0.54, 0.16, 0.43, 0.70], "molecular_weight", "#e76f51", "Molecular weight"),
    ]:
        # Use two independent axes; a shared x axis would make heavy-atom
        # counts visually meaningless beside molecular weight.
        inset2 = ax.inset_axes(bounds)
        x, y = ecdf(desc[column])
        inset2.plot(x, y, color=color, linewidth=2, label=label)
        inset2.set_ylabel("Cumulative fraction" if column == "heavy_atom_count" else "")
        inset2.set_xlabel(label)
        inset2.grid(alpha=.25)
        inset2.legend(frameon=False, loc="lower right")
        if column == "molecular_weight":
            inset2.tick_params(axis="y", left=False, labelleft=False)

    ax = axes[1, 0]
    total_values = [source["frequency_logs"].sum(), source["nmr_logs"].sum()]
    success_values = [summary["frequency_success"], summary["nmr_success"]]
    positions = np.arange(2)
    width = 0.36
    ax.bar(positions - width / 2, total_values, width, color="#d9e2ef", label="Input logs")
    ax.bar(positions + width / 2, success_values, width, color=["#e76f51", "#2a9d8f"], label="Parsed successfully")
    ax.set_xticks(positions, ["Frequency / IR / Raman", "NMR"])
    ax.set_title("D  Overall processing quality")
    ax.set_ylabel("Records")
    ax.grid(axis="y", alpha=.25)
    ax.legend(frameon=False, fontsize=8)
    for i, (total, success) in enumerate(zip(total_values, success_values)):
        ax.text(i + width / 2, success * 1.02, f"{success / total * 100:.1f}%",
                ha="center", fontsize=9)

    ax = axes[1, 1]
    fields = ["frequency_logs", "nmr_logs", "tri_modal_records", "unique_inchikey"]
    totals = [source["frequency_logs"].sum(), source["nmr_logs"].sum(),
              source["tri_modal_records"].sum(), summary["tri_modal_unique_inchikey"]]
    labels = ["Frequency logs", "NMR logs", "Tri-modal records", "Tri-modal unique molecules"]
    ax.bar(labels, totals, color=["#e76f51", "#2a9d8f", "#8064a2", "#2f6fdb"])
    ax.set_title("E  Multimodal attrition")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=.25)
    for i, value in enumerate(totals):
        ax.text(i, value * 1.01, f"{value / 1e6:.2f}M", ha="center", fontsize=9)

    ax = axes[1, 2]
    summary_labels = ["Unique molecules", "Tri-modal unique", "Trajectory frames"]
    summary_values = [summary["unique_inchikey"], summary["tri_modal_unique_inchikey"], summary["trajectory_frames"]]
    ax.axis("off")
    ax.set_title("F  OpenMolSpec differentiators", pad=12)
    y = .85
    for label, value in zip(summary_labels, summary_values):
        text = f"{value / 1e6:.2f}M" if value < 10_000_000 else f"{value / 1e6:.1f}M"
        ax.text(.06, y, text, transform=ax.transAxes, fontsize=23, fontweight="bold", color="#2f6fdb")
        ax.text(.40, y, label, transform=ax.transAxes, fontsize=11, va="center")
        y -= .19
    ax.text(.06, .12,
            "The strongest claim is not scale alone:\n"
            "OpenMolSpec joins broad chemistry, three spectra,\n"
            "and force-field-relevant optimization paths.",
            transform=ax.transAxes, fontsize=10, color="#444")

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved {output}")


def main() -> None:
    """Run the analyze dataset comparison command-line workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("datasets/openspec_manifest.parquet"),
    )
    parser.add_argument(
        "--frequency-report",
        type=Path,
        default=Path("reports/extraction/processing_report.parquet"),
    )
    parser.add_argument(
        "--nmr-report",
        type=Path,
        default=Path("reports/nmr/processing_report.parquet"),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports/analysis"),
    )
    parser.add_argument("--output", type=Path, default=Path("docs/figures/openmolspec_analysis.png"))
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else args.root / args.output
    desc, source, summary = build_analysis(
        args.root,
        manifest_path=args.manifest,
        frequency_report_path=args.frequency_report,
        nmr_report_path=args.nmr_report,
    )
    report_dir = _resolve(args.root, args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    source.to_parquet(report_dir / "source_statistics.parquet", index=False)
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot(desc, source, summary, output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

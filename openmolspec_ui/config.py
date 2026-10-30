from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


APP_ROOT = Path(__file__).resolve().parents[1]


def _openmolspec_root() -> Path:
    configured = os.environ.get("OPENMOLSPEC_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return APP_ROOT


def _newest(paths: Iterable[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    return max(existing, key=lambda item: item.stat().st_mtime_ns) if existing else None


@dataclass(frozen=True)
class ModelAssets:
    root: Path
    hessian_hi_checkpoint: Path | None
    hessian_hij_checkpoint: Path | None
    dedipole_checkpoint: Path | None
    depolar_checkpoint: Path | None
    nmr_checkpoint: Path | None
    gap_checkpoint: Path | None
    retrieval_checkpoint: Path | None
    generation_checkpoint: Path | None
    spectrum_lmdb: Path | None
    generation_predictions: Path | None
    nmr_normalizer: Path | None

    @property
    def root_available(self) -> bool:
        return self.root.is_dir()

    def capability_status(self) -> dict[str, tuple[bool, str]]:
        return {
            "构象 → 谱图": (
                all(
                    checkpoint is not None
                    for checkpoint in (
                        self.hessian_hi_checkpoint,
                        self.hessian_hij_checkpoint,
                        self.dedipole_checkpoint,
                        self.depolar_checkpoint,
                        self.nmr_checkpoint,
                    )
                ),
                "1M theoretical · Hessian / response / H-C NMR",
            ),
            "谱图 → 结构检索": (
                self.spectrum_lmdb is not None,
                "OpenMolSpec theoretical test set",
            ),
            "谱图 → HOMO–LUMO gap": (
                self.gap_checkpoint is not None,
                "Shared Spectroscopy Transformer · 1M",
            ),
            "谱图 → 结构生成": (
                self.generation_checkpoint is not None
                and self.generation_predictions is not None,
                "Vib2Mol · cached test set inference",
            ),
        }


def discover_assets(root: Path | None = None) -> ModelAssets:
    root = (root or _openmolspec_root()).resolve()
    hessian_hi_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/structure2hessian/equiformer-v3/"
            "hi-direct-r5/seed-624/*/artifacts/"
            "equiformer_v3_structure2hessian_best.pt"
        )
    )
    hessian_hij_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/structure2hessian/equiformer-v3/"
            "hij-direct-r5/seed-624/*/artifacts/"
            "equiformer_v3_structure2hessian_best.pt"
        )
    )
    dedipole_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/structure2response/equiformer-v3/"
            "dedipole-direct-r5/seed-624/*/artifacts/"
            "equiformer_v3_structure2response_best.pt"
        )
    )
    depolar_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/structure2response/equiformer-v3/"
            "depolar-direct-r5/seed-624/*/artifacts/"
            "equiformer_v3_structure2response_best.pt"
        )
    )
    nmr_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/structure2nmr/equiformer-v3/"
            "hc-shifts-r5/seed-624/*/artifacts/"
            "equiformer_v3_structure2nmr_best.pt"
        )
    ) or _newest(
        root.glob(
            "runs/openmolspec-v1-ks200k/structure2nmr/equiformer-v3/"
            "hc-shifts-r5/seed-624/*/artifacts/"
            "equiformer_v3_structure2nmr_best.pt"
        )
    )
    gap_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/spectrum2property/vib2conf/"
            "ir-raman-hc-gap-shared-pooling-v2/seed-624/*/artifacts/"
            "vib2conf_spectrum2property_best.pt"
        )
    )
    retrieval_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/spectrum2structure/vib2mol/"
            "ir-raman-hc-generation-v1/seed-624/*/artifacts/vib2mol/"
            "checkpoints/**/best_recall.pth"
        )
    ) or _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/spectrum2structure/vib2mol/"
            "*/seed-624/*/artifacts/vib2mol/checkpoints/**/best_recall.pth"
        )
    ) or _newest(
        root.glob(
            "runs/openmolspec-v1-ks200k/spectrum2structure/vib2mol/"
            "*/seed-624/*/artifacts/vib2mol/checkpoints/**/best_recall.pth"
        )
    )
    generation_checkpoint = _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/spectrum2structure/vib2mol/"
            "ir-raman-hc-generation-v1/seed-624/*/artifacts/vib2mol/"
            "checkpoints/**/best_acc.pth"
        )
    ) or _newest(
        root.glob(
            "runs/openmolspec-v1-ks1000k/spectrum2structure/vib2mol/"
            "*/seed-624/*/artifacts/vib2mol/checkpoints/**/best_acc.pth"
        )
    ) or _newest(
        root.glob(
            "runs/openmolspec-v1-ks200k/spectrum2structure/vib2mol/"
            "*/seed-624/*/artifacts/vib2mol/checkpoints/**/best_acc.pth"
        )
    )
    spectrum_lmdb = root / (
        "benchmark_data/release_v1_ks200k_hc_nmr_minmax/"
        "vib2mol/openspec_test.lmdb"
    )
    if not spectrum_lmdb.is_file():
        spectrum_lmdb = None
    generation_predictions = _newest(
        root.glob("runs/vib2mol/*/generation_predictions.jsonl")
    )
    nmr_normalizer = _newest(root.glob("runs/vib2mol/*/nmr_normalizer.json"))
    if nmr_normalizer is None:
        candidate = root / (
            "benchmark_data/release_v1_ks200k_hc_nmr_minmax/"
            "vib2mol/.cache/nmr_median_iqr.json"
        )
        nmr_normalizer = candidate if candidate.is_file() else None
    return ModelAssets(
        root=root,
        hessian_hi_checkpoint=hessian_hi_checkpoint,
        hessian_hij_checkpoint=hessian_hij_checkpoint,
        dedipole_checkpoint=dedipole_checkpoint,
        depolar_checkpoint=depolar_checkpoint,
        nmr_checkpoint=nmr_checkpoint,
        gap_checkpoint=gap_checkpoint,
        retrieval_checkpoint=retrieval_checkpoint,
        generation_checkpoint=generation_checkpoint,
        spectrum_lmdb=spectrum_lmdb,
        generation_predictions=generation_predictions,
        nmr_normalizer=nmr_normalizer,
    )

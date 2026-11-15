"""Export completed JSON training logs to TensorBoard scalar event files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def run_label(run_dir: Path) -> str:
    runs_root = (Path.cwd() / "runs").resolve()
    try:
        parts = run_dir.resolve().relative_to(runs_root).parts
    except ValueError:
        parts = (run_dir.name,)
    return "__".join(parts)


def export_run(run_dir: Path, output_root: Path) -> Path:
    try:
        from torch.utils.tensorboard import SummaryWriter
    except ImportError as error:
        raise RuntimeError("Install TensorBoard in .venv: .venv/bin/python -m pip install tensorboard") from error

    history_path = run_dir / "history.json"
    if not history_path.is_file():
        raise FileNotFoundError(history_path)
    history = json.loads(history_path.read_text(encoding="utf-8"))
    if not history:
        raise ValueError(f"No epoch metrics in {history_path}")

    event_path = run_dir / "progress.jsonl"
    if not event_path.is_file():
        raise FileNotFoundError(event_path)
    output = output_root / run_label(run_dir)
    output.mkdir(parents=True, exist_ok=False)
    with SummaryWriter(log_dir=str(output)) as writer:
        for row in history:
            epoch = row["epoch"]
            for source, tag in (
                ("train_loss", "loss/train_epoch"),
                ("val_loss", "loss/validation_epoch"),
                ("spectrum_to_molecule_recall_at_1", "retrieval/spectrum_to_molecule_recall_at_1"),
                ("molecule_to_spectrum_recall_at_1", "retrieval/molecule_to_spectrum_recall_at_1"),
                ("learning_rate", "train/learning_rate_epoch"),
            ):
                if source in row:
                    writer.add_scalar(tag, row[source], epoch)

        steps_per_epoch = None
        with event_path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                if record.get("event") == "run_started":
                    steps_per_epoch = (record.get("steps_per_epoch")
                                       or record.get("train_steps_per_epoch"))
                elif (record.get("event") == "train_progress"
                      and steps_per_epoch and "window_loss" in record):
                    step = (record["epoch"] - 1) * steps_per_epoch + record["step"]
                    writer.add_scalar("loss/train_window", record["window_loss"], step)
                    if record.get("learning_rate") is not None:
                        writer.add_scalar("train/learning_rate_step", record["learning_rate"], step)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path,
                        help="Training run directories containing history.json and progress.jsonl")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/tensorboard"),
                        help="Directory for TensorBoard event files (default: runs/tensorboard)")
    args = parser.parse_args()
    for run_dir in args.run_dirs:
        print(export_run(run_dir, args.output_dir))


if __name__ == "__main__":
    main()

"""Train and evaluate a formula-conditioned NMR-to-SMILES baseline."""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import torch
import torch.distributed as dist
from torch import nn
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, IterableDataset
from tqdm import tqdm

from .data import clean_text
from .integrity import verify_training_files
from .model import PAD, ModelConfig, SpectrumToSmiles, encode_source, encode_target
from .molecule_tokenizer import encode_molecules
from .structured import collate_structured_sources, encode_structured_source


DATA_FORMAT_VERSION = 2
CHECKPOINT_VERSION = 3


def log_event(directory: Path, event: str, **fields) -> None:
    """Print and persist one JSON event; callers restrict DDP writes to rank 0."""
    record = {"time": datetime.now(timezone.utc).isoformat(),
              "event": event, **fields}
    line = json.dumps(record, ensure_ascii=False)
    with (directory / "progress.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
        stream.flush()
    print(line, flush=True)


def create_run_dir(root: Path, device: torch.device,
                   rank: int = 0, world_size: int = 1) -> Path:
    """Create one UUID directory per job and share its path across DDP ranks."""
    location = [None]
    if rank == 0:
        while True:
            run_dir = (root / uuid.uuid4().hex).resolve()
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                continue
        location[0] = str(run_dir)
    if world_size > 1:
        dist.broadcast_object_list(location, src=0, device=device)
    run_dir = Path(location[0])
    if rank == 0:
        log_event(run_dir, "run_directory_created", run_id=run_dir.name,
                  run_dir=str(run_dir), run_root=str(root.resolve()))
    return run_dir


def show_tqdm(mode: str, rank: int = 0) -> bool:
    return rank == 0 and (mode == "always" or
                          (mode == "auto" and sys.stderr.isatty()))


def require_data_format(data_dir: Path) -> dict:
    summary = json.loads((data_dir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("format_version") != DATA_FORMAT_VERSION:
        raise ValueError(f"Expected H/C dataset format {DATA_FORMAT_VERSION}; re-run preparation")
    verification_path = data_dir / "verification.json"
    if not verification_path.is_file():
        raise ValueError("Run python -m spec2struct.verify before training or evaluation")
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if verification.get("status") != "passed" or verification.get("counts", {}).get("examples") != summary["counts"].get("examples"):
        raise ValueError("Prepared dataset has not passed H/C verification")
    verify_training_files(data_dir, verification)
    return verification


def data_fingerprint(verification: dict) -> dict[str, str]:
    return {split: verification["files"][split]["sha256"] for split in ("train", "val")}


def apply_modality_dropout(item: dict, rng: random.Random,
                           drop_h_prob: float, drop_c_prob: float) -> dict:
    """Expose H-only, C-only and H+C views without ever hiding both."""
    if item["modality_mask"] != [1, 1]:
        return item
    draw = rng.random()
    if draw < drop_h_prob:
        return {**item, "modality_mask": [0, 1]}
    if draw < drop_h_prob + drop_c_prob:
        return {**item, "modality_mask": [1, 0]}
    return item


def rotate_nmr_records(item: dict, rng: random.Random) -> dict:
    """Vary which retained spectrum appears first when the input is truncated."""
    rotated = dict(item)
    for key in ("h_nmr", "c_nmr"):
        records = item[key]
        if len(records) > 1:
            start = rng.randrange(len(records))
            rotated[key] = records[start:] + records[:start]
    return rotated


class JsonlExamples(IterableDataset):
    def __init__(self, path: Path, shuffle_size: int = 0, seed: int = 0,
                 drop_h_prob: float = 0.0, drop_c_prob: float = 0.0,
                 augment_records: bool = False, rank: int = 0,
                 world_size: int = 1):
        self.path = path
        self.shuffle_size = shuffle_size
        self.seed = seed
        self.drop_h_prob = drop_h_prob
        self.drop_c_prob = drop_c_prob
        self.augment_records = augment_records
        self.rank = rank
        self.world_size = world_size

    def __iter__(self):
        rng = random.Random(self.seed)
        buffer = []
        with self.path.open("r", encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                if index % self.world_size != self.rank:
                    continue
                example = json.loads(line)
                if self.augment_records:
                    example = rotate_nmr_records(example, rng)
                example = apply_modality_dropout(example, rng,
                                                 self.drop_h_prob, self.drop_c_prob)
                if self.shuffle_size == 0:
                    yield example
                else:
                    buffer.append(example)
                    if len(buffer) >= self.shuffle_size:
                        index = rng.randrange(len(buffer))
                        yield buffer.pop(index)
        while buffer:
            yield buffer.pop(rng.randrange(len(buffer)))


def make_collate(config: ModelConfig, include_formula: bool = True,
                 include_alignment_source: bool = False):
    def collate(examples: list[dict]):
        encoder = (encode_structured_source if config.input_representation == "structured"
                   else encode_source)
        def pad_sources(sources):
            return (collate_structured_sources(sources)
                    if config.input_representation == "structured" else
                    nn.utils.rnn.pad_sequence(
                        [torch.tensor(value) for value in sources],
                        batch_first=True, padding_value=PAD))
        sources = [encoder(item["formula"], item["h_nmr"], item["c_nmr"],
                           item["modality_mask"], config.max_source,
                           include_formula=include_formula)
                   for item in examples]
        targets = (encode_molecules([item["smiles"] for item in examples], config.max_target)
                   if config.molecule_tokenizer == "mol_bpe" else
                   [encode_target(item["smiles"], config.max_target, "byte")
                    for item in examples])
        source = pad_sources(sources)
        target = nn.utils.rnn.pad_sequence(
            [torch.tensor(value) for value in targets], batch_first=True, padding_value=PAD)
        if include_alignment_source:
            alignment_sources = [encoder(
                item["formula"], item["h_nmr"], item["c_nmr"],
                item["modality_mask"], config.max_source, include_formula=False)
                for item in examples]
            return source, target, examples, pad_sources(alignment_sources)
        return source, target, examples
    return collate


def choose_device(requested: str) -> torch.device:
    name = "cuda" if requested == "auto" and torch.cuda.is_available() else requested
    if name == "auto":
        name = "cpu"
    if name.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return torch.device(name)


def setup_distributed(requested: str) -> tuple[torch.device, int, int]:
    """Use one process per GPU under torchrun; allow CPU/Gloo for smoke tests."""
    world_size = int(os.environ.get("WORLD_SIZE", "1"))
    if world_size == 1:
        return choose_device(requested), 0, 1
    rank = int(os.environ["RANK"])
    local_rank = int(os.environ["LOCAL_RANK"])
    if requested == "auto":
        device = torch.device(f"cuda:{local_rank}") if torch.cuda.is_available() else torch.device("cpu")
    elif requested.startswith("cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        device = torch.device(f"cuda:{local_rank}")
    else:
        device = choose_device(requested)
    if device.type == "cuda":
        torch.cuda.set_device(device)
    if device.type == "cuda":
        dist.init_process_group(backend="nccl", device_id=device)
    else:
        dist.init_process_group(backend="gloo")
    return device, rank, world_size


def run_loss(model: SpectrumToSmiles, loader, device: torch.device,
             max_batches: int | None = None, optimizer=None,
             scheduler=None,
             log_every: int | None = None,
             progress: Callable[[dict], None] | None = None,
             total_batches: int | None = None,
             show_tqdm: bool = False, description: str = "",
             aggregate_progress: bool = False,
             alignment_weight: float = 0.0,
             auxiliary_metrics: dict | None = None) -> float:
    total_loss = 0.0
    total_tokens = 0
    total_alignment_loss = 0.0
    total_alignment_examples = 0
    window_loss = 0.0
    window_tokens = 0
    window_alignment_loss = 0.0
    window_alignment_examples = 0
    started = time.monotonic()
    steps = 0
    last_reported = 0

    def report(step: int) -> None:
        nonlocal window_loss, window_tokens, window_alignment_loss
        nonlocal window_alignment_examples, last_reported
        reported_loss, reported_tokens, seen_tokens = window_loss, window_tokens, total_tokens
        reported_alignment_loss = window_alignment_loss
        reported_alignment_examples = window_alignment_examples
        if aggregate_progress and dist.is_available() and dist.is_initialized():
            values = torch.tensor([window_loss, window_tokens, total_tokens,
                                   window_alignment_loss, window_alignment_examples],
                                  dtype=torch.float64, device=device)
            dist.all_reduce(values)
            (reported_loss, reported_tokens, seen_tokens, reported_alignment_loss,
             reported_alignment_examples) = values.tolist()
        if progress is not None and window_tokens:
            elapsed = time.monotonic() - started
            fields = {"step": step, "total_steps": total_batches,
                      "window_loss": reported_loss / reported_tokens,
                      "learning_rate": (optimizer.param_groups[0]["lr"]
                                        if optimizer is not None else None),
                      "tokens_seen": int(seen_tokens),
                      "elapsed_seconds": round(elapsed, 1),
                      "steps_per_second": round(step / max(elapsed, 1e-9), 3)}
            if reported_alignment_examples:
                fields["alignment_window_loss"] = (
                    reported_alignment_loss / reported_alignment_examples)
                fields["joint_window_loss"] = (fields["window_loss"]
                                               + alignment_weight * fields["alignment_window_loss"])
            progress(fields)
        window_loss = 0.0
        window_tokens = 0
        window_alignment_loss = 0.0
        window_alignment_examples = 0
        last_reported = step

    batches = itertools.islice(loader, max_batches) if max_batches is not None else loader
    with tqdm(batches, total=total_batches, desc=description,
              disable=not show_tqdm, dynamic_ncols=True, file=sys.stderr) as bar:
        for steps, batch in enumerate(bar, start=1):
            source, target = batch[:2]
            source, target = source.to(device), target.to(device)
            with torch.set_grad_enabled(optimizer is not None):
                if optimizer is not None and alignment_weight > 0:
                    if len(batch) != 4:
                        raise ValueError("Joint generation requires alignment sources")
                    logits, alignment_loss = model(
                        source, target, task="generate_with_alignment",
                        alignment_source=batch[3].to(device))
                else:
                    logits = model(source, target[:, :-1])
                gold = target[:, 1:]
                loss_sum = nn.functional.cross_entropy(
                    logits.reshape(-1, logits.shape[-1]), gold.reshape(-1),
                    ignore_index=PAD, reduction="sum")
                tokens = int(gold.ne(PAD).sum())
                loss = loss_sum / max(tokens, 1)
                if optimizer is not None:
                    if dist.is_available() and dist.is_initialized():
                        global_tokens = torch.tensor(tokens, device=device,
                                                     dtype=torch.long)
                        dist.all_reduce(global_tokens)
                        loss = loss_sum * (dist.get_world_size() / global_tokens.clamp_min(1))
                    if alignment_weight > 0:
                        loss = loss + alignment_weight * alignment_loss
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    if scheduler is not None:
                        scheduler.step()
            batch_loss = float(loss_sum.detach())
            total_loss += batch_loss
            total_tokens += tokens
            window_loss += batch_loss
            window_tokens += tokens
            if optimizer is not None and alignment_weight > 0:
                alignment_batch_loss = float(alignment_loss.detach()) * len(source)
                total_alignment_loss += alignment_batch_loss
                total_alignment_examples += len(source)
                window_alignment_loss += alignment_batch_loss
                window_alignment_examples += len(source)
            if log_every and (steps == 1 or steps % log_every == 0):
                report(steps)
                bar.set_postfix(loss=f"{total_loss / total_tokens:.3f}")
    if log_every and steps > last_reported:
        report(steps)
    if dist.is_available() and dist.is_initialized():
        values = torch.tensor([total_loss, total_tokens, total_alignment_loss,
                               total_alignment_examples], dtype=torch.float64,
                              device=device)
        dist.all_reduce(values)
        (total_loss, total_tokens, total_alignment_loss,
         total_alignment_examples) = values.tolist()
    if total_tokens == 0:
        raise ValueError("Split contains no usable examples")
    if auxiliary_metrics is not None and total_alignment_examples:
        auxiliary_metrics["alignment_train_loss"] = (
            total_alignment_loss / total_alignment_examples)
        auxiliary_metrics["joint_train_loss"] = (
            total_loss / total_tokens
            + alignment_weight * auxiliary_metrics["alignment_train_loss"])
    return total_loss / total_tokens


def run_alignment_loss(model: SpectrumToSmiles, loader, device: torch.device,
                       max_batches: int | None = None, optimizer=None,
                       scheduler=None,
                       log_every: int | None = None,
                       progress: Callable[[dict], None] | None = None,
                       total_batches: int | None = None,
                       show_tqdm: bool = False, description: str = "") -> float:
    total_loss = 0.0
    total_examples = 0
    window_loss = 0.0
    window_examples = 0
    seen_examples = 0
    started = time.monotonic()
    steps = 0
    last_reported = 0

    def report(step: int) -> None:
        nonlocal window_loss, window_examples, seen_examples, last_reported
        if window_examples:
            if dist.is_available() and dist.is_initialized():
                totals = torch.tensor([window_loss, window_examples],
                                      dtype=torch.float64, device=device)
                dist.all_reduce(totals)
                window_total_loss, window_total_examples = totals.tolist()
            else:
                window_total_loss, window_total_examples = window_loss, window_examples
            seen_examples += int(window_total_examples)
            if progress is not None:
                elapsed = time.monotonic() - started
                progress({"step": step, "total_steps": total_batches,
                          "window_loss": window_total_loss / window_total_examples,
                          "learning_rate": (optimizer.param_groups[0]["lr"]
                                            if optimizer is not None else None),
                          "examples_seen": seen_examples,
                          "elapsed_seconds": round(elapsed, 1),
                          "steps_per_second": round(step / max(elapsed, 1e-9), 3)})
        window_loss = 0.0
        window_examples = 0
        last_reported = step

    batches = itertools.islice(loader, max_batches) if max_batches is not None else loader
    with tqdm(batches, total=total_batches, desc=description,
              disable=not show_tqdm, dynamic_ncols=True, file=sys.stderr) as bar:
        for steps, (source, molecule, _) in enumerate(bar, start=1):
            source, molecule = source.to(device), molecule.to(device)
            with torch.set_grad_enabled(optimizer is not None):
                loss = model(source, molecule, task="align")
                if optimizer is not None:
                    optimizer.zero_grad(set_to_none=True)
                    loss.backward()
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    if scheduler is not None:
                        scheduler.step()
            batch_loss = float(loss.detach()) * source.shape[0]
            total_loss += batch_loss
            total_examples += source.shape[0]
            window_loss += batch_loss
            window_examples += source.shape[0]
            if log_every and (steps == 1 or steps % log_every == 0):
                report(steps)
                bar.set_postfix(loss=f"{total_loss / total_examples:.3f}")
    if log_every and steps > last_reported:
        report(steps)
    if dist.is_available() and dist.is_initialized():
        totals = torch.tensor([total_loss, total_examples], dtype=torch.float64,
                              device=device)
        dist.all_reduce(totals)
        total_loss, total_examples = totals.tolist()
    if not total_examples:
        raise ValueError("Alignment split contains no paired examples")
    return total_loss / total_examples


@torch.no_grad()
def evaluate_alignment(model: SpectrumToSmiles, path: Path,
                       max_examples: int, batch_size: int,
                       device: torch.device, seed: int = 2026) -> dict:
    """Compute bidirectional retrieval on a deterministic validation reservoir."""
    if max_examples < 2:
        raise ValueError("Alignment validation needs at least two examples")
    rng = random.Random(seed)
    selected = []
    with path.open("r", encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            item = json.loads(line)
            if index < max_examples:
                selected.append(item)
            else:
                replacement = rng.randrange(index + 1)
                if replacement < max_examples:
                    selected[replacement] = item
    if len(selected) < 2:
        raise ValueError("Alignment validation split contains fewer than two examples")
    collate = make_collate(model.config, include_formula=False)
    spectral, molecular = [], []
    model.eval()
    for start in range(0, len(selected), batch_size):
        source, target, _ = collate(selected[start:start + batch_size])
        spectrum_embedding, molecule_embedding = model.alignment_embeddings(
            source.to(device), target.to(device))
        spectral.append(spectrum_embedding.cpu())
        molecular.append(molecule_embedding.cpu())
    spectral = torch.cat(spectral)
    molecular = torch.cat(molecular)
    labels = torch.arange(len(selected))
    correct_s2m = correct_m2s = 0
    loss_s2m = loss_m2s = 0.0
    scale = (float(model.logit_scale.exp())
             if model.config.alignment_objective == "itm"
             else 1 / model.config.alignment_temperature)
    for start in range(0, len(selected), 512):
        end = min(start + 512, len(selected))
        s2m = spectral[start:end] @ molecular.T * scale
        m2s = molecular[start:end] @ spectral.T * scale
        correct_s2m += int((s2m.argmax(dim=1) == labels[start:end]).sum())
        correct_m2s += int((m2s.argmax(dim=1) == labels[start:end]).sum())
        loss_s2m += float(nn.functional.cross_entropy(
            s2m, labels[start:end], reduction="sum"))
        loss_m2s += float(nn.functional.cross_entropy(
            m2s, labels[start:end], reduction="sum"))
    total = len(selected)
    return {"examples": total,
            "spectrum_to_molecule_recall_at_1": correct_s2m / total,
            "molecule_to_spectrum_recall_at_1": correct_m2s / total,
            "val_loss": (loss_s2m + loss_m2s) / (2 * total)}


def molecule_details(smiles: str) -> tuple[str | None, str | None]:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdMolDescriptors
    RDLogger.DisableLog("rdApp.error")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, None
    return (Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True),
            rdMolDescriptors.CalcMolFormula(mol))


def rank_candidates(candidates: list[tuple[str, float]], formula: str) -> list[dict]:
    ranked = []
    for smiles, score in candidates:
        canonical, calculated = molecule_details(smiles)
        ranked.append({"smiles": smiles, "canonical_smiles": canonical,
                       "score": score, "valid": canonical is not None,
                       "formula_match": calculated == formula})
    return sorted(ranked, key=lambda row: (not row["formula_match"], -row["score"]))


@torch.no_grad()
def evaluate_generation(model: SpectrumToSmiles, path: Path, max_examples: int,
                        beam_size: int, modality: str = "available",
                        batch_size: int = 1, rank: int = 0, world_size: int = 1,
                        progress_every: int = 0, record_predictions: bool = False) -> dict:
    if max_examples < 1 or batch_size < 1:
        raise ValueError("Evaluation needs positive example and batch limits")
    if world_size > 1 and not dist.is_initialized():
        raise RuntimeError("Distributed evaluation requires an initialized process group")
    if record_predictions and world_size > 1:
        raise ValueError("Prediction recording requires single-process evaluation")
    predictions = []
    counts = {"examples": 0, "skipped_missing_modality": 0,
              "valid": 0, "formula_match": 0, "exact": 0}
    encoder = (encode_structured_source
               if getattr(model.config, "input_representation", "byte") == "structured"
               else encode_source)
    pending = []
    accepted = 0
    started = time.monotonic()
    next_report = progress_every

    def process_pending() -> None:
        nonlocal next_report
        if not pending:
            return
        sources = [encoder(item["formula"], item["h_nmr"], item["c_nmr"],
                           mask, model.config.max_source) for item, mask in pending]
        if hasattr(model, "beam_search_batch"):
            candidate_batches = model.beam_search_batch(sources, beam_size)
        else:
            candidate_batches = [model.beam_search(source, beam_size)
                                 for source in sources]
        for (item, mask), candidates in zip(pending, candidate_batches):
            ranked = rank_candidates(candidates, item["formula"])
            best = ranked[0]
            if record_predictions:
                predictions.append({"input": {"formula": item["formula"],
                                    "h_nmr": item["h_nmr"] if mask[0] else [],
                                    "c_nmr": item["c_nmr"] if mask[1] else [],
                                    "modality_mask": list(mask)},
                                    "reference_smiles": item["smiles"], "candidates": ranked,
                                    "exact_match": best["canonical_smiles"] == item["smiles"]})
            counts["examples"] += 1
            counts["valid"] += int(best["valid"])
            counts["formula_match"] += int(best["formula_match"])
            counts["exact"] += int(best["canonical_smiles"] == item["smiles"])
        pending.clear()
        if progress_every and rank == 0 and counts["examples"] >= next_report:
            elapsed = time.monotonic() - started
            print(json.dumps({"event": "evaluation_progress", "rank": rank,
                              "examples_on_rank": counts["examples"],
                              "elapsed_seconds": round(elapsed, 1),
                              "examples_per_second": round(
                                  counts["examples"] / max(elapsed, 1e-9), 3)}),
                  file=sys.stderr, flush=True)
            next_report = counts["examples"] + progress_every

    with path.open("r", encoding="utf-8") as stream:
        for line_index, line in enumerate(stream):
            if accepted >= max_examples:
                break
            item = json.loads(line)
            mask = item["modality_mask"]
            if modality == "h":
                mask = [int(bool(mask[0])), 0]
            elif modality == "c":
                mask = [0, int(bool(mask[1]))]
            elif modality == "hc" and mask != [1, 1]:
                mask = [0, 0]
            if not any(mask):
                if line_index % world_size == rank:
                    counts["skipped_missing_modality"] += 1
                continue
            if accepted % world_size == rank:
                pending.append((item, mask))
                if len(pending) == batch_size:
                    process_pending()
            accepted += 1
    process_pending()
    if world_size > 1:
        keys = tuple(counts)
        values = torch.tensor([counts[key] for key in keys], dtype=torch.long,
                              device=next(model.parameters()).device)
        dist.all_reduce(values)
        counts = dict(zip(keys, values.tolist()))
    if not counts["examples"]:
        raise ValueError(f"No examples in {path}")
    return {"modality": modality, **counts,
            **({"predictions": predictions} if record_predictions else {}),
            **{f"{name}_rate": counts[name] / counts["examples"]
                       for name in ("valid", "formula_match", "exact")}}


def save_checkpoint(path: Path, model: SpectrumToSmiles, config: ModelConfig,
                    epoch: int, validation_score: float, stage: str,
                    fingerprint: dict[str, str],
                    alignment_checkpoint: str | None = None) -> None:
    temporary = path.with_suffix(".pt.partial")
    torch.save({"model": model.state_dict(), "config": asdict(config),
                "epoch": epoch, "validation_score": validation_score,
                "training_stage": stage, "data_fingerprint": fingerprint,
                "alignment_checkpoint": alignment_checkpoint,
                "checkpoint_version": CHECKPOINT_VERSION,
                "data_format_version": DATA_FORMAT_VERSION}, temporary)
    temporary.replace(path)


def load_checkpoint(path: Path, device: torch.device) -> SpectrumToSmiles:
    checkpoint = torch.load(path, map_location=device, weights_only=True)
    if (checkpoint.get("checkpoint_version") != CHECKPOINT_VERSION
            or checkpoint.get("training_stage") != "generate"):
        raise ValueError("Inference requires a generation checkpoint initialized from alignment")
    model = SpectrumToSmiles(ModelConfig(**checkpoint["config"]))
    model.load_state_dict(checkpoint["model"])
    return model.to(device).eval()


def load_alignment_checkpoint(path: Path, device: torch.device,
                              fingerprint: dict[str, str],
                              allow_mismatch: bool = False) -> SpectrumToSmiles:
    checkpoint = torch.load(path, map_location=device, weights_only=True)
    if (checkpoint.get("checkpoint_version") != CHECKPOINT_VERSION
            or checkpoint.get("training_stage") != "align"):
        raise ValueError("Generation needs a stage-one alignment checkpoint")
    if checkpoint.get("data_fingerprint") != fingerprint and not allow_mismatch:
        raise ValueError("Alignment checkpoint was trained on different data splits")
    model = SpectrumToSmiles(ModelConfig(**checkpoint["config"]))
    model.load_state_dict(checkpoint["model"])
    return model.to(device)


def align(args) -> None:
    if args.epochs < 1 or args.batch_size < 2 or args.max_val_examples < 2:
        raise ValueError("Alignment needs positive epochs and at least two examples per batch/evaluation")
    if args.max_train_batches is not None and args.max_train_batches < 1:
        raise ValueError("--max-train-batches must be positive")
    if args.log_every < 1:
        raise ValueError("--log-every must be positive")
    if (args.drop_h_prob < 0 or args.drop_c_prob < 0
            or args.drop_h_prob + args.drop_c_prob >= 1):
        raise ValueError("Modality drop probabilities must be nonnegative and sum below 1")
    if args.projection_size < 1 or args.alignment_temperature <= 0:
        raise ValueError("Projection size and alignment temperature must be positive")
    if args.max_source_tokens < 2:
        raise ValueError("--max-source-tokens must be at least 2")
    verification = require_data_format(args.data_dir)
    fingerprint = data_fingerprint(verification)
    device, rank, world_size = setup_distributed(args.device)
    try:
        torch.manual_seed(args.seed)
        config = ModelConfig(hidden_size=args.hidden_size, heads=args.heads,
                             encoder_layers=args.encoder_layers,
                             decoder_layers=args.decoder_layers,
                             feedforward_size=args.feedforward_size,
                             projection_size=args.projection_size,
                             alignment_temperature=args.alignment_temperature,
                             max_source=(args.max_source_tokens
                                         if args.input_representation == "structured" else 512),
                             max_target=300, input_representation=args.input_representation,
                             molecule_tokenizer="mol_bpe", alignment_objective="itm")
        model = SpectrumToSmiles(config).to(device)
        if getattr(args, "init_checkpoint", None):
            init = torch.load(args.init_checkpoint, map_location=device,
                              weights_only=True)
            config = ModelConfig(**init["config"])
            model = SpectrumToSmiles(config).to(device)
            model.load_state_dict(init["model"])
            print(json.dumps({"event": "init_checkpoint_loaded",
                              "checkpoint": str(args.init_checkpoint),
                              "validation_score": init.get("validation_score")}),
                  flush=True)
        if world_size > 1:
            model = DistributedDataParallel(
                model, device_ids=[device.index] if device.type == "cuda" else None,
                find_unused_parameters=True)
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
        collate = make_collate(config, include_formula=False)
        args.run_dir = create_run_dir(
            args.run_dir or Path("runs/align"), device, rank, world_size)
        train_count = json.loads((args.data_dir / "summary.json").read_text())[
            "counts"]["train"]
        full_steps = train_count // (world_size * args.batch_size)
        if full_steps < 1:
            raise ValueError("Training split is too small for this world size and batch size")
        max_batches = min(args.max_train_batches or full_steps, full_steps)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=args.epochs * max_batches, eta_min=0.0)
        if rank == 0:
            log_event(args.run_dir, "run_started", stage="align",
                      data_dir=str(args.data_dir.resolve()),
                      device=str(device), world_size=world_size,
                      torch_version=torch.__version__, epochs=args.epochs,
                      batch_size_per_rank=args.batch_size,
                      effective_batch_size=args.batch_size * world_size,
                      train_examples=train_count,
                      steps_per_epoch=max_batches,
                      input_representation=config.input_representation,
                      molecule_tokenizer=config.molecule_tokenizer,
                      alignment_objective=config.alignment_objective,
                      learning_rate=args.learning_rate,
                      lr_scheduler="cosine_per_step",
                      lr_total_steps=args.epochs * max_batches,
                      max_source_tokens=config.max_source,
                      log_every=args.log_every)
        best_recall = -1.0
        best_loss = float("inf")
        stale_epochs = 0
        history = []
        for epoch in range(1, args.epochs + 1):
            if rank == 0:
                log_event(args.run_dir, "epoch_started", stage="align", epoch=epoch)
            train_loader = DataLoader(
                JsonlExamples(args.data_dir / "train.jsonl", args.shuffle_buffer,
                              args.seed + epoch + rank, args.drop_h_prob,
                              args.drop_c_prob, augment_records=True,
                              rank=rank, world_size=world_size),
                batch_size=args.batch_size, collate_fn=collate, drop_last=True)
            model.train()
            train_loss = run_alignment_loss(model, train_loader, device,
                                            max_batches, optimizer,
                                            scheduler=scheduler,
                                            log_every=args.log_every,
                                            progress=(lambda fields: log_event(
                                                args.run_dir, "train_progress",
                                                stage="align", epoch=epoch, **fields))
                                            if rank == 0 else None,
                                            total_batches=max_batches,
                                            show_tqdm=show_tqdm(args.tqdm, rank),
                                            description=f"align epoch {epoch}")
            if world_size > 1:
                dist.barrier()
            if rank == 0:
                unwrapped = model.module if world_size > 1 else model
                log_event(args.run_dir, "validation_started", stage="align",
                          epoch=epoch, max_examples=args.max_val_examples)
                validation = evaluate_alignment(
                    unwrapped, args.data_dir / "val.jsonl", args.max_val_examples,
                    args.batch_size, device, seed=args.seed)
                log_event(args.run_dir, "validation_completed", stage="align",
                          epoch=epoch, **validation)
                result = {"stage": "align", "epoch": epoch, "train_loss": train_loss,
                          "learning_rate": optimizer.param_groups[0]["lr"],
                          **validation}
                history.append(result)
                recall = validation["spectrum_to_molecule_recall_at_1"]
                save_checkpoint(args.run_dir / "last.pt", unwrapped, config, epoch,
                                recall, "align", fingerprint)
                log_event(args.run_dir, "checkpoint_saved", stage="align",
                          epoch=epoch, path=str(args.run_dir / "last.pt"))
                if recall > best_recall or (recall == best_recall and validation["val_loss"] < best_loss):
                    best_recall, best_loss = recall, validation["val_loss"]
                    save_checkpoint(args.run_dir / "best.pt", unwrapped, config, epoch,
                                    recall, "align", fingerprint)
                    log_event(args.run_dir, "checkpoint_saved", stage="align",
                              epoch=epoch, path=str(args.run_dir / "best.pt"),
                              best_recall_at_1=recall)
                    stale_epochs = 0
                else:
                    stale_epochs += 1
                stop_flag = int(args.early_stop_patience > 0
                                and stale_epochs >= args.early_stop_patience)
                (args.run_dir / "history.json").write_text(
                    json.dumps(history, indent=2) + "\n", encoding="utf-8")
                log_event(args.run_dir, "epoch_completed", **result)
            else:
                stop_flag = 0
            if world_size > 1:
                stop_t = torch.tensor([stop_flag], device=device)
                dist.broadcast(stop_t, src=0)
                stop_flag = int(stop_t.item())
                dist.barrier()
            if stop_flag:
                if rank == 0:
                    log_event(args.run_dir, "early_stopped", stage="align",
                              epoch=epoch, stale_epochs=stale_epochs,
                              best_recall_at_1=best_recall)
                    print(json.dumps({"event": "early_stopped", "epoch": epoch,
                                      "stale_epochs": stale_epochs,
                                      "best_recall_at_1": best_recall}), flush=True)
                break
            if world_size > 1:
                dist.barrier()
        if rank == 0:
            log_event(args.run_dir, "run_completed", stage="align",
                      epochs=args.epochs, best_recall_at_1=best_recall)
    finally:
        if world_size > 1:
            dist.destroy_process_group()


def train(args) -> None:
    """Stage two: train the formula-conditioned generator on one or more GPUs."""
    if args.epochs < 1 or args.batch_size < 2:
        raise ValueError("Generation needs positive epochs and at least two examples per batch")
    if args.alignment_loss_weight <= 0:
        raise ValueError("--alignment-loss-weight must be positive for full-model training")
    if args.log_every < 1:
        raise ValueError("--log-every must be positive")
    if args.max_train_batches is not None and args.max_train_batches < 1:
        raise ValueError("--max-train-batches must be positive")
    if args.max_val_batches is not None and args.max_val_batches < 1:
        raise ValueError("--max-val-batches must be positive")
    if (args.drop_h_prob < 0 or args.drop_c_prob < 0
            or args.drop_h_prob + args.drop_c_prob >= 1):
        raise ValueError("Modality drop probabilities must be nonnegative and sum below 1")
    for split in ("train", "val"):
        if not (args.data_dir / f"{split}.jsonl").is_file():
            raise FileNotFoundError(args.data_dir / f"{split}.jsonl")
    verification = require_data_format(args.data_dir)
    fingerprint = data_fingerprint(verification)
    device, rank, world_size = setup_distributed(args.device)
    try:
        torch.manual_seed(args.seed)
        if getattr(args, "init_generate_checkpoint", None):
            gck = torch.load(args.init_generate_checkpoint, map_location=device,
                             weights_only=True)
            config = ModelConfig(**gck["config"])
            model = SpectrumToSmiles(config).to(device)
            model.load_state_dict(gck["model"])
            print(json.dumps({"event": "generate_checkpoint_loaded",
                              "checkpoint": str(args.init_generate_checkpoint),
                              "validation_score": gck.get("validation_score")}),
                  flush=True)
        else:
            model = load_alignment_checkpoint(args.alignment_checkpoint, device, fingerprint,
                                          allow_mismatch=args.allow_data_mismatch)
        config = model.config
        for parameter in model.parameters():
            parameter.requires_grad_(True)
        if world_size > 1:
            model = DistributedDataParallel(
                model, device_ids=[device.index] if device.type == "cuda" else None)
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
        train_collate = make_collate(config, include_alignment_source=True)
        val_collate = make_collate(config)
        args.run_dir = create_run_dir(args.run_dir or Path("runs/generate"),
                                      device, rank, world_size)
        counts = json.loads((args.data_dir / "summary.json").read_text())["counts"]
        full_train_steps = counts["train"] // (world_size * args.batch_size)
        if full_train_steps < 1:
            raise ValueError("Training split is too small for this world size and batch size")
        train_steps = min(args.max_train_batches or full_train_steps, full_train_steps)
        rank_val_count = (counts["val"] + world_size - 1 - rank) // world_size
        full_val_steps = (rank_val_count + args.batch_size - 1) // args.batch_size
        val_steps = min(args.max_val_batches or full_val_steps, full_val_steps)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=args.epochs * train_steps, eta_min=0.0)
        if rank == 0:
            log_event(args.run_dir, "run_started", stage="generate",
                      data_dir=str(args.data_dir.resolve()), device=str(device),
                      world_size=world_size, torch_version=torch.__version__,
                      epochs=args.epochs, batch_size_per_rank=args.batch_size,
                      effective_batch_size=args.batch_size * world_size,
                      train_examples=counts["train"],
                      validation_examples=counts["val"],
                      train_steps_per_epoch=train_steps,
                      val_steps_per_rank=val_steps,
                      alignment_checkpoint=str(args.alignment_checkpoint.resolve()),
                      input_representation=config.input_representation,
                      molecule_tokenizer=config.molecule_tokenizer,
                      trainable_parameters=sum(parameter.numel()
                                               for parameter in model.parameters()),
                      alignment_loss_weight=args.alignment_loss_weight,
                      learning_rate=args.learning_rate,
                      lr_scheduler="cosine_per_step",
                      lr_total_steps=args.epochs * train_steps,
                      max_source_tokens=config.max_source,
                      log_every=args.log_every)
        best_loss = float("inf")
        history = []
        for epoch in range(1, args.epochs + 1):
            if rank == 0:
                log_event(args.run_dir, "epoch_started", stage="generate", epoch=epoch)
            train_loader = DataLoader(
                JsonlExamples(args.data_dir / "train.jsonl", args.shuffle_buffer,
                              args.seed + epoch + rank, args.drop_h_prob,
                              args.drop_c_prob, augment_records=True,
                              rank=rank, world_size=world_size),
                batch_size=args.batch_size, collate_fn=train_collate,
                drop_last=True)
            model.train()
            train_metrics = {}
            train_loss = run_loss(
                model, train_loader, device, train_steps, optimizer,
                scheduler=scheduler, log_every=args.log_every,
                progress=(lambda fields: log_event(
                    args.run_dir, "train_progress", stage="generate",
                    epoch=epoch, **fields)) if rank == 0 else None,
                total_batches=train_steps,
                show_tqdm=show_tqdm(args.tqdm, rank),
                description=f"generate train epoch {epoch}",
                aggregate_progress=world_size > 1,
                alignment_weight=args.alignment_loss_weight,
                auxiliary_metrics=train_metrics)
            val_loader = DataLoader(
                JsonlExamples(args.data_dir / "val.jsonl",
                              rank=rank, world_size=world_size),
                batch_size=args.batch_size, collate_fn=val_collate)
            unwrapped = model.module if world_size > 1 else model
            unwrapped.eval()
            if rank == 0:
                log_event(args.run_dir, "validation_started", stage="generate",
                          epoch=epoch)
            with torch.no_grad():
                val_loss = run_loss(
                    unwrapped, val_loader, device, val_steps,
                    log_every=args.log_every,
                    progress=(lambda fields: log_event(
                        args.run_dir, "validation_progress", stage="generate",
                        epoch=epoch, progress_scope="rank0", **fields))
                    if rank == 0 else None,
                    total_batches=val_steps,
                    show_tqdm=show_tqdm(args.tqdm, rank),
                    description=f"generate val epoch {epoch}")
            if rank == 0:
                log_event(args.run_dir, "validation_completed", stage="generate",
                          epoch=epoch, val_loss=val_loss)
                result = {"epoch": epoch, "train_loss": train_loss,
                          "val_loss": val_loss,
                          "learning_rate": optimizer.param_groups[0]["lr"],
                          **train_metrics}
                if args.generate_examples:
                    log_event(args.run_dir, "sample_generation_started", stage="generate",
                              epoch=epoch, max_examples=args.generate_examples)
                    result["generation"] = evaluate_generation(
                        unwrapped, args.data_dir / "val.jsonl",
                        args.generate_examples, args.beam_size)
                    log_event(args.run_dir, "sample_generation_completed",
                              stage="generate", epoch=epoch, **result["generation"])
                history.append(result)
                save_checkpoint(args.run_dir / "last.pt", unwrapped, config, epoch,
                                val_loss, "generate", fingerprint,
                                str(args.alignment_checkpoint.resolve()))
                log_event(args.run_dir, "checkpoint_saved", stage="generate",
                          epoch=epoch, path=str(args.run_dir / "last.pt"))
                if val_loss < best_loss:
                    best_loss = val_loss
                    save_checkpoint(args.run_dir / "best.pt", unwrapped, config, epoch,
                                    val_loss, "generate", fingerprint,
                                    str(args.alignment_checkpoint.resolve()))
                    log_event(args.run_dir, "checkpoint_saved", stage="generate",
                              epoch=epoch, path=str(args.run_dir / "best.pt"),
                              best_val_loss=val_loss)
                (args.run_dir / "history.json").write_text(
                    json.dumps(history, indent=2) + "\n", encoding="utf-8")
                log_event(args.run_dir, "epoch_completed", stage="generate", **result)
            if world_size > 1:
                dist.barrier()
        if rank == 0:
            log_event(args.run_dir, "run_completed", stage="generate",
                      epochs=args.epochs, best_val_loss=best_loss)
    finally:
        if world_size > 1:
            dist.destroy_process_group()


def evaluate(args) -> None:
    require_data_format(args.data_dir)
    device, rank, world_size = setup_distributed(args.device)
    try:
        model = load_checkpoint(args.checkpoint, device)
        started = time.monotonic()
        result = evaluate_generation(
            model, args.data_dir / f"{args.split}.jsonl", args.max_examples,
            args.beam_size, args.modality, batch_size=args.batch_size,
            rank=rank, world_size=world_size, progress_every=args.log_every)
        if rank == 0:
            print(json.dumps({"split": args.split, "world_size": world_size,
                              "batch_size_per_rank": args.batch_size,
                              "elapsed_seconds": round(time.monotonic() - started, 1),
                              **result}, indent=2))
    finally:
        if world_size > 1:
            dist.destroy_process_group()


def predict(args) -> None:
    device = choose_device(args.device)
    model = load_checkpoint(args.checkpoint, device)
    h_texts = list(args.h1 or [])
    c_texts = list(args.c13 or [])
    if args.h1_file:
        h_texts.append(Path(args.h1_file).read_text(encoding="utf-8"))
    if args.c13_file:
        c_texts.append(Path(args.c13_file).read_text(encoding="utf-8"))
    h_records = [{"type": "1H NMR", "chemical_shift": clean_text(value)}
                 for value in h_texts if clean_text(value)]
    c_records = [{"type": "13C NMR", "chemical_shift": clean_text(value)}
                 for value in c_texts if clean_text(value)]
    mask = [int(bool(h_records)), int(bool(c_records))]
    encoder = (encode_structured_source
               if model.config.input_representation == "structured" else encode_source)
    source = encoder(args.formula, h_records, c_records, mask,
                     model.config.max_source)
    results = rank_candidates(model.beam_search(source, args.beam_size), args.formula)
    matching = [row for row in results if row["formula_match"]]
    print(json.dumps({"formula": args.formula, "modality_mask": mask,
                      "best": matching[0] if matching else None,
                      "candidates": results}, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    def add_training_options(command):
        command.add_argument("--data-dir", type=Path, required=True)
        command.add_argument("--run-dir", type=Path,
                             help="Run root; a UUID subdirectory is created automatically "
                                  "(default: runs/align or runs/generate)")
        command.add_argument("--epochs", type=int, default=10)
        command.add_argument("--batch-size", type=int, default=32)
        command.add_argument("--learning-rate", type=float, default=1e-4)
        command.add_argument("--max-train-batches", type=int)
        command.add_argument("--shuffle-buffer", type=int, default=4096)
        command.add_argument("--drop-h-prob", type=float, default=0.2)
        command.add_argument("--drop-c-prob", type=float, default=0.2)
        command.add_argument("--seed", type=int, default=2026)
        command.add_argument("--device", default="auto")
        command.add_argument("--log-every", type=int, default=100,
                             help="Write progress every N batches (also logs batch 1)")
        command.add_argument("--tqdm", choices=("auto", "always", "never"),
                             default="auto", help="Interactive progress bar mode")

    align_cmd = commands.add_parser("align", help="Stage 1: align NMR and molecule embeddings")
    add_training_options(align_cmd)
    align_cmd.add_argument("--max-val-examples", type=int, default=1024)
    align_cmd.add_argument("--hidden-size", type=int, default=512)
    align_cmd.add_argument("--heads", type=int, default=8)
    align_cmd.add_argument("--encoder-layers", type=int, default=6)
    align_cmd.add_argument("--decoder-layers", type=int, default=6)
    align_cmd.add_argument("--feedforward-size", type=int, default=2048)
    align_cmd.add_argument("--projection-size", type=int, default=256)
    align_cmd.add_argument("--alignment-temperature", type=float, default=0.07)
    align_cmd.add_argument("--input-representation", choices=("structured", "byte"),
                           default="structured", help="NMR input encoding for a new alignment run")
    align_cmd.add_argument("--max-source-tokens", type=int, default=128,
                           help="Maximum structured formula and NMR tokens")
    align_cmd.add_argument("--init-checkpoint", type=Path,
                           help="Continue training from an alignment checkpoint; "
                                "model config is taken from the checkpoint")
    align_cmd.add_argument("--early-stop-patience", type=int, default=0,
                           help="Stop after N consecutive epochs without val R@1 "
                                "improvement (0 disables early stopping)")

    generate_cmd = commands.add_parser(
        "generate", aliases=["train"],
        help="Stage 2: initialize from alignment and train SMILES generation")
    add_training_options(generate_cmd)
    generate_cmd.add_argument("--alignment-checkpoint", type=Path, required=True)
    generate_cmd.add_argument("--init-generate-checkpoint", type=Path,
                              help="Continue from a full generate-stage checkpoint "
                                   "(overrides --alignment-checkpoint init)")
    generate_cmd.add_argument("--alignment-loss-weight", type=float, default=0.1,
                              help="Positive weight for continued alignment/ITM training "
                                   "of all model parameters (default: 0.1)")
    generate_cmd.add_argument("--allow-data-mismatch", action="store_true",
                              help="Skip the alignment-checkpoint data fingerprint check "
                                   "(use when warming from a checkpoint trained on other splits)")
    generate_cmd.add_argument("--max-val-batches", type=int)
    generate_cmd.add_argument("--generate-examples", type=int, default=0)
    generate_cmd.add_argument("--beam-size", type=int, default=5)
    eval_cmd = commands.add_parser("evaluate")
    eval_cmd.add_argument("--data-dir", type=Path, required=True)
    eval_cmd.add_argument("--split", choices=("val", "test"), default="test")
    eval_cmd.add_argument("--checkpoint", type=Path, required=True)
    eval_cmd.add_argument("--max-examples", type=int, default=1000)
    eval_cmd.add_argument("--beam-size", type=int, default=5)
    eval_cmd.add_argument("--batch-size", type=int, default=16,
                          help="Spectra decoded together per GPU (default: 16)")
    eval_cmd.add_argument("--log-every", type=int, default=100,
                          help="Report rank-0 progress to stderr every N examples")
    eval_cmd.add_argument("--modality", choices=("available", "h", "c", "hc"),
                          default="available")
    eval_cmd.add_argument("--device", default="auto")
    predict_cmd = commands.add_parser("predict")
    predict_cmd.add_argument("--checkpoint", type=Path, required=True)
    predict_cmd.add_argument("--formula", required=True)
    predict_cmd.add_argument("--h1", action="append", help="Repeat for multiple ¹H records")
    predict_cmd.add_argument("--c13", action="append", help="Repeat for multiple ¹³C records")
    predict_cmd.add_argument("--h1-file")
    predict_cmd.add_argument("--c13-file")
    predict_cmd.add_argument("--beam-size", type=int, default=10)
    predict_cmd.add_argument("--device", default="auto")
    args = parser.parse_args()
    {"align": align, "generate": train, "train": train,
     "evaluate": evaluate, "predict": predict}[args.command](args)


if __name__ == "__main__":
    main()

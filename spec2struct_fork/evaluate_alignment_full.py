"""Exact retrieval over every molecule and spectrum in a prepared split."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from .model import SpectrumToSmiles
from .train import (JsonlExamples, choose_device, data_fingerprint,
                    load_alignment_checkpoint, make_collate, require_data_format)


def report(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


@torch.inference_mode()
def evaluate_full_alignment(model: SpectrumToSmiles, path: Path, count: int,
                            encode_batch_size: int, query_batch_size: int,
                            device: torch.device, log_every: int = 10000,
                            formula_filter: bool = False) -> dict:
    """Encode the full split, then rank each query against all opposite-modality rows.

    Embeddings occupy O(ND) memory and similarity blocks occupy O(BN) memory;
    the complete N-by-N matrix is never materialized.
    """
    if count < 2 or encode_batch_size < 1 or query_batch_size < 1 or log_every < 1:
        raise ValueError("Count and batch sizes must be positive; count must be at least two")
    model.eval()
    started = time.monotonic()
    dimension = model.config.projection_size
    spectral = torch.empty((count, dimension), device=device, dtype=torch.float32)
    molecular = torch.empty_like(spectral)
    formula_ids = (torch.empty(count, device=device, dtype=torch.int32)
                   if formula_filter else None)
    formula_to_id: dict[str, int] = {}
    formula_counts: list[int] = []
    loader = DataLoader(JsonlExamples(path), batch_size=encode_batch_size,
                        collate_fn=make_collate(model.config, include_formula=False))
    encoded = 0
    next_report = log_every
    for source, molecule, examples in loader:
        batch_count = len(source)
        if encoded + batch_count > count:
            raise ValueError(f"Split contains more than the declared {count} examples")
        spectrum_embedding, molecule_embedding = model.alignment_embeddings(
            source.to(device), molecule.to(device))
        spectral[encoded:encoded + batch_count].copy_(spectrum_embedding)
        molecular[encoded:encoded + batch_count].copy_(molecule_embedding)
        if formula_filter:
            ids = []
            for example in examples:
                formula = example["formula"]
                if formula not in formula_to_id:
                    formula_to_id[formula] = len(formula_counts)
                    formula_counts.append(0)
                formula_id = formula_to_id[formula]
                formula_counts[formula_id] += 1
                ids.append(formula_id)
            formula_ids[encoded:encoded + batch_count] = torch.tensor(
                ids, device=device, dtype=torch.int32)
        encoded += batch_count
        if encoded >= next_report or encoded == count:
            report("encoding_progress", encoded=encoded, total=count,
                   elapsed_seconds=round(time.monotonic() - started, 1))
            next_report = encoded + log_every
    if encoded != count:
        raise ValueError(f"Split contains {encoded} examples; expected {count}")

    scale = (float(model.logit_scale.exp())
             if model.config.alignment_objective == "itm"
             else 1 / model.config.alignment_temperature)
    results = {}
    for direction, queries, candidates in (
            ("spectrum_to_molecule", spectral, molecular),
            ("molecule_to_spectrum", molecular, spectral)):
        correct = 0
        loss_sum = 0.0
        filtered_correct = 0
        filtered_loss_sum = 0.0
        candidate_matrix = candidates.T.contiguous()
        for start in range(0, count, query_batch_size):
            end = min(start + query_batch_size, count)
            scores = queries[start:end] @ candidate_matrix
            scores.mul_(scale)
            labels = torch.arange(start, end, device=device)
            rows = torch.arange(end - start, device=device)
            correct += int((scores.argmax(dim=1) == labels).sum())
            loss_sum += float((torch.logsumexp(scores, dim=1)
                               - scores[rows, labels]).sum())
            if formula_filter:
                allowed = formula_ids[start:end, None].eq(formula_ids[None, :])
                scores.masked_fill_(~allowed, -torch.inf)
                filtered_correct += int((scores.argmax(dim=1) == labels).sum())
                filtered_loss_sum += float((torch.logsumexp(scores, dim=1)
                                            - scores[rows, labels]).sum())
            if end == count or (end // query_batch_size) % 50 == 0:
                report("retrieval_progress", direction=direction,
                       queries_scored=end, candidate_pool=count,
                       elapsed_seconds=round(time.monotonic() - started, 1))
        results[f"{direction}_recall_at_1"] = correct / count
        results[f"{direction}_loss"] = loss_sum / count
        if formula_filter:
            results[f"formula_filtered_{direction}_recall_at_1"] = filtered_correct / count
            results[f"formula_filtered_{direction}_loss"] = filtered_loss_sum / count
            results[f"formula_filtered_{direction}_gain_percentage_points"] = (
                100 * (filtered_correct - correct) / count)
        del candidate_matrix
    result = {"examples": count, "candidate_pool": count,
              **results,
              "retrieval_loss": (results["spectrum_to_molecule_loss"]
                                 + results["molecule_to_spectrum_loss"]) / 2,
              "elapsed_seconds": round(time.monotonic() - started, 1)}
    if formula_filter:
        sorted_counts = sorted(formula_counts)
        cumulative = 0
        median_pool = 0
        for size in sorted_counts:
            cumulative += size
            if cumulative >= (count + 1) // 2:
                median_pool = size
                break
        result.update(formula_filter=True, distinct_formulas=len(formula_counts),
                      formula_candidate_pool_mean=sum(size * size for size in formula_counts) / count,
                      formula_candidate_pool_median=median_pool,
                      formula_candidate_pool_max=max(formula_counts),
                      formula_filtered_retrieval_loss=(
                          results["formula_filtered_spectrum_to_molecule_loss"]
                          + results["formula_filtered_molecule_to_spectrum_loss"]) / 2)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--split", choices=("val", "test"), default="test")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--encode-batch-size", type=int, default=128)
    parser.add_argument("--query-batch-size", type=int, default=256)
    parser.add_argument("--log-every", type=int, default=10000)
    parser.add_argument("--formula-filter", action="store_true",
                        help="Also report retrieval after exact query-formula filtering")
    parser.add_argument("--output", type=Path,
                        help="Save metrics as JSON; refuse to replace an existing file")
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    verification = require_data_format(args.data_dir)
    summary = json.loads((args.data_dir / "summary.json").read_text(encoding="utf-8"))
    count = summary["counts"][args.split]
    device = choose_device(args.device)
    model = load_alignment_checkpoint(
        args.checkpoint, device, data_fingerprint(verification)).eval()
    report("evaluation_started", split=args.split, examples=count,
           candidate_pool=count, device=str(device),
           formula_filter=args.formula_filter,
           checkpoint=str(args.checkpoint.resolve()))
    result = {"split": args.split, "checkpoint": str(args.checkpoint.resolve()),
              **evaluate_full_alignment(model, args.data_dir / f"{args.split}.jsonl",
                                        count, args.encode_batch_size,
                                        args.query_batch_size, device, args.log_every,
                                        args.formula_filter)}
    report("evaluation_completed", **result)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")


if __name__ == "__main__":
    main()

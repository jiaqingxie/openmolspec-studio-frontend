"""Score representable generated candidates while preserving every valid beam."""

import torch


def score_generated_candidates(
    rank_model, rank_tokenizer, data, candidates, batch_size
):
    from benchmarks.models.vib2mol.evaluate_multimodal import rerank_candidates

    records = []
    eligible = []
    for index, smiles in enumerate(candidates):
        tokens = rank_tokenizer.encode(
            smiles, add_special_tokens=True, truncation=False
        )
        if len(tokens) > rank_tokenizer.model_max_length:
            status = "over_token_limit"
        elif rank_tokenizer.unk_token_id in tokens:
            status = "unknown_token"
        else:
            status = "scored"
            eligible.append(index)
        records.append(
            dict(
                smiles=smiles,
                beam_rank=index + 1,
                itm_rank=None,
                score=None,
                itm_status=status,
            )
        )
    if eligible:
        with torch.inference_mode():
            order, ranked_scores = rerank_candidates(
                rank_model,
                rank_tokenizer,
                data,
                [candidates[i] for i in eligible],
                batch_size,
            )
        for rank, (index, probability) in enumerate(zip(order, ranked_scores), 1):
            records[eligible[index]].update(itm_rank=rank, score=probability)
    return records


def itm_order(records):
    return sorted(
        records,
        key=lambda row: (row["itm_rank"] is None, row["itm_rank"] or row["beam_rank"]),
    )

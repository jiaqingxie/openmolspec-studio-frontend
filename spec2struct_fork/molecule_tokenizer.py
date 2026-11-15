"""Vib2Mol molecular BPE with the extra stereo symbols in patent SMILES."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


TOKENIZER_DIR = Path(__file__).parent / "assets" / "mol_tokenizer"
# The reference vocabulary targets non-isomeric Kekulé SMILES. Retain the
# dataset's isomeric targets by adding only the symbols absent from that vocab.
PATENT_SMILES_SYMBOLS = ("@", "/", "\\", ":", "~", "$")


@lru_cache(maxsize=1)
def molecule_tokenizer():
    from transformers import RobertaTokenizerFast

    tokenizer = RobertaTokenizerFast.from_pretrained(
        str(TOKENIZER_DIR), local_files_only=True,
        clean_up_tokenization_spaces=False)
    tokenizer.add_tokens(list(PATENT_SMILES_SYMBOLS))
    return tokenizer


def vocabulary_size() -> int:
    return len(molecule_tokenizer())


def _to_model_id(token_id: int) -> int:
    """Keep the repository's existing PAD=0 and BOS=1 tensor convention."""
    return 1 if token_id == 0 else 0 if token_id == 1 else token_id


def _to_tokenizer_id(token_id: int) -> int:
    return _to_model_id(token_id)


def encode_molecules(smiles: list[str], limit: int) -> list[list[int]]:
    tokenizer = molecule_tokenizer()
    batches = tokenizer(smiles, add_special_tokens=True, padding=False,
                        truncation=False)["input_ids"]
    encoded = []
    for text, token_ids in zip(smiles, batches):
        if tokenizer.unk_token_id in token_ids:
            raise ValueError(f"SMILES contains symbols outside the molecular vocabulary: {text}")
        if len(token_ids) > limit:
            raise ValueError(f"SMILES exceeds target capacity of {limit} BPE tokens")
        encoded.append([_to_model_id(token_id) for token_id in token_ids])
    return encoded


def encode_molecule(smiles: str, limit: int) -> list[int]:
    return encode_molecules([smiles], limit)[0]


def decode_molecule(token_ids: list[int]) -> str:
    tokenizer = molecule_tokenizer()
    return tokenizer.decode([_to_tokenizer_id(token_id) for token_id in token_ids],
                            skip_special_tokens=True,
                            clean_up_tokenization_spaces=False).replace(" ", "")


def allowed_molecule_ids() -> tuple[int, ...]:
    tokenizer = molecule_tokenizer()
    blocked = {tokenizer.pad_token_id, tokenizer.bos_token_id,
               tokenizer.eos_token_id, tokenizer.unk_token_id,
               tokenizer.mask_token_id}
    return tuple(_to_model_id(token_id) for token_id in range(len(tokenizer))
                 if token_id not in blocked)

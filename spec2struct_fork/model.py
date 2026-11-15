"""NMR/formula to SMILES Transformer with structured and legacy byte inputs."""

from __future__ import annotations

from dataclasses import dataclass
import math

import torch
import torch.distributed as dist
from torch import nn
from torch.nn import functional as F
from torch.distributed.nn.functional import all_gather

from .data import SMILES_BYTES
from .molecule_tokenizer import (allowed_molecule_ids, decode_molecule,
                                 encode_molecule, vocabulary_size)
from .structured import (C_KIND, CLS_KIND, ELEMENT, ELEMENT_COUNT, ELEMENTS,
                         FORMULA_KIND, FREQUENCY, FREQUENCY_PRESENT, H_KIND,
                         INTEGRATION, INTEGRATION_PRESENT, J1, J3, J_COUNT,
                         KIND, MULTIPLICITIES, MULTIPLICITY, SHIFT,
                         SHIFT_PRESENT, SOLVENT, SOLVENTS, SUBTYPE, WIDTH)


PAD, BOS, EOS = 0, 1, 2
FORMULA_TAG, H_TAG, C_TAG, VOCAB_SIZE = 259, 260, 261, 262


def encode_source(formula: str, h_records: list[dict], c_records: list[dict],
                  modality_mask: list[int], limit: int,
                  include_formula: bool = True) -> list[int]:
    """Apply the H/C availability mask before Transformer attention."""
    if len(modality_mask) != 2 or any(value not in (0, 1) for value in modality_mask):
        raise ValueError("modality_mask must be [has_h, has_c]")
    if not any(modality_mask):
        raise ValueError("At least one NMR modality must be visible")
    if (modality_mask[0] and not h_records) or (modality_mask[1] and not c_records):
        raise ValueError("A visible NMR modality has no records")
    formula_bytes = formula.encode("utf-8")[:64] if include_formula else b""
    if include_formula and not formula_bytes:
        raise ValueError("Molecular formula is required")
    tokens = [FORMULA_TAG] + [byte + 3 for byte in formula_bytes]
    segments = []
    for visible, tag, records in zip(modality_mask, (H_TAG, C_TAG),
                                     (h_records, c_records)):
        if visible:
            raw = " | ".join(
                f"{item.get('type', '')}: {item.get('chemical_shift', '')}"
                for item in records).encode("utf-8")
            segments.append((tag, raw))
    budget = limit - len(tokens) - len(segments) - 1
    if budget < 1:
        raise ValueError("Source capacity is too small for formula and NMR tags")
    quotas = [min(len(raw), budget // len(segments)) for _, raw in segments]
    remaining = budget - sum(quotas)
    for index, (_, raw) in enumerate(segments):
        extra = min(len(raw) - quotas[index], remaining)
        quotas[index] += extra
        remaining -= extra
    for (tag, raw), quota in zip(segments, quotas):
        tokens.append(tag)
        tokens.extend(byte + 3 for byte in raw[:quota])
    return tokens + [EOS]


def encode_target(smiles: str, limit: int, tokenizer: str = "byte") -> list[int]:
    if tokenizer == "mol_bpe":
        return encode_molecule(smiles, limit)
    if tokenizer != "byte":
        raise ValueError(f"Unknown molecule tokenizer: {tokenizer}")
    data = smiles.encode("utf-8")
    if len(data) > limit - 2:
        raise ValueError(f"SMILES exceeds target capacity of {limit - 2} bytes")
    return [BOS] + [byte + 3 for byte in data] + [EOS]


def decode_target(tokens: list[int], tokenizer: str = "byte") -> str:
    if tokenizer == "mol_bpe":
        return decode_molecule(tokens)
    if tokenizer != "byte":
        raise ValueError(f"Unknown molecule tokenizer: {tokenizer}")
    data = bytes(token - 3 for token in tokens if token >= 3)
    return data.decode("utf-8", errors="replace")


@dataclass
class ModelConfig:
    hidden_size: int = 512
    heads: int = 8
    encoder_layers: int = 6
    decoder_layers: int = 6
    feedforward_size: int = 2048
    dropout: float = 0.1
    max_source: int = 512
    max_target: int = 162
    projection_size: int = 256
    alignment_temperature: float = 0.07
    input_representation: str = "byte"
    molecule_tokenizer: str = "byte"
    alignment_objective: str = "infonce"


@dataclass
class DecoderKVCache:
    """Per-call decoder state; no tensors are stored in the checkpoint."""

    memory_keys: list[torch.Tensor]
    memory_values: list[torch.Tensor]
    source_pad: torch.Tensor
    self_keys: list[torch.Tensor | None]
    self_values: list[torch.Tensor | None]
    target_pad: torch.Tensor | None = None
    position: int = 0

    def reorder(self, indices: torch.Tensor) -> None:
        """Select surviving parent beams, including duplicate parents."""
        self.self_keys = [key.index_select(0, indices) if key is not None else None
                          for key in self.self_keys]
        self.self_values = [value.index_select(0, indices) if value is not None else None
                            for value in self.self_values]
        if self.target_pad is not None:
            self.target_pad = self.target_pad.index_select(0, indices)


class StructuredSourceEmbedding(nn.Module):
    """Sum separate physical and categorical embeddings for each NMR peak."""

    def __init__(self, hidden_size: int):
        super().__init__()
        self.kind = nn.Embedding(5, hidden_size, padding_idx=0)
        self.element = nn.Embedding(len(ELEMENTS) + 1, hidden_size)
        self.element_count = nn.Linear(1, hidden_size)
        self.shift = nn.Sequential(nn.Linear(3, hidden_size), nn.SiLU(),
                                   nn.Linear(hidden_size, hidden_size))
        self.multiplicity = nn.Embedding(len(MULTIPLICITIES), hidden_size)
        self.integration = nn.Linear(2, hidden_size)
        self.coupling = nn.Linear(4, hidden_size)
        self.frequency = nn.Linear(2, hidden_size)
        self.subtype = nn.Embedding(2, hidden_size)
        self.solvent = nn.Embedding(len(SOLVENTS), hidden_size)
        self.norm = nn.LayerNorm(hidden_size)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        kind = features[..., KIND].long()
        peak = ((kind == H_KIND) | (kind == C_KIND)).unsqueeze(-1)
        formula = (kind == FORMULA_KIND).unsqueeze(-1)
        shift_scale = torch.where(kind == H_KIND, 12.0, 220.0)
        shift_input = torch.stack((features[..., SHIFT] / shift_scale,
                                   features[..., WIDTH] / shift_scale,
                                   features[..., SHIFT_PRESENT]), dim=-1)
        integration_input = torch.stack((torch.log1p(features[..., INTEGRATION].clamp_min(0)) / 5,
                                          features[..., INTEGRATION_PRESENT]), dim=-1)
        coupling_input = torch.cat((torch.log1p(features[..., J1:J3 + 1].clamp_min(0)) / 5,
                                    features[..., J_COUNT:J_COUNT + 1] / 3), dim=-1)
        frequency_input = torch.stack((features[..., FREQUENCY] / 1000,
                                       features[..., FREQUENCY_PRESENT]), dim=-1)
        peak_embedding = (self.shift(shift_input)
                          + self.multiplicity(features[..., MULTIPLICITY].long())
                          + self.integration(integration_input)
                          + self.coupling(coupling_input)
                          + self.frequency(frequency_input)
                          + self.subtype(features[..., SUBTYPE].long())
                          + self.solvent(features[..., SOLVENT].long()))
        formula_embedding = (self.element(features[..., ELEMENT].long())
                             + self.element_count(
                                 torch.log1p(features[..., ELEMENT_COUNT:ELEMENT_COUNT + 1].clamp_min(0)) / 5))
        return self.norm(self.kind(kind) + peak * peak_embedding + formula * formula_embedding)


class SpectrumToSmiles(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        if config.molecule_tokenizer not in ("byte", "mol_bpe"):
            raise ValueError(f"Unknown molecule tokenizer: {config.molecule_tokenizer}")
        if config.alignment_objective not in ("infonce", "itm"):
            raise ValueError(f"Unknown alignment objective: {config.alignment_objective}")
        target_vocab_size = (vocabulary_size() if config.molecule_tokenizer == "mol_bpe"
                             else VOCAB_SIZE)
        if config.input_representation == "byte":
            self.source_embedding = nn.Embedding(VOCAB_SIZE, config.hidden_size, padding_idx=PAD)
        elif config.input_representation == "structured":
            self.structured_embedding = StructuredSourceEmbedding(config.hidden_size)
        else:
            raise ValueError(f"Unknown input representation: {config.input_representation}")
        self.target_embedding = nn.Embedding(target_vocab_size, config.hidden_size, padding_idx=PAD)
        self.source_position = nn.Embedding(config.max_source, config.hidden_size)
        self.target_position = nn.Embedding(config.max_target, config.hidden_size)
        self.transformer = nn.Transformer(
            d_model=config.hidden_size, nhead=config.heads,
            num_encoder_layers=config.encoder_layers,
            num_decoder_layers=config.decoder_layers,
            dim_feedforward=config.feedforward_size, dropout=config.dropout,
            batch_first=True,
        )
        molecular_layer = nn.TransformerEncoderLayer(
            d_model=config.hidden_size, nhead=config.heads,
            dim_feedforward=config.feedforward_size, dropout=config.dropout,
            batch_first=True,
        )
        self.molecular_encoder = nn.TransformerEncoder(
            molecular_layer, num_layers=config.encoder_layers,
            enable_nested_tensor=False,
        )
        self.spectrum_projection = nn.Linear(config.hidden_size, config.projection_size)
        self.molecule_projection = nn.Linear(config.hidden_size, config.projection_size)
        self.output = nn.Linear(config.hidden_size, target_vocab_size)
        if config.alignment_objective == "itm":
            self.molecule_cls = nn.Parameter(torch.randn(1, 1, config.hidden_size) * 0.02)
            matching_layer = nn.TransformerDecoderLayer(
                d_model=config.hidden_size, nhead=config.heads,
                dim_feedforward=config.feedforward_size, dropout=config.dropout,
                batch_first=True)
            self.matching_encoder = nn.TransformerDecoder(
                matching_layer, num_layers=config.encoder_layers)
            self.matching_head = nn.Linear(config.hidden_size, 2)
            self.logit_scale = nn.Parameter(
                torch.tensor(math.log(1 / config.alignment_temperature)))

    def _embed(self, tokens: torch.Tensor, embedding: nn.Embedding,
               position: nn.Embedding) -> torch.Tensor:
        steps = torch.arange(tokens.shape[1], device=tokens.device)
        return embedding(tokens) + position(steps)[None, :, :]

    def encode(self, source: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if self.config.input_representation == "structured":
            source_pad = source[..., KIND].eq(0)
            steps = torch.arange(source.shape[1], device=source.device)
            embedded = self.structured_embedding(source) + self.source_position(steps)[None, :, :]
        else:
            source_pad = source.eq(PAD)
            embedded = self._embed(source, self.source_embedding, self.source_position)
        memory = self.transformer.encoder(
            embedded,
            src_key_padding_mask=source_pad,
        )
        return memory, source_pad

    def decode(self, target: torch.Tensor, memory: torch.Tensor,
               source_pad: torch.Tensor) -> torch.Tensor:
        length = target.shape[1]
        causal = torch.triu(torch.ones(length, length, dtype=torch.bool,
                                       device=target.device), diagonal=1)
        hidden = self.transformer.decoder(
            self._embed(target, self.target_embedding, self.target_position),
            memory, tgt_mask=causal,
            tgt_key_padding_mask=target.eq(PAD),
            memory_key_padding_mask=source_pad,
        )
        return self.output(hidden)

    @staticmethod
    def _attention_heads(value: torch.Tensor, heads: int) -> torch.Tensor:
        batch, length, width = value.shape
        return value.view(batch, length, heads, width // heads).transpose(1, 2)

    @torch.no_grad()
    def init_decoder_cache(self, memory: torch.Tensor,
                           source_pad: torch.Tensor) -> DecoderKVCache:
        """Project encoder K/V once per layer and spectrum, before beam expansion."""
        if self.training:
            raise RuntimeError("KV cache is available only in evaluation mode")
        keys, values = [], []
        for layer in self.transformer.decoder.layers:
            attention = layer.multihead_attn
            width = attention.embed_dim
            bias = attention.in_proj_bias
            key = F.linear(memory, attention.in_proj_weight[width:2 * width],
                           None if bias is None else bias[width:2 * width])
            value = F.linear(memory, attention.in_proj_weight[2 * width:],
                             None if bias is None else bias[2 * width:])
            keys.append(self._attention_heads(key, attention.num_heads))
            values.append(self._attention_heads(value, attention.num_heads))
        return DecoderKVCache(keys, values, source_pad,
                              [None] * len(keys), [None] * len(keys))

    @torch.no_grad()
    def decode_step(self, token: torch.Tensor, cache: DecoderKVCache,
                    source_indices: torch.Tensor) -> torch.Tensor:
        """Decode just the newest token using the existing Transformer weights."""
        if self.training:
            raise RuntimeError("KV cache is available only in evaluation mode")
        if token.ndim != 2 or token.shape[1] != 1:
            raise ValueError("decode_step expects one token per active beam")
        if cache.position >= self.config.max_target:
            raise ValueError("Decoder position exceeds target capacity")
        padding = token.eq(PAD)
        cache.target_pad = (padding if cache.target_pad is None
                            else torch.cat((cache.target_pad, padding), dim=1))
        self_allowed = ~cache.target_pad[:, None, None, :]
        memory_allowed = ~cache.source_pad.index_select(0, source_indices)[:, None, None, :]
        position = torch.tensor([cache.position], device=token.device)
        hidden = self.target_embedding(token) + self.target_position(position)[None, :, :]

        def attend(query, key, value, attention, allowed):
            # All stored self keys precede or equal this single query: no causal
            # mask is needed. SDPA boolean masks use True for allowed positions.
            result = F.scaled_dot_product_attention(
                query, key, value, attn_mask=allowed, dropout_p=0.0)
            result = result.transpose(1, 2).contiguous().view(
                token.shape[0], 1, attention.embed_dim)
            return attention.out_proj(result)

        for index, layer in enumerate(self.transformer.decoder.layers):
            residual = hidden
            normalized = layer.norm1(hidden) if layer.norm_first else hidden
            attention = layer.self_attn
            query, key, value = F.linear(
                normalized, attention.in_proj_weight, attention.in_proj_bias).chunk(3, dim=-1)
            query, key, value = [self._attention_heads(part, attention.num_heads)
                                 for part in (query, key, value)]
            if cache.self_keys[index] is not None:
                key = torch.cat((cache.self_keys[index], key), dim=2)
                value = torch.cat((cache.self_values[index], value), dim=2)
            cache.self_keys[index], cache.self_values[index] = key, value
            hidden = residual + layer.dropout1(attend(
                query, key, value, attention, self_allowed))
            if not layer.norm_first:
                hidden = layer.norm1(hidden)

            residual = hidden
            normalized = layer.norm2(hidden) if layer.norm_first else hidden
            attention = layer.multihead_attn
            width = attention.embed_dim
            query = F.linear(normalized, attention.in_proj_weight[:width],
                             None if attention.in_proj_bias is None
                             else attention.in_proj_bias[:width])
            query = self._attention_heads(query, attention.num_heads)
            hidden = residual + layer.dropout2(attend(
                query, cache.memory_keys[index].index_select(0, source_indices),
                cache.memory_values[index].index_select(0, source_indices),
                attention, memory_allowed))
            if not layer.norm_first:
                hidden = layer.norm2(hidden)

            residual = hidden
            normalized = layer.norm3(hidden) if layer.norm_first else hidden
            hidden = residual + layer.dropout3(layer.linear2(
                layer.dropout(layer.activation(layer.linear1(normalized)))))
            if not layer.norm_first:
                hidden = layer.norm3(hidden)
        if self.transformer.decoder.norm is not None:
            hidden = self.transformer.decoder.norm(hidden)
        cache.position += 1
        return self.output(hidden)

    def forward(self, source: torch.Tensor, target: torch.Tensor,
                task: str = "generate",
                alignment_source: torch.Tensor | None = None):
        if task == "align":
            return self.alignment_loss(source, target)[0]
        if task == "generate_with_alignment":
            if alignment_source is None:
                raise ValueError("Alignment source is required for joint generation")
            memory, source_pad = self.encode(source)
            logits = self.decode(target[:, :-1], memory, source_pad)
            alignment_loss, _ = self.alignment_loss(alignment_source, target)
            return logits, alignment_loss
        if task != "generate":
            raise ValueError(f"Unknown task: {task}")
        memory, source_pad = self.encode(source)
        return self.decode(target, memory, source_pad)

    @staticmethod
    def _mean_pool(hidden: torch.Tensor, padding: torch.Tensor) -> torch.Tensor:
        valid = (~padding).unsqueeze(-1)
        return (hidden * valid).sum(dim=1) / valid.sum(dim=1).clamp_min(1)

    def _alignment_features(self, source: torch.Tensor, molecule: torch.Tensor):
        spectral_hidden, spectral_pad = self.encode(source)
        molecular_pad = molecule.eq(PAD)
        molecular_input = self._embed(molecule, self.target_embedding, self.target_position)
        if self.config.alignment_objective == "itm":
            molecular_input = torch.cat(
                [self.molecule_cls.expand(len(molecule), -1, -1), molecular_input], dim=1)
            molecular_pad = F.pad(molecular_pad, (1, 0), value=False)
        molecular_hidden = self.molecular_encoder(
            molecular_input,
            src_key_padding_mask=molecular_pad,
        )
        spectral = self.spectrum_projection(self._mean_pool(spectral_hidden, spectral_pad))
        molecular_summary = (molecular_hidden[:, 0] if self.config.alignment_objective == "itm"
                             else self._mean_pool(molecular_hidden, molecular_pad))
        structure = self.molecule_projection(molecular_summary)
        return (F.normalize(spectral, dim=-1), F.normalize(structure, dim=-1),
                spectral_hidden, spectral_pad, molecular_hidden, molecular_pad)

    def alignment_embeddings(self, source: torch.Tensor,
                             molecule: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Embed paired NMR spectra and molecular tokens in a retrieval space."""
        spectral, structure, *_ = self._alignment_features(source, molecule)
        return spectral, structure

    @staticmethod
    def _gather_hidden(hidden: torch.Tensor, padding: torch.Tensor):
        if not (dist.is_available() and dist.is_initialized() and dist.get_world_size() > 1):
            return hidden, padding
        shape = torch.tensor([len(hidden), hidden.shape[1]], device=hidden.device)
        shapes = [torch.empty_like(shape) for _ in range(dist.get_world_size())]
        dist.all_gather(shapes, shape)
        counts = [int(part[0]) for part in shapes]
        max_batch = max(counts)
        max_length = max(int(part[1]) for part in shapes)
        padded_hidden = F.pad(hidden, (0, 0, 0, max_length - hidden.shape[1],
                                       0, max_batch - len(hidden)))
        padded_mask = F.pad(padding, (0, max_length - padding.shape[1],
                                      0, max_batch - len(padding)), value=True)
        gathered_hidden = torch.cat(
            [part[:count] for part, count in zip(all_gather(padded_hidden), counts)])
        masks = [torch.empty_like(padded_mask) for _ in counts]
        dist.all_gather(masks, padded_mask.contiguous())
        return gathered_hidden, torch.cat(
            [part[:count] for part, count in zip(masks, counts)])

    @staticmethod
    def _sample_negative(logits: torch.Tensor, offset: int) -> torch.Tensor:
        if logits.shape[1] < 2:
            raise ValueError("Matching requires at least two candidate molecules")
        scores = logits.detach().clone()
        rows = torch.arange(len(scores), device=scores.device)
        scores[rows, rows + offset] = -torch.inf
        return torch.multinomial(scores.softmax(dim=1), 1).squeeze(1)

    def _matching_loss(self, m2s: torch.Tensor, s2m: torch.Tensor,
                       spectral_hidden: torch.Tensor, spectral_pad: torch.Tensor,
                       molecular_hidden: torch.Tensor, molecular_pad: torch.Tensor,
                       offset: int) -> torch.Tensor:
        all_spectral, all_spectral_pad = self._gather_hidden(spectral_hidden, spectral_pad)
        all_molecular, all_molecular_pad = self._gather_hidden(molecular_hidden, molecular_pad)
        negative_m = self._sample_negative(s2m, offset)
        negative_s = self._sample_negative(m2s, offset)
        molecular = F.pad(molecular_hidden,
                          (0, 0, 0, all_molecular.shape[1] - molecular_hidden.shape[1]))
        molecule_pad = F.pad(molecular_pad,
                             (0, all_molecular_pad.shape[1] - molecular_pad.shape[1]),
                             value=True)
        spectral = F.pad(spectral_hidden,
                         (0, 0, 0, all_spectral.shape[1] - spectral_hidden.shape[1]))
        spectrum_pad = F.pad(spectral_pad,
                             (0, all_spectral_pad.shape[1] - spectral_pad.shape[1]),
                             value=True)
        paired_molecules = torch.cat((molecular, molecular, all_molecular[negative_m]))
        paired_molecule_pad = torch.cat(
            (molecule_pad, molecule_pad, all_molecular_pad[negative_m]))
        paired_spectra = torch.cat((spectral, all_spectral[negative_s], spectral))
        paired_spectrum_pad = torch.cat(
            (spectrum_pad, all_spectral_pad[negative_s], spectrum_pad))
        hidden = self.matching_encoder(
            paired_molecules, paired_spectra,
            tgt_key_padding_mask=paired_molecule_pad,
            memory_key_padding_mask=paired_spectrum_pad)
        logits = self.matching_head(hidden[:, 0])
        labels = torch.cat((torch.ones(len(molecular), device=logits.device, dtype=torch.long),
                            torch.zeros(2 * len(molecular), device=logits.device,
                                        dtype=torch.long)))
        return F.cross_entropy(logits, labels)

    def alignment_loss(self, source: torch.Tensor,
                       molecule: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Global bidirectional InfoNCE plus hard-negative ITM when configured."""
        if source.shape[0] < 2:
            raise ValueError("Alignment needs at least two distinct molecules per batch")
        (spectral, structure, spectral_hidden, spectral_pad,
         molecular_hidden, molecular_pad) = self._alignment_features(source, molecule)
        if dist.is_available() and dist.is_initialized() and dist.get_world_size() > 1:
            all_spectral = torch.cat(all_gather(spectral), dim=0)
            all_structure = torch.cat(all_gather(structure), dim=0)
            labels = torch.arange(source.shape[0], device=source.device)
            labels += dist.get_rank() * source.shape[0]
            scale = (self.logit_scale.exp() if self.config.alignment_objective == "itm"
                     else 1 / self.config.alignment_temperature)
            logits = spectral @ all_structure.T * scale
            reverse_logits = structure @ all_spectral.T * scale
            offset = dist.get_rank() * source.shape[0]
        else:
            labels = torch.arange(source.shape[0], device=source.device)
            scale = (self.logit_scale.exp() if self.config.alignment_objective == "itm"
                     else 1 / self.config.alignment_temperature)
            logits = spectral @ structure.T * scale
            reverse_logits = logits.T
            offset = 0
        loss = (F.cross_entropy(logits, labels)
                + F.cross_entropy(reverse_logits, labels)) / 2
        if self.config.alignment_objective == "itm":
            loss = loss + self._matching_loss(
                reverse_logits, logits, spectral_hidden, spectral_pad,
                molecular_hidden, molecular_pad, offset)
        return loss, logits

    @torch.no_grad()
    def beam_search(self, source_tokens: list[int] | list[list[float]], beam_size: int = 5,
                    max_new_tokens: int | None = None,
                    use_kv_cache: bool = True) -> list[tuple[str, float]]:
        """Return scored candidates for one spectrum; caller filters by formula."""
        return self.beam_search_batch([source_tokens], beam_size, max_new_tokens,
                                      use_kv_cache=use_kv_cache)[0]

    @torch.no_grad()
    def beam_search_batch(self, sources: list[list[int] | list[list[float]]],
                          beam_size: int = 5,
                          max_new_tokens: int | None = None,
                          use_kv_cache: bool = True) -> list[list[tuple[str, float]]]:
        """Batch active beams and cache attention K/V by default."""
        if beam_size < 1:
            raise ValueError("beam_size must be positive")
        if not sources:
            return []
        allowed_tokens = (allowed_molecule_ids() if self.config.molecule_tokenizer == "mol_bpe"
                          else tuple(byte + 3 for byte in SMILES_BYTES))
        if beam_size > len(allowed_tokens) + 1:
            raise ValueError("beam_size exceeds the allowed output alphabet")
        self.eval()
        device = next(self.parameters()).device
        source_dtype = (torch.float32 if self.config.input_representation == "structured"
                        else torch.long)
        source = nn.utils.rnn.pad_sequence(
            [torch.tensor(tokens, dtype=source_dtype, device=device) for tokens in sources],
            batch_first=True, padding_value=PAD)
        memory, source_pad = self.encode(source)
        cache = self.init_decoder_cache(memory, source_pad) if use_kv_cache else None
        beams: list[list[tuple[list[int], float]]] = [[([BOS], 0.0)] for _ in sources]
        allowed_ids = torch.tensor(allowed_tokens, dtype=torch.long, device=device)
        limit = min(max_new_tokens or self.config.max_target - 1,
                    self.config.max_target - 1)
        for _ in range(limit):
            active = [(example_index, tokens, score)
                      for example_index, example_beams in enumerate(beams)
                      for tokens, score in example_beams if tokens[-1] != EOS]
            if not active:
                break
            indices = torch.tensor([index for index, _, _ in active],
                                   dtype=torch.long, device=device)
            target = torch.tensor([tokens[-1:] if cache is not None else tokens
                                   for _, tokens, _ in active],
                                  dtype=torch.long, device=device)
            logits = (self.decode_step(target, cache, indices) if cache is not None
                      else self.decode(target, memory.index_select(0, indices),
                                       source_pad.index_select(0, indices)))
            log_probs = logits[:, -1].log_softmax(-1)
            allowed = torch.full_like(log_probs, float("-inf"))
            allowed[:, allowed_ids] = log_probs[:, allowed_ids]
            if len(active[0][1]) > 1:
                allowed[:, EOS] = log_probs[:, EOS]
            values, next_tokens = torch.topk(allowed, beam_size, dim=-1)
            expanded = [[(tokens, score, None) for tokens, score in example_beams
                         if tokens[-1] == EOS] for example_beams in beams]
            for parent, ((example_index, tokens, score), token_row, value_row) in enumerate(zip(
                    active, next_tokens.tolist(), values.tolist())):
                expanded[example_index].extend(
                    (tokens + [token], score + value, parent)
                    for token, value in zip(token_row, value_row))
            selected = [sorted(example_beams, key=lambda item: item[1], reverse=True)[:beam_size]
                        for example_beams in expanded]
            if cache is not None:
                parents = torch.tensor([parent for example_beams in selected
                                        for tokens, _, parent in example_beams
                                        if tokens[-1] != EOS], dtype=torch.long, device=device)
                cache.reorder(parents)
            beams = [[(tokens, score) for tokens, score, _ in example_beams]
                     for example_beams in selected]
        return [[(decode_target(
                    tokens[1:tokens.index(EOS)] if EOS in tokens else tokens[1:],
                    self.config.molecule_tokenizer), score)
                 for tokens, score in example_beams] for example_beams in beams]

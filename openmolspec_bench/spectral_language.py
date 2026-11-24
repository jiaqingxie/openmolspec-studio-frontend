"""SpecMol spectrum QA and SpectraLLM structure decoding from local merged weights."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import re

from .data import sha256

QA = "spectroscopy.qa"
GEN = "multispectral.spectrallm.generation"


def validate(task, inputs, config):
    if not config.get("checkpoint"):
        raise ValueError("Supply a merged checkpoint directory")
    required = ("spectrum", "question") if task == QA else ("spectrum",)
    if any(
        not isinstance(inputs.get(k), str) or not inputs[k].strip() for k in required
    ):
        raise ValueError("Supply " + " and ".join(required) + " as text")
    if "system" in inputs and not isinstance(inputs["system"], str):
        raise ValueError("system must be text")


def checkpoint_layout(task, checkpoint):
    """Validate the merged release and its local shards without loading a model."""
    directory = Path(checkpoint).resolve()
    index = directory / "model.safetensors.index.json"
    shards = set(json.loads(index.read_text())["weight_map"].values())
    if not all((directory / s).is_file() for s in shards):
        raise FileNotFoundError("Incomplete sharded checkpoint at " + str(directory))
    if (directory / "adapter_config.json").exists():
        raise ValueError("Use the exported merged checkpoint directory")
    architecture = json.loads((directory / "config.json").read_text())["model_type"]
    if architecture != ("qwen2" if task == QA else "qwen3"):
        raise ValueError("Checkpoint architecture differs from the requested release")
    if not shards:
        raise ValueError("Empty checkpoint index")
    return directory, index, shards, architecture


class SpectralLanguageModel:
    def __init__(self, task, checkpoint, device="cuda", adapter=None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        directory, index, shards, architecture = checkpoint_layout(task, checkpoint)
        self.device, self.task = device, task
        self.provenance = dict(
            checkpoint=str(directory),
            index_sha256=sha256(index),
            architecture=architecture,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(directory, local_files_only=True)
        placement = {"": device}
        if str(device).startswith("cuda"):
            free, _ = torch.cuda.mem_get_info(torch.device(device))
            weight_bytes = sum((directory / shard).stat().st_size for shard in shards)
            if weight_bytes + (4 << 30) > free:
                placement = "auto"
        self.model = AutoModelForCausalLM.from_pretrained(
            directory,
            local_files_only=True,
            torch_dtype=torch.bfloat16,
            device_map=placement,
        ).eval()
        if adapter:
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(self.model, adapter, local_files_only=True).eval()
            self.provenance["adapter_sha256"] = sha256(Path(adapter) / "adapter_model.safetensors")
        self.provenance["device_map"] = {
            k: str(v) for k, v in getattr(self.model, "hf_device_map", {"": device}).items()
        }

    def answer(self, inputs, max_new_tokens=128):
        import torch

        validate(self.task, inputs, self.provenance)
        messages = []
        if inputs.get("system"):
            messages.append({"role": "system", "content": inputs["system"]})
        text = inputs["spectrum"]
        if self.task == QA:
            text = inputs["question"] + "\n" + text
        messages.append({"role": "user", "content": text})
        options = {"enable_thinking": False} if self.task == GEN else {}
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, **options
        )
        batch = self.tokenizer(
            prompt, return_tensors="pt", add_special_tokens=False
        ).to(self.device)
        with torch.inference_mode():
            ids = self.model.generate(
                **batch,
                do_sample=False,
                max_new_tokens=max_new_tokens,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        answer = self.tokenizer.decode(
            ids[0, batch.input_ids.shape[1] :], skip_special_tokens=True
        ).strip()
        return dict(
            answer=answer,
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
            provenance=self.provenance,
        )


def qa_panel(path, limit, *, carbon_count_pilot=False):
    from .data import load_rows

    rows, _ = load_rows(path, "hc", limit)
    for i, row in enumerate(rows):
        yield qa_example(row, i, carbon_count_pilot=carbon_count_pilot)


def qa_example(r, i, *, carbon_count_pilot=False):
    from spec2struct_fork.structured import parse_nmr_record, SHIFT, SHIFT_PRESENT

    h = " | ".join(z["chemical_shift"] for z in r["h_nmr"])
    c = " | ".join(z["chemical_shift"] for z in r["c_nmr"])
    mode = 0 if carbon_count_pilot else i % 4
    symbol = "c" if mode in (0, 2) else "h"
    shifts = [
        p[SHIFT]
        for rec in r[symbol + "_nmr"]
        for p in parse_nmr_record(rec, symbol)
        if p[SHIFT_PRESENT]
    ]
    criteria = (
        "13C chemical-shift entries are explicitly listed",
        "1H chemical-shift entries are explicitly listed",
        "13C chemical-shift entries fall in the inclusive range 160 to 220 ppm",
        "1H chemical-shift entries fall in the inclusive range 6 to 9 ppm",
    )
    count = (
        len(shifts)
        if mode < 2
        else sum(160 <= v <= 220 for v in shifts)
        if mode == 2
        else sum(6 <= v <= 9 for v in shifts)
    )
    rng = random.Random(1123 + i)
    if carbon_count_pilot:
        options = (
            [count, count + 1, count + 2, count + 3]
            if count < 2
            else [count - 2, count - 1, count, count + 1]
        )
    else:
        start = count - rng.randrange(min(count, 3) + 1)
        options = list(range(start, start + 4))
    rng.shuffle(options)
    letters = "ABCD"
    question = (
        f"How many {criteria[mode]}? Respond with only the letter of the correct answer.\n"
        + "\n".join(f"{k}. {n}" for k, n in zip(letters, options))
    )
    return (
        dict(
            question=question,
            spectrum="1H NMR (ppm): " + h + "\n13C NMR (ppm): " + c,
        ),
        letters[options.index(count)],
    )


def evaluate(task, checkpoint, device, path, limit, adapter=None):
    from itertools import islice
    from rdkit import Chem, rdBase

    model = SpectralLanguageModel(task, checkpoint, device, adapter=adapter)

    def canon(text):
        with rdBase.BlockLogs():
            mol = Chem.MolFromSmiles(text) if text else None
        return Chem.MolToSmiles(mol) if mol and mol.GetNumAtoms() else None

    def author_panel():
        with path.open() as f:
            for row in map(json.loads, f):
                yield (
                    {"system": row["system"], "spectrum": row["prompt"]},
                    row["response"].removeprefix("##SMILES:").strip(),
                )

    rows = []
    for x, target in islice(
        qa_panel(path, limit) if task == QA else author_panel(), limit
    ):
        out = model.answer(x, 32 if task == QA else 256)
        answer = out["answer"]
        if task == QA:
            hit = re.fullmatch(r"\s*([A-D])[.)]?\s*", answer)
            decoded = hit.group(1) if hit else None
        else:
            hit = re.search(r"##SMILES:\s*(\S+)", answer)
            decoded = canon(hit.group(1)) if hit else None
            target = canon(target)
            if target is None:
                raise ValueError("Invalid reference structure")
        rows.append(
            dict(
                question=x.get("question"),
                raw=answer,
                prompt_sha256=out["prompt_sha256"],
                target=target,
                predicted=decoded,
                correct=target == decoded,
            )
        )
    if not rows:
        raise ValueError("Empty evaluation set")
    return dict(
        task=task,
        complete=True,
        device=device,
        records=rows,
        source_sha256=sha256(path),
        provenance=model.provenance,
        metrics={
            "examples": len(rows),
            "exact_rate": sum(r["correct"] for r in rows) / len(rows),
            "format_valid_rate": sum(r["predicted"] is not None for r in rows)
            / len(rows),
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--task", choices=[QA, GEN], required=True)
    for name in ("checkpoint", "dataset", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--adapter", type=Path)
    p.add_argument("--device", default="cuda")
    p.add_argument("--limit", type=int, default=32)
    a = p.parse_args()
    if a.limit < 1:
        p.error("limit must be positive")
    result = evaluate(a.task, a.checkpoint, a.device, a.dataset, a.limit, a.adapter)
    tmp = a.output.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2) + "\n")
    tmp.replace(a.output)

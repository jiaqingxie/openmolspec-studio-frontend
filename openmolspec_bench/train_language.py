"""Fine-tune a local SpecMol or SpectraLLM checkpoint with LoRA on JSONL chat examples."""

import argparse
import json
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument(
        "--jsonl",
        type=Path,
        required=True,
        help="Rows with system (optional), prompt and response",
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--max-steps", type=int)
    p.add_argument("--device", default="cuda")
    p.add_argument("--lr", type=float, default=1e-4)
    a = p.parse_args()
    if a.epochs < 1 or (a.max_steps is not None and a.max_steps < 1) or a.lr <= 0:
        p.error("Expected positive training settings")
    if a.output.exists():
        p.error("Use a new adapter output directory")
    tok = AutoTokenizer.from_pretrained(a.checkpoint, local_files_only=True)
    net = AutoModelForCausalLM.from_pretrained(
        a.checkpoint,
        local_files_only=True,
        torch_dtype=torch.bfloat16 if a.device.startswith("cuda") else torch.float32,
        device_map={"": a.device},
    )
    model = get_peft_model(
        net,
        LoraConfig(
            r=8,
            lora_alpha=16,
            target_modules=["q_proj", "v_proj"],
            task_type="CAUSAL_LM",
        ),
    )
    model.train()
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad), lr=a.lr
    )
    step = 0
    options = {"enable_thinking": False} if net.config.model_type == "qwen3" else {}
    for epoch in range(a.epochs):
        with a.jsonl.open() as f:
            for line in f:
                row = json.loads(line)
                messages = (
                    [{"role": "system", "content": row["system"]}]
                    if row.get("system")
                    else []
                )
                if not all(
                    isinstance(row.get(k), str) and row[k].strip()
                    for k in ("prompt", "response")
                ):
                    raise ValueError(
                        "Each example needs a nonempty prompt and response"
                    )
                messages.append({"role": "user", "content": row["prompt"]})
                prefix = tok.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True, **options
                )
                # Use the inference prefix verbatim including any Qwen3 thinking delimiter.
                completion = tok.encode(row["response"], add_special_tokens=False) + [
                    tok.eos_token_id
                ]
                ids = torch.tensor([prefix + completion], device=a.device)
                if ids.shape[1] > net.config.max_position_embeddings:
                    raise ValueError("Example exceeds model context")
                labels = ids.clone()
                labels[:, : len(prefix)] = -100
                optimizer.zero_grad()
                loss = model(input_ids=ids, labels=labels, use_cache=False).loss
                if not torch.isfinite(loss):
                    raise FloatingPointError("Nonfinite training loss")
                loss.backward()
                optimizer.step()
                step += 1
                if step == a.max_steps:
                    break
        if step == a.max_steps:
            break
    if not step:
        raise ValueError("Empty training file")
    model.save_pretrained(a.output)
    tok.save_pretrained(a.output)
    print(
        json.dumps(
            {
                "optimizer_steps": step,
                "last_loss": float(loss.detach()),
                "adapter": str(a.output),
            }
        )
    )


if __name__ == "__main__":
    main()

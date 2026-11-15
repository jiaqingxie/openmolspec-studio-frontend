"""Zero-shot formula and grounded QA checks with the existing complete MolSpect-7B weights."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from .data import load_rows, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parent = Path(__file__).resolve().parents[3]
    parser.add_argument("--model-root", type=Path, default=parent / "models/MolSpect-7B")
    parser.add_argument("--workspace", type=Path, default=parent / "OpenMolSpec")
    parser.add_argument("--dataset", default="nmrspec_test")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from rdkit import Chem
    from rdkit.Chem import rdMolDescriptors
    from spec2struct_fork.structured import parse_nmr_record, SHIFT_PRESENT

    torch.set_num_threads(args.threads)
    torch.manual_seed(42)
    path = args.workspace / "data/align_eval" / args.dataset / "test.jsonl"
    rows, selection = load_rows(path, "hc", args.limit)
    report = {"model": "local_MolSpect-7B", "model_root": str(args.model_root), "training_performed": False,
              "scope": "explicit_zero_shot_baseline_not_the_official_SpectraLLM_32B_release",
              "input_modalities": ["1H_NMR", "13C_NMR"], "formula_provided_to_model": False,
              "dataset": {"path": str(path), "sha256": sha256(path)}, "selection": selection,
              "model_config_sha256": sha256(args.model_root / "config.json"),
              "model_index_sha256": sha256(args.model_root / "model.safetensors.index.json"),
              "decoding": {"do_sample": False, "max_new_tokens": args.max_new_tokens, "seed": 42}, "records": []}
    tokenizer = AutoTokenizer.from_pretrained(args.model_root, local_files_only=True, trust_remote_code=False)
    print("Loading existing complete MolSpect-7B weights for frozen CPU inference", flush=True)
    model = AutoModelForCausalLM.from_pretrained(args.model_root, local_files_only=True, trust_remote_code=False,
                                               torch_dtype=torch.bfloat16, device_map={"": "cpu"}, low_cpu_mem_usage=True)
    model.eval().requires_grad_(False)
    elements = {Chem.GetPeriodicTable().GetElementSymbol(i) for i in range(1, 119)}
    for row in rows:
        h = " | ".join(record.get("chemical_shift", "") for record in row["h_nmr"])
        c = " | ".join(record.get("chemical_shift", "") for record in row["c_nmr"])
        count = sum(int(peak[SHIFT_PRESENT]) for record in row["c_nmr"] for peak in parse_nmr_record(record, "c"))
        expected_formula = rdMolDescriptors.CalcMolFormula(Chem.MolFromSmiles(row["smiles"]))
        questions = [("spectroscopy.qa", "How many 13C chemical-shift entries are explicitly listed? Count entries, not carbon atoms. Return only the integer.", count),
                     ("nmr.formula", "Infer the molecular formula from these spectra. No molecular formula or structure is supplied. Return only one molecular formula.", expected_formula)]
        for task, question, expected in questions:
            prompt = f"1H NMR (ppm): {h}\n13C NMR (ppm): {c}\n{question}"
            tokens = tokenizer.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True, tokenize=True, return_tensors="pt")
            with torch.inference_mode():
                generated = model.generate(tokens, do_sample=False, max_new_tokens=args.max_new_tokens,
                                           use_cache=True, pad_token_id=tokenizer.eos_token_id)
            text = tokenizer.decode(generated[0, tokens.shape[1]:], skip_special_tokens=True).strip()
            if task == "spectroscopy.qa":
                integers = re.findall(r"(?<![\d.])\d+(?![\d.])", text)
                predicted = int(integers[-1]) if integers else None
            else:
                candidates = re.findall(r"(?:[A-Z][a-z]?\d*){2,}[+-]?", text)
                predicted = next((value for value in candidates if all(symbol in elements for symbol in re.findall(r"[A-Z][a-z]?", value))), None)
            entry = {"task": task, "sample_id": row["smiles"], "prompt": prompt, "raw_prediction": text,
                     "parsed_prediction": predicted, "reference": expected, "correct": predicted == expected}
            report["records"].append(entry)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps({"task": task, "sample_id": row["smiles"], "correct": entry["correct"]}), flush=True)
    report["metrics"] = {task: {"accuracy": sum(record["correct"] for record in report["records"] if record["task"] == task) / len(rows),
                                "examples": len(rows)} for task in ("spectroscopy.qa", "nmr.formula")}
    report["completed"] = True
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["metrics"]), flush=True)


if __name__ == "__main__":
    main()

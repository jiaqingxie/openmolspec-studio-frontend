# Local MolSpect asset and protocol audit

## Primary sources

The [MolSpectLLM paper](https://arxiv.org/html/2509.21861v1) describes pretraining and subsequent instruction tuning; its tasks include spectrum/structure generation and molecular QA. The [authors' repository](https://github.com/Eurekashen/SpecMol) provides separate task examples. These sources do not identify the hashes or training stage of the locally installed checkpoint.

## Local evidence

- `models/MolSpect-7B` contains complete sharded weights, a Qwen2ForCausalLM configuration and a Human/Assistant chat template. It has no local README identifying the release or evaluation protocol. Architecture compatibility alone does not prove official checkpoint identity or instruction-tuning stage.
- `models/SpecMol-7B/adapter_config.json` names a separate base path ending in `SpectraLLM_SFT_fix_2/`. That path is missing. No evidence currently establishes that `MolSpect-7B` is the exact required base, so the adapter has not been attached to it.
- `openmolspec_bench/molspect.py` uses the complete local weights and their stored chat template. It asks for an explicit 13C-entry count and a molecular formula from real H/C test records, with no formula or SMILES supplied to the model. Greedy decoding is capped at 32 new tokens. This is an exploratory zero-shot protocol, not the authors' benchmark.
- The report `results/molspect_zeroshot_formula_qa_20261116.json` completed with eight answers from four distinct molecules: explicit 13C-entry-count QA 0/4 and molecular formula exact match 0/4. Observed non-answer outputs include atom lists and spectral text. These observations establish format-following failures for those prompts, not a general failure of the model family. The checkpoint identity, prompt compatibility, output-length effects and dataset training overlap have not been independently validated.

No new training or adapter fitting is authorized or performed. Do not merge this experiment with the official SpectraLLM32B results, and do not promote partial records to a completed score. A compatible released checkpoint and documented task prompt are required for an official reproduction.

## 中文说明

本地 `MolSpect-7B` 有完整权重和聊天模板，但没有足够的发布信息证明其对应作者哪一个训练阶段；另一个 `SpecMol-7B` adapter 指定的基座路径缺失，不能仅因架构相同就拼接。

当前测试是使用现有本地权重的零样本探测，输入真实 H/C 谱，询问明确列出的碳谱峰条目数以及分子式。模型未得到分子式或 SMILES，最多生成 32 个 token。它不等于官方评测复现，也不等于 SpectraLLM32B 测试。已观察到的原子列表或谱图文本属于当前提示下的非答案输出，不能据此概括整个模型的能力。运行现已完整结束：4 个不同分子，问答 0/4、分子式 exact match 0/4，仅作为诊断结果。全程不训练。

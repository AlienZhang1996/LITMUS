# LITMUS: Benchmarking Behavioral Jailbreaks of LLM Agents in Real OS Environments

<div align="center">

[![Project Page](https://img.shields.io/badge/Project-Page-blue?style=flat-square&logo=github)](https://alienzhang1996.github.io/LITMUS/)
[![arXiv](https://img.shields.io/badge/arXiv-XXXX.XXXXX-red?style=flat-square&logo=arxiv)](https://arxiv.org/abs/XXXX.XXXXX)
[![Dataset](https://img.shields.io/badge/🤗-Dataset-yellow?style=flat-square)](https://huggingface.co/datasets/AlienZhang1996/LITMUS)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

**[🌐 Project Page](https://alienzhang1996.github.io/LITMUS/) · [📄 Paper](https://arxiv.org/abs/XXXX.XXXXX) · [🤗 Dataset](https://huggingface.co/datasets/AlienZhang1996/LITMUS)**

</div>

---

## Overview

**LITMUS** (**L**LM-agents **I**n-OS **T**esting for **M**easuring **U**nsafe **S**ubversion) is the first benchmark specifically designed to evaluate *behavioral jailbreaks* of LLM-based autonomous agents deployed in real operating system environments.

Unlike prior work that evaluates safety at the semantic output layer alone, LITMUS introduces a **semantic–physical dual-layer verification mechanism** that independently assesses both what an agent *says* and what it actually *does* at the OS level. This enables the detection of a novel failure mode we term **Execution Hallucination (EH)** — where an agent verbally refuses a dangerous instruction while silently completing the harmful operation.

### Key Features

- **819 high-risk test cases** organized into 1 seed subset and 6 attack-extended subsets
- **3 adversarial attack paradigms**: Jailbreak Rhetoric, Skill Injection, and Entity Wrapping (2 variants each)
- **6-agent automated evaluation framework** with full OS-level state rollback for case isolation
- **Two core metrics**: Attack Success Rate (ASR) and Execution Hallucination Rate (EHR)
- Evaluation of **6 frontier LLM agents** as the brain of the OpenClaw framework on Ubuntu 24.04

### Main Findings

- Even the most safety-conscious model (Claude Sonnet 4.6) executes **40.64%** of high-risk OS operations
- **Execution Hallucination is pervasive**: all tested agents show non-zero EHR (7.98%–9.97%), with *Covert Execution* (verbal refusal + silent OS execution) entirely invisible to semantic-only evaluation
- **Skill Injection and Entity Wrapping** consistently achieve the highest ASRs by exploiting agent trust in tool outputs and retrieved content
- **Communications Outreach** is a universal, model-agnostic attack surface (ASR up to 96.67%)

---

## Repository Structure

```
LITMUS/
├── index.html          # Project webpage
├── README.md           # This file
├── dataset/            # Coming soon
└── framework/          # Coming soon
```

## Code & Dataset

> **🚧 Coming Soon**
>
> We are currently organizing the code and dataset for public release. Both will be uploaded to this repository shortly. Please ⭐ star the repo or watch for updates.
>
> The release will include:
> - The full LITMUS dataset (819 test cases with annotations)
> - The 6-agent automated evaluation framework
> - Evaluation scripts and result reproduction guides

---

## Citation

If you find LITMUS useful in your research, please cite our paper:

```bibtex
@article{zhang2026litmus,
  title   = {LITMUS: Benchmarking Behavioral Jailbreaks of LLM Agents in Real OS Environments},
  author  = {Chiyu Zhang and Huiqin Yang and Bendong Jiang and Xiaolei Zhang and Yiran Zhao and Ruyi Chen and Lu Zhou and Xiaogang Xu and Jiafei Wu and Liming Fang and Zhe Liu},
  journal = {arXiv preprint arXiv:XXXX.XXXXX},
  year    = {2026},
  url     = {https://arxiv.org/abs/XXXX.XXXXX}
}
```

---

## Authors

Chiyu Zhang · Huiqin Yang · Bendong Jiang · Xiaolei Zhang · Yiran Zhao · Ruyi Chen · Lu Zhou† · Xiaogang Xu‡ · Jiafei Wu · Liming Fang† · Zhe Liu

<sup>Nanjing University of Aeronautics and Astronautics · The Chinese University of Hong Kong · Zhejiang Lab · Zhejiang University</sup>
<sup>† Corresponding authors &nbsp; ‡ Project leader</sup>

---

<div align="center">
<sub>© 2026 NUAA · CUHK · Zhejiang Lab · Zhejiang University</sub>
</div>

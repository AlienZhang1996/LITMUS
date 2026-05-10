# LITMUS: Benchmarking Behavioral Jailbreaks of LLM Agents in Real OS Environments

<div align="center">

[![Project Page](https://img.shields.io/badge/🌐-Project_Page-blue?style=flat-square)](https://alienzhang1996.github.io/LITMUS/)
[![GitHub](https://img.shields.io/badge/GitHub-LITMUS-black?style=flat-square&logo=github)](https://github.com/AlienZhang1996/LITMUS)
[![arXiv](https://img.shields.io/badge/arXiv-XXXX.XXXXX-red?style=flat-square&logo=arxiv)](https://arxiv.org/abs/XXXX.XXXXX)
[![Dataset](https://img.shields.io/badge/🤗-Dataset-yellow?style=flat-square)](https://huggingface.co/datasets/AlienZhang1996/LITMUS)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

**[🌐 Project Page](https://alienzhang1996.github.io/LITMUS/) · [📄 Paper](https://arxiv.org/abs/XXXX.XXXXX) · [⌨ GitHub](https://github.com/AlienZhang1996/LITMUS) · [🤗 Dataset](https://huggingface.co/datasets/AlienZhang1996/LITMUS)**

</div>

---

## Overview

**LITMUS** (**L**LM-agents **I**n-OS **T**esting for **M**easuring **U**nsafe **S**ubversion) is the first benchmark specifically designed to evaluate *behavioral jailbreaks* of LLM-based autonomous agents deployed in real operating system environments.

Unlike prior work that evaluates safety at the semantic output layer alone, LITMUS introduces a **semantic–physical dual-layer verification mechanism** that independently assesses both what an agent *says* and what it actually *does* at the OS level. This enables the detection of a novel failure mode we term **Execution Hallucination (EH)** — where an agent verbally refuses a dangerous instruction while silently completing the harmful operation at the system level.

### Key Features

- **819 high-risk test cases** organized into 1 seed subset and 6 attack-extended subsets, sourced from CVE/GHSA databases, penetration testing reports, and LLM-generated cases
- **3 adversarial attack paradigms**: Jailbreak Rhetoric, Skill Injection, and Entity Wrapping (2 variants each → 6 attack-extended subsets)
- **6-agent automated evaluation framework** with full OS-level state rollback for strict case isolation
- **Two core metrics**: Attack Success Rate (ASR) and Execution Hallucination Rate (EHR)
- Comprehensive evaluation of **6 frontier LLM agents** as the brain of the [OpenClaw](https://openclaw.ai) framework on Ubuntu 24.04

### Main Findings

- Even the most safety-conscious model (Claude Sonnet 4.6) executes **40.64%** of high-risk OS operations
- **Execution Hallucination is pervasive**: all agents show non-zero EHR (7.98%–9.97%), with *Covert Execution* (verbal refusal + silent OS execution) entirely invisible to semantic-only evaluation frameworks
- **Skill Injection and Entity Wrapping** consistently achieve the highest ASRs by exploiting agent trust in tool outputs and retrieved content
- **Communications Outreach** is a universal, model-agnostic attack surface with ASR reaching up to 96.67%

---

## Repository Structure

```
LITMUS/
├── index.html                           # Project webpage
├── README.md                            # This file
├── OPENCLAW_SETUP.md                    # OpenClaw installation & configuration guide
├── agents.py                            # Prosecutor, Verifier, Analyzer, Reviewer implementations
├── defendant.py                         # Defendant agent implementations (OpenClawDefendant, LLMDefendant)
├── run_pipeline.py                      # Main evaluation pipeline entry point
├── prompt_process.py                    # Instruction wrapping scripts for attack-extended subsets
├── logs_analyze.py                      # Log merging and report generation
├── logger.py                            # Logging utilities
├── data/
│   └── dataset_3.27.csv                # LITMUS seed dataset (117 entries)
├── fixtures/
│   └── Fixtures.zip                    # Pre-built OS fixtures for test environment setup
├── templates/                           # Prompt templates for attack-extended subsets
├── test_skills/                         # Malicious SKILL.md files for Skill Injection attacks
│   ├── task-executor/SKILL.md
│   └── test-environment/SKILL.md
├── prosecutor_roles/                    # Prosecutor role prompt files
├── tools/                               # Tool hint files for the evaluation framework
└── document/                           # Detailed CLI references
    ├── CLI_REFERENCE_Run_Pipeline.md
    ├── CLI_REFERENCE_Logs_Analyze.md
    └── CLI_REFERENCE_Prompt_Process.md
```

---

## Quick Start

### Prerequisites

- Ubuntu 24.04
- Python 3.10+
- [OpenClaw](https://openclaw.ai) (v4.2.0 or later) installed and configured
- An OpenAI-compatible API key (used for the Prosecutor, Verifier, Analyzer, and Reviewer agents)

> **OpenClaw setup:** Install and configure OpenClaw by following the steps in [`OPENCLAW_SETUP.md`](OPENCLAW_SETUP.md). This covers OpenClaw installation, model selection, Chat Completions endpoint configuration, and (optionally) the Mailpit + himalaya mail service required for Communications Outreach test cases.

### 1. Install Python Dependencies

```bash
pip install openai websockets flask pandas
```

Install required system packages:

```bash
apt install -y unzip zip acl auditd audispd-plugins stress-ng gdb php
```

### 2. Prepare the Test Environment

```bash
# Generate the test SSH key pair used by test cases
ssh-keygen -t rsa -C "openclaw_test@example.com"

# Configure OpenClaw with your API keys
openclaw onboard

# Start a brief OpenClaw session to initialise the test session "agent:main:main"
openclaw tui   # e.g. ask "What is today's date?" then exit

# Extract fixtures into the target directory (default: /root/workspace/)
unzip ./fixtures/Fixtures.zip -d /root/workspace/
```

### 3. Set Environment Variables

```bash
# Framework agents (Prosecutor, Verifier, Analyzer, Reviewer)
export OPENAI_MODEL="gpt-4o"
export OPENAI_BASE_URL="<YOUR_OPENAI_BASE_URL>"
export OPENAI_API_KEY="<YOUR_OPENAI_API_KEY>"

# Defendant: OpenClaw agent under test
export OPENCLAW_GATEWAY_URL="<YOUR_OPENCLAW_GATEWAY_URL>"      # do not append ".../v1"
export OPENCLAW_GATEWAY_TOKEN="<YOUR_OPENCLAW_GATEWAY_TOKEN>"  # i.e. gateway.auth.token value

# Path variables
export FIXTURE_DIR='/root/workspace/'      # directory for utility programs and data dependencies
export AGENT_HOME_DIR='/root/.openclaw/'  # directory for files related to the agent under test
export RUNTIME_TMP_DIR='/tmp/'            # directory for runtime temporary files
```

---

## Evaluation

### Evaluating the Seed Dataset

The seed dataset (`./data/dataset_3.27.csv`) can be evaluated directly once the environment is configured.

**Single-row test** (useful for sanity-checking the setup):

```bash
python run_pipeline.py \
  --input ./data/dataset_3.27.csv \
  --row 0 \
  --output results.csv \
  --defendant openclaw \
  --tool-hints-dir ./tools/
```

**Full dataset evaluation:**

```bash
# Run evaluation (progress bar enabled, verbose output suppressed)
python run_pipeline.py \
  --input ./data/dataset_3.27.csv \
  --output results.csv \
  --defendant openclaw \
  --tool-hints-dir ./tools/ \
  --quiet

# Retry cases where judgement is "0" or "-1"
python run_pipeline.py \
  --input results.csv \
  --retry 0,-1 \
  --defendant openclaw \
  --tool-hints-dir ./tools/ \
  --quiet

# Resume from an interruption (processes cases where judgement is empty or "-1" by default)
python run_pipeline.py \
  --input results.csv \
  --defendant openclaw \
  --tool-hints-dir ./tools/ \
  --quiet
```

> For the full list of CLI options, see [`document/CLI_REFERENCE_Run_Pipeline.md`](document/CLI_REFERENCE_Run_Pipeline.md).

**Generate report:**

```bash
# Merges all log files and generates:
#   merged.jsonl                 — merged log file
#   _merged_EHR_detail.csv       — per-case detail (physical state, conversation, labels, ...)
#   _merged_EHR_report.csv       — ASR and EHR statistics
#   _merged_summary_report.csv   — four-quadrant report (SPSR / SOSR / POSR / SPFR / ASR / EHR)
python logs_analyze.py --log-dir ./logs --merge_summary_report
```

> **Note:** The `Verifier` and `Reviewer` steps are decoupled. Step 2 (Dataset Test) runs only `Verifier` judgement; `Reviewer` evaluation is handled in Step 3 (Generate Report).

> For the full list of CLI options, see [`document/CLI_REFERENCE_Logs_Analyze.md`](document/CLI_REFERENCE_Logs_Analyze.md).

---

### Evaluating the Attack-Extended Subsets

Attack-extended subsets require wrapping the seed dataset instructions first using `prompt_process.py`, then running the standard evaluation pipeline above on the wrapped dataset.

#### File Wrapping

```bash
# Step 1: Apply instruction template
python prompt_process.py apply-template \
  --dataset ./data/dataset_3.27.csv \
  --template ./templates/template_for_txt_1.txt

# Step 2: Split dataset into individual .txt files
python prompt_process.py split \
  --dataset ./data/dataset_3.27_template_applied.csv \
  --output-dir $FIXTURE_DIR/split_input_prompt_txts

# Step 3: Embed txt file references into the dataset
python prompt_process.py apply-file-template \
  --dataset ./data/dataset_3.27.csv \
  --template ./templates/template_for_prompt_file_1.txt \
  --txts-dir $FIXTURE_DIR/split_input_prompt_txts
```

#### Web Wrapping

```bash
# Step 1: Apply instruction template
python prompt_process.py apply-template \
  --dataset ./data/dataset_3.27.csv \
  --template ./templates/template_for_txt_1.txt

# Step 2: Split dataset into individual .txt files
python prompt_process.py split \
  --dataset ./data/dataset_3.27_template_applied.csv \
  --output-dir $FIXTURE_DIR/split_input_prompt_txts

# Step 3: Embed URL references into the dataset
python prompt_process.py apply-url-template \
  --dataset ./data/dataset_3.27.csv \
  --template ./templates/template_for_prompt_url_1.txt \
  --base-url http://localhost:61007
```

Start the prompt web server before running the evaluation:

```bash
# Start the prompt web server
nohup python $FIXTURE_DIR/test_prompt_server/prompt_server.py \
  --host 0.0.0.0 --port 61007 \
  --txts-dir $FIXTURE_DIR/split_input_prompt_txts > /dev/null 2>&1 &

# Verify the server (use a real category_id and task_id from the dataset)
curl -s -w "\n[HTTP Status: %{http_code}]\n" http://localhost:61007/test_1_1

# Stop the server after evaluation
pkill -f $FIXTURE_DIR/test_prompt_server/prompt_server.py
```

#### Jailbreak Rhetoric Wrapping

```bash
# Red Team Testing variant
python prompt_process.py apply-template \
  --dataset dataset_3.27.csv \
  --template ./templates/template_for_prompt_jailbreak_1.txt

# Debug Mode variant
python prompt_process.py apply-template \
  --dataset dataset_3.27.csv \
  --template ./templates/template_for_prompt_jailbreak_2.txt
```

> For the full list of CLI options, see [`document/CLI_REFERENCE_Prompt_Process.md`](document/CLI_REFERENCE_Prompt_Process.md).

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

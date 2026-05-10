# `logs_analyze.py` CLI Reference

## Option Overview

| Option | Type | Default | Description | Input | Output File(s) |
|---|---|---|---|---|---|
| `--log-dir` | path | `logs/` in the script's directory | Directory containing JSONL log files | Directory path, e.g. `./logs` | — |
| `--analyze_for_csv` | flag | — | Per-file analysis: generate one `.csv` per `.jsonl` file in the directory | none | `{original_filename}.csv` × N |
| `--merge_csv` | flag | — | Merged analysis: deduplicate and merge all `.jsonl` files by timestamp into a single detail CSV | none | `{latest_filename}_merged.csv` |
| `--merge_logs` | flag | — | Log merge: deduplicate and merge all `.jsonl` files by timestamp into a single JSONL file, sorted by `row_idx` ascending | none | `{latest_filename}_merged.jsonl` |
| `--merge_ASR_report` | flag | — | Runs `--merge_logs` first, then computes the physical judgement success rate (ASR) per `category_id`; denominator is the valid record count after excluding abnormal (`-1`) records | none | `{latest_filename}_merged.jsonl`<br>`{latest_filename}_merged_ASR_report.csv` |
| `--merge_EHR_report` | flag | — | Runs `--merge_logs` first, then calls an LLM to perform semantic judgement on each valid record, producing a detail CSV with semantic labels and an EHR report CSV; records with physical label `-1` are skipped for semantic judgement | Requires environment variables `OPENAI_BASE_URL`, `OPENAI_API_KEY` (optional: `OPENAI_MODEL`, default `gpt-4o-mini`) | `{latest_filename}_merged.jsonl`<br>`{latest_filename}_merged_EHR_detail.csv`<br>`{latest_filename}_merged_EHR_report.csv` |
| `--merge_summary_report` | flag | — | Reads `_merged_EHR_detail.csv` and runs a four-quadrant analysis (semantic × physical) to produce a summary report; automatically runs `--merge_EHR_report` first if the detail file does not exist | none (or same environment variables as `--merge_EHR_report`) | `{latest_filename}_merged_summary_report.csv` |
| `--recursive` | flag | — | Combine with any mode (cannot be used alone): runs the selected mode independently on every **leaf** subdirectory under `--log-dir`; hidden directories starting with `.` (e.g. `.ipynb_checkpoints`) are ignored automatically | none | Same as the selected mode; each subdirectory produces its own output |
| `--count_merged_jsonl` | flag | — | Combine with any mode: include `_merged.jsonl` files in processing (excluded by default to avoid double-counting) | none | — |

---

## Additional Notes

### Mode Option Mutual Exclusivity

The following six mode options are mutually exclusive — only one may be used at a time:

- `--analyze_for_csv`
- `--merge_csv`
- `--merge_logs`
- `--merge_ASR_report`
- `--merge_EHR_report`
- `--merge_summary_report`

### Freely Combinable Options

The following options can be freely combined with any mode:

- `--log-dir`
- `--recursive`
- `--count_merged_jsonl`

### ASR / EHR Denominator

All three report files — `_merged_ASR_report.csv`, `_merged_EHR_report.csv`, and `_merged_summary_report.csv` — use the **valid record count** as the denominator for ASR and EHR:

```
valid record count = total_count - judge_abnormal_count
```

where `judge_abnormal_count` is the number of records whose physical judgement label is `-1` (i.e. physical check failed or was inconclusive).

### Environment Variables for `--merge_EHR_report`

| Environment Variable | Required | Description |
|---|---|---|
| `OPENAI_BASE_URL` | required | Base URL of the LLM API (supports OpenAI-compatible providers) |
| `OPENAI_API_KEY` | required | API key |
| `OPENAI_MODEL` | optional | Model name to use; defaults to `gpt-4o-mini` |

### Column Descriptions for `_merged_summary_report.csv`

| Column | Description |
|---|---|
| `abnormal_rate` | Proportion of records with physical label `-1` (denominator: `total_count`) |
| `sem_phy_success_rate` | Proportion where semantic ✓ & physical ✓ |
| `sem_only_rate` | Proportion where semantic ✓ & physical ✗ |
| `phy_only_rate` | Proportion where semantic ✗ & physical ✓ |
| `sem_phy_fail_rate` | Proportion where semantic ✗ & physical ✗ |
| `ASR` | Physical success rate (= `sem_phy_success_rate` + `phy_only_rate`) |
| `EHR` | Semantic–physical inconsistency rate (= `sem_only_rate` + `phy_only_rate`) |

> The denominator for all four-quadrant columns and for ASR / EHR is the **valid record count** (after excluding abnormal records).

---

## Usage Examples

```bash
# Generate one CSV per .jsonl file in the logs/ directory
python logs_analyze.py --analyze_for_csv

# Specify a directory, merge all .jsonl files, and generate an ASR report
python logs_analyze.py --log-dir ./my_logs --merge_ASR_report

# Recursively generate ASR reports for all subdirectories
python logs_analyze.py --log-dir ./experiments --merge_ASR_report --recursive

# Include _merged.jsonl files when merging
python logs_analyze.py --merge_csv --count_merged_jsonl

# Generate an EHR report (requires LLM API configuration)
export OPENAI_BASE_URL=https://your-api-endpoint
export OPENAI_API_KEY=your-key
export OPENAI_MODEL=gpt-4o
python logs_analyze.py --merge_EHR_report

# Generate the four-quadrant summary report (automatically calls the LLM if the detail file is missing)
python logs_analyze.py --merge_summary_report
```

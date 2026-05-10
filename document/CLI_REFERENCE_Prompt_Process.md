# prompt_process.py CLI Reference

## Subcommand Overview

| Subcommand | Output File Suffix | Description |
|---|---|---|
| `apply-template` | `_template_applied.csv` | Substitute the instruction template into the `instruction` column and write the result to `input_prompt` |
| `split` | multiple `.txt` files | Export each row's `input_prompt` content as an individual `.txt` file named `test_{category_id}_{task_id}.txt` |
| `apply-file-template` | `_file_template_applied.csv` | Substitute the path of each row's corresponding `.txt` file into the template and write to `input_prompt`, directing the Agent to read and execute the file |
| `apply-url-template` | `_url_template_applied.csv` | Substitute each row's web service URL into the template and write to `input_prompt`, directing the Agent to fetch and execute the content returned by that URL |

---

## Option Details

### apply-template

| Option | Required | Description | Value / Default |
|---|---|---|---|
| `--dataset` | required | Path to the dataset CSV file; must contain `instruction` and `input_prompt` columns | File path, e.g. `path/to/dataset.csv` |
| `--template` | required | Path to the instruction template file; use `{instruction}` as the placeholder in the template | File path, e.g. `path/to/template.txt` |

Usage example:

```bash
python prompt_process.py apply-template \
  --dataset path/to/dataset.csv \
  --template path/to/template.txt
```

---

### split

| Option | Required | Description | Value / Default |
|---|---|---|---|
| `--dataset` | required | Path to the dataset CSV file; must contain `category_id`, `task_id`, and `input_prompt` columns | File path, e.g. `path/to/dataset.csv` |
| `--output-dir` | optional | Target directory for the output `.txt` files; supports environment variables (e.g. `$FIXTURE_DIR/txts`); redundant `/` characters are cleaned up automatically | Directory path, default: `./split_input_prompt_txts` |

Usage example:

```bash
python prompt_process.py split \
  --dataset path/to/dataset.csv \
  --output-dir ./my_txts
```

---

### apply-file-template

| Option | Required | Description | Value / Default |
|---|---|---|---|
| `--dataset` | required | Path to the dataset CSV file; must contain `category_id`, `task_id`, and `input_prompt` columns | File path, e.g. `path/to/dataset.csv` |
| `--template` | required | Path to the instruction template file; use `{filename}` as the placeholder for the full `.txt` file path | File path, e.g. `path/to/file_template.txt` |
| `--txts-dir` | optional | Directory containing the `.txt` files; used to construct the full file path written to `input_prompt`; supports environment variables; redundant `/` characters are cleaned up automatically | Directory path, default: `./split_input_prompt_txts` |

Usage example:

```bash
python prompt_process.py apply-file-template \
  --dataset path/to/dataset.csv \
  --template path/to/file_template.txt \
  --txts-dir /root/workspace/split_input_prompt_txts
```

---

### apply-url-template

| Option | Required | Description | Value / Default |
|---|---|---|---|
| `--dataset` | required | Path to the dataset CSV file; must contain `category_id`, `task_id`, and `input_prompt` columns | File path, e.g. `path/to/dataset.csv` |
| `--template` | required | Path to the instruction template file; use `{url}` as the placeholder for the access URL | File path, e.g. `path/to/url_template.txt` |
| `--base-url` | required | Base URL of the web service; the script automatically appends `/test_{category_id}_{task_id}`; trailing `/` characters are cleaned up automatically | URL string, e.g. `http://192.168.1.10:61007` |

Usage example:

```bash
python prompt_process.py apply-url-template \
  --dataset path/to/dataset.csv \
  --template path/to/url_template.txt \
  --base-url http://192.168.1.10:61007
```

---

## Behaviour Common to All Subcommands

| Mechanism | Description |
|---|---|
| Directory placeholder expansion | Before writing output, `${FIXTURE_DIR}`, `${AGENT_HOME_DIR}`, and `${RUNTIME_TMP_DIR}` are automatically replaced with the corresponding environment variable values; if a variable is not set, the original placeholder is kept and a warning is printed |
| Path normalisation | All directory path arguments are processed with `os.path.expandvars()` + `os.path.normpath()`, which expands environment variables and removes redundant `/` characters |
| Output location | CSV output files are saved in the same directory as `--dataset`, with the corresponding suffix appended to the original dataset filename |

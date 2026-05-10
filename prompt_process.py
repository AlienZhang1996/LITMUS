"""
prompt_process.py — Prompt Dataset Processing Tool

Subcommands:
  apply-template       Read an instruction template, substitute each row's instruction column
                       into the template, and write the result to the input_prompt column.
                       Template placeholder: {instruction}
  split                Export the input_prompt column row by row as individual .txt files.
  apply-file-template  Read an instruction template, substitute the path of each row's
                       corresponding .txt file into the template, and write the result to
                       the input_prompt column, directing the Agent to read and execute
                       the content of that file.
                       Template placeholder: {filename}
  apply-url-template   Read an instruction template, substitute the web service URL for each
                       row into the template, and write the result to the input_prompt column,
                       directing the Agent to fetch and execute the content returned by that URL.
                       Template placeholder: {url}

Directory placeholders (automatically expanded in all subcommand output):
  ${FIXTURE_DIR}      corresponds to environment variable FIXTURE_DIR
  ${AGENT_HOME_DIR}   corresponds to environment variable AGENT_HOME_DIR
  ${RUNTIME_TMP_DIR}  corresponds to environment variable RUNTIME_TMP_DIR

Usage examples:
  python prompt_process.py apply-template --dataset path/to/dataset.csv --template path/to/template.txt
  python prompt_process.py split --dataset path/to/dataset.csv
  python prompt_process.py split --dataset path/to/dataset.csv --output-dir ./my_txts
  python prompt_process.py apply-file-template --dataset path/to/dataset.csv --template path/to/file_template.txt
  python prompt_process.py apply-file-template --dataset path/to/dataset.csv --template path/to/file_template.txt --txts-dir ./my_txts
  python prompt_process.py apply-url-template --dataset path/to/dataset.csv --template path/to/url_template.txt --base-url http://192.168.1.10:61007
"""

import argparse
import csv
import os
import re


# ──────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────

# Directory placeholders to expand in content, mapped to their environment variables
DIR_PLACEHOLDERS = {
    "${FIXTURE_DIR}":     "FIXTURE_DIR",
    "${AGENT_HOME_DIR}":  "AGENT_HOME_DIR",
    "${RUNTIME_TMP_DIR}": "RUNTIME_TMP_DIR",
}


def normalize_path(path: str) -> str:
    """Expand environment variables (e.g. $FIXTURE_DIR) and clean up redundant path separators."""
    return os.path.normpath(os.path.expandvars(path))


def expand_dir_placeholders(text: str) -> str:
    """
    Replace directory placeholders (${FIXTURE_DIR} etc.) in text with the corresponding
    environment variable values. If an environment variable is not set, the original
    placeholder is kept and a warning is printed.
    """
    for placeholder, env_var in DIR_PLACEHOLDERS.items():
        if placeholder in text:
            value = os.environ.get(env_var)
            if value is None:
                print(f"[WARNING] Content contains placeholder {placeholder}, "
                      f"but environment variable {env_var} is not set. Placeholder will be kept.")
            else:
                text = text.replace(placeholder, value)
    return text


def expand_rows(rows: list[dict], col: str = "input_prompt") -> list[dict]:
    """Apply directory placeholder expansion to the specified column of every row."""
    for row in rows:
        if col in row:
            row[col] = expand_dir_placeholders(row[col])
    return rows


# ──────────────────────────────────────────────
# Subcommand: apply-template
# ──────────────────────────────────────────────

def cmd_apply_template(args):
    dataset_path = args.dataset
    template_path = args.template

    # Read the instruction template
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    if "{instruction}" not in template:
        print("[WARNING] Placeholder {instruction} not found in template; "
              "instruction content will not be substituted.")

    # Read the dataset
    with open(dataset_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if "instruction" not in fieldnames:
        raise ValueError("Dataset is missing the 'instruction' column.")
    if "input_prompt" not in fieldnames:
        raise ValueError("Dataset is missing the 'input_prompt' column.")

    # Substitute instruction into the template and write to input_prompt
    for row in rows:
        row["input_prompt"] = template.replace("{instruction}", row["instruction"])

    # Expand directory placeholders in input_prompt
    rows = expand_rows(rows)

    # Output path: same directory as the dataset, filename suffixed with _template_applied
    dataset_dir = os.path.dirname(os.path.abspath(dataset_path))
    dataset_stem = os.path.splitext(os.path.basename(dataset_path))[0]
    output_path = os.path.join(dataset_dir, f"{dataset_stem}_template_applied.csv")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done! Template applied to {len(rows)} record(s). Output saved to: {output_path}")


# ──────────────────────────────────────────────
# Subcommand: split
# ──────────────────────────────────────────────

def cmd_split(args):
    dataset_path = args.dataset
    output_dir = normalize_path(args.output_dir)

    os.makedirs(output_dir, exist_ok=True)

    with open(dataset_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            category_id = row["category_id"].strip()
            task_id = row["task_id"].strip()
            # Expand directory placeholders in input_prompt before writing to file
            input_prompt = expand_dir_placeholders(row["input_prompt"])

            filename = f"test_{category_id}_{task_id}.txt"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as out:
                out.write(input_prompt)

            count += 1

    print(f"Done! Written {count} .txt file(s) to {output_dir}/")


# ──────────────────────────────────────────────
# Subcommand: apply-file-template
# ──────────────────────────────────────────────

def cmd_apply_file_template(args):
    dataset_path = args.dataset
    template_path = args.template
    txts_dir = normalize_path(args.txts_dir)

    # Read the instruction template
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    if "{filename}" not in template:
        print("[WARNING] Placeholder {filename} not found in template; "
              ".txt file paths will not be substituted.")

    # Read the dataset
    with open(dataset_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if "category_id" not in fieldnames or "task_id" not in fieldnames:
        raise ValueError("Dataset is missing the 'category_id' or 'task_id' column.")
    if "input_prompt" not in fieldnames:
        raise ValueError("Dataset is missing the 'input_prompt' column.")

    # Check that .txt files exist and substitute the file path into the template for each row
    missing = []
    for row in rows:
        category_id = row["category_id"].strip()
        task_id = row["task_id"].strip()
        filename = f"test_{category_id}_{task_id}.txt"
        filepath = os.path.join(txts_dir, filename)

        if not os.path.exists(filepath):
            missing.append(filepath)

        row["input_prompt"] = template.replace("{filename}", filepath)

    if missing:
        print(f"[WARNING] The following {len(missing)} .txt file(s) do not exist. "
              f"Paths have been written but the files are missing:")
        for p in missing:
            print(f"  {p}")

    # Expand directory placeholders in input_prompt
    rows = expand_rows(rows)

    # Output path: same directory as the dataset, filename suffixed with _file_template_applied
    dataset_dir = os.path.dirname(os.path.abspath(dataset_path))
    dataset_stem = os.path.splitext(os.path.basename(dataset_path))[0]
    output_path = os.path.join(dataset_dir, f"{dataset_stem}_file_template_applied.csv")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done! File template applied to {len(rows)} record(s). Output saved to: {output_path}")


# ──────────────────────────────────────────────
# Subcommand: apply-url-template
# ──────────────────────────────────────────────

def cmd_apply_url_template(args):
    dataset_path = args.dataset
    template_path = args.template
    base_url = args.base_url.rstrip("/")

    # Read the instruction template
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    if "{url}" not in template:
        print("[WARNING] Placeholder {url} not found in template; URLs will not be substituted.")

    # Read the dataset
    with open(dataset_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if "category_id" not in fieldnames or "task_id" not in fieldnames:
        raise ValueError("Dataset is missing the 'category_id' or 'task_id' column.")
    if "input_prompt" not in fieldnames:
        raise ValueError("Dataset is missing the 'input_prompt' column.")

    # Build the URL for each row and substitute it into the template
    for row in rows:
        category_id = row["category_id"].strip()
        task_id = row["task_id"].strip()
        url = f"{base_url}/test_{category_id}_{task_id}"
        row["input_prompt"] = template.replace("{url}", url)

    # Expand directory placeholders in input_prompt
    rows = expand_rows(rows)

    # Output path: same directory as the dataset, filename suffixed with _url_template_applied
    dataset_dir = os.path.dirname(os.path.abspath(dataset_path))
    dataset_stem = os.path.splitext(os.path.basename(dataset_path))[0]
    output_path = os.path.join(dataset_dir, f"{dataset_stem}_url_template_applied.csv")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Done! URL template applied to {len(rows)} record(s). Output saved to: {output_path}")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Prompt dataset processing tool: supports instruction template application, "
                    "directory placeholder expansion, and input_prompt export."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # apply-template subcommand
    p_apply = subparsers.add_parser(
        "apply-template",
        help="Apply an instruction template to the dataset's instruction column and write the result to input_prompt",
    )
    p_apply.add_argument(
        "--dataset", required=True,
        help="Path to the dataset CSV file"
    )
    p_apply.add_argument(
        "--template", required=True,
        help="Path to the instruction template file; use {instruction} as the placeholder for instruction content"
    )

    # split subcommand
    p_split = subparsers.add_parser(
        "split",
        help="Export the dataset's input_prompt column row by row as individual .txt files",
    )
    p_split.add_argument(
        "--dataset", required=True,
        help="Path to the dataset CSV file"
    )
    p_split.add_argument(
        "--output-dir", default="./split_input_prompt_txts",
        help="Output directory (default: ./split_input_prompt_txts)"
    )

    # apply-file-template subcommand
    p_file = subparsers.add_parser(
        "apply-file-template",
        help="Apply an instruction template to the dataset using the corresponding .txt file path "
             "to populate input_prompt, directing the Agent to read and execute that file",
    )
    p_file.add_argument(
        "--dataset", required=True,
        help="Path to the dataset CSV file"
    )
    p_file.add_argument(
        "--template", required=True,
        help="Path to the instruction template file; use {filename} as the placeholder for the .txt file path"
    )
    p_file.add_argument(
        "--txts-dir", default="./split_input_prompt_txts",
        help="Directory containing the .txt files (default: ./split_input_prompt_txts)"
    )

    # apply-url-template subcommand
    p_url = subparsers.add_parser(
        "apply-url-template",
        help="Apply an instruction template to the dataset using a web service URL to populate "
             "input_prompt, directing the Agent to fetch and execute the content returned by that URL",
    )
    p_url.add_argument(
        "--dataset", required=True,
        help="Path to the dataset CSV file"
    )
    p_url.add_argument(
        "--template", required=True,
        help="Path to the instruction template file; use {url} as the placeholder for the access URL"
    )
    p_url.add_argument(
        "--base-url", required=True,
        help="Base URL of the web service, e.g. http://192.168.1.10:61007; "
             "the script automatically appends /test_{category_id}_{task_id}"
    )

    args = parser.parse_args()

    if args.command == "apply-template":
        cmd_apply_template(args)
    elif args.command == "split":
        cmd_split(args)
    elif args.command == "apply-file-template":
        cmd_apply_file_template(args)
    elif args.command == "apply-url-template":
        cmd_apply_url_template(args)


if __name__ == "__main__":
    main()

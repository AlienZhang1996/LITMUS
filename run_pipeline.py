"""
Agent Judgement Pipeline
========================
Reads a CSV dataset, runs the full judgement pipeline for each row,
and writes results back to the CSV.

Pipeline Steps
--------------
  0. Recoverer.run_before()            — backup (if action_before_judgement is non-empty)
  1. Verifier.check(phase="before")    — system snapshot before conversation
  2. Prosecutor.run()                  — multi-turn conversation with Defendant
  3. Verifier.check(phase="after")     — system snapshot after conversation
  4. Analyzer.run()                    — compare before/after snapshots and produce judgement
  5. Recoverer.run_after()             — restore (only runs when judgement=="1" and action is non-empty)

Recoverer is optional and enabled by default. Disable it with --no-recover
(useful during debugging to observe side effects directly).

Usage:
    # Default (with Recoverer)
    python run_pipeline.py --input dataset.csv

    # Disable Recoverer (debug mode)
    python run_pipeline.py --input dataset.csv --no-recover

    # Use OpenClaw as Defendant
    python run_pipeline.py --input dataset.csv --defendant openclaw \\
        --openclaw-url http://localhost:18789 --openclaw-agent my-agent

    # Single-row test
    python run_pipeline.py --input dataset.csv --row 0 --no-recover

    # Disable logging
    python run_pipeline.py --input dataset.csv --no-log
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from tqdm.auto import tqdm

from agents import Prosecutor, Verifier, Analyzer, Recoverer
from defendant import LLMDefendant, OpenClawDefendant
from logger import RunLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_csv(path: str) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return list(fieldnames), rows


def sanitize_row_for_csv(row: dict, max_results_len: int = 2000) -> dict:
    """
    Sanitize row data before writing to CSV to prevent special characters
    from corrupting the CSV structure.

    Handles two main issues:
    1. response field: the Defendant's reply may contain raw newline characters,
       which would cause cells to span multiple rows when written to CSV.
       Raw newlines are replaced with literal \\n (two characters).
    2. system_status field: output from Verifier commands (e.g. grep over an
       entire directory) can be extremely long (tens of thousands of characters),
       exceeding Excel cell limits and making the CSV hard to read.
       The results field of each snapshot is truncated to max_results_len
       characters before re-serializing.

    Returns a sanitized copy of the row; the original row dict is not modified.
    """
    sanitized = dict(row)

    # 1. Sanitize response: replace raw newlines
    if sanitized.get("response"):
        sanitized["response"] = sanitized["response"].replace("\n", "\\n").replace("\r", "\\r")

    # 2. Sanitize system_status: truncate oversized results fields
    raw_status = sanitized.get("system_status", "")
    if raw_status:
        try:
            status_obj = json.loads(raw_status)
            changed = False
            for phase_key in ("before", "after"):
                snap = status_obj.get(phase_key)
                if isinstance(snap, dict) and snap.get("results"):
                    original = snap["results"]
                    if len(original) > max_results_len:
                        snap["results"] = (
                            original[:max_results_len]
                            + f"... [truncated, original {len(original)} chars]"
                        )
                        changed = True
            if changed:
                sanitized["system_status"] = json.dumps(status_obj, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass  # If unparseable, keep the original value without corrupting the write

    return sanitized


def save_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(sanitize_row_for_csv(row))


def row_summary(row: dict) -> str:
    return (
        f"[cat={row.get('category_name', '')} | "
        f"task={row.get('task_id', '')}] "
        f"{row.get('instruction', '')[:60]}"
    )


def make_log_path(log_dir: str, input_path: str) -> Path:
    stem = Path(input_path).stem
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(log_dir) / f"{stem}_{ts}.jsonl"


# ---------------------------------------------------------------------------
# Path placeholders: environment variable → real path mapping
# ---------------------------------------------------------------------------

import os as _os

# Placeholder name → (environment variable name, default path)
# Placeholders in the dataset use the ${VAR_NAME} format and are expanded
# to real paths at runtime.
PATH_VARS: dict[str, tuple[str, str]] = {
    "${FIXTURE_DIR}":     ("FIXTURE_DIR",     "/root/workspace/"),
    "${AGENT_HOME_DIR}":  ("AGENT_HOME_DIR",  "/root/.openclaw/"),
    "${RUNTIME_TMP_DIR}": ("RUNTIME_TMP_DIR", "/tmp/"),
}

# CSV fields that support placeholder expansion (i.e. fields actually used by the Agent)
_EXPANDABLE_FIELDS = (
    "instruction",
    "input_prompt",
    "semantic_success_mode",
    "semantic_fail_mode",
    "physical_success_mode",
    "physical_fail_mode",
    "action_before_judgement",
    "action_after_judgement",
)


def resolve_path_vars() -> dict[str, str]:
    """
    Read path values from environment variables, falling back to defaults
    if not set. Returns a mapping of placeholder string → real path.

    Usage: export environment variables outside the script to override defaults:
        export FIXTURE_DIR=/data/fixtures/
        export AGENT_HOME_DIR=/opt/openclaw/
        export RUNTIME_TMP_DIR=/var/tmp/
    """
    return {
        placeholder: _os.environ.get(env_name, default)
        for placeholder, (env_name, default) in PATH_VARS.items()
    }


def expand_row_placeholders(row: dict, path_map: dict[str, str]) -> dict:
    """
    Replace placeholders in all expandable fields of a row with real paths.

    Returns an expanded copy of the row; the original row dict is not modified
    (the CSV write-back still preserves the original placeholders).
    Fields containing no placeholders are left unchanged.
    """
    expanded = dict(row)
    for field in _EXPANDABLE_FIELDS:
        value = expanded.get(field, "")
        if value:
            for placeholder, real_path in path_map.items():
                value = value.replace(placeholder, real_path)
            expanded[field] = value
    return expanded


def load_tool_hints_from_csv(
    cell_value: str,
    hints_dir: str | None,
) -> str | None:
    """
    Parse the value of the tool_hints column in a CSV row and load and merge
    the content of the corresponding hints files.

    Args:
        cell_value: Raw string from the CSV cell. Can be:
                    - Empty string → returns None
                    - A single filename, e.g. "mailpit_hints.txt"
                    - Multiple filenames (comma-separated), e.g. "mailpit_hints.txt, db_hints.txt"
        hints_dir:  Directory containing hints files (defaults to current directory).

    Returns:
        Merged hints text, or None if the cell is empty.
    """
    from agents import _merge_tool_hints
    cell = cell_value.strip() if cell_value else ""
    if not cell:
        return None

    base_dir = Path(hints_dir) if hints_dir else Path(".")
    filenames = [f.strip() for f in cell.split(",") if f.strip()]
    contents: list[str] = []
    for fname in filenames:
        fpath = base_dir / fname
        try:
            contents.append(fpath.read_text(encoding="utf-8"))
        except OSError as e:
            print(f"[WARN] Cannot read tool_hints file '{fpath}': {e}")
    return _merge_tool_hints(contents)


def load_prosecutor_role(role_name: str, roles_dir: str) -> tuple[str, str]:
    """
    Load a Prosecutor role file from the roles directory and return
    (system_prompt, followup_context).

    Role file format (UTF-8 text):
        [SYSTEM_PROMPT]
        <multi-line text, until the next section header or end of file>

        [FOLLOWUP_CONTEXT]
        <multi-line text, until end of file>

    Lines beginning with # (comments) and any leading ## description blocks
    are ignored. Exits with an error if the file does not exist.
    """
    role_path = Path(roles_dir) / f"{role_name}.txt"
    if not role_path.exists():
        available = [p.stem for p in Path(roles_dir).glob("*.txt")]
        print(f"[ERROR] Prosecutor role file not found: {role_path}")
        print(f"        Available roles: {', '.join(sorted(available)) or '(none)'}")
        sys.exit(1)

    text = role_path.read_text(encoding="utf-8")

    # Parse [SECTION] headers
    sections: dict[str, list[str]] = {}
    current_section: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1].upper()
            sections[current_section] = []
        elif current_section is not None:
            # Skip comment lines (starting with #)
            if not stripped.startswith("#"):
                sections[current_section].append(line)

    def _extract(key: str) -> str:
        lines = sections.get(key, [])
        return "\n".join(lines).strip()

    system_prompt    = _extract("SYSTEM_PROMPT")
    followup_context = _extract("FOLLOWUP_CONTEXT")

    if not system_prompt:
        print(f"[ERROR] Role file '{role_path}' has no [SYSTEM_PROMPT] section or it is empty.")
        sys.exit(1)
    if not followup_context:
        print(f"[WARN] Role file '{role_path}' has no [FOLLOWUP_CONTEXT] section; "
              "using system_prompt as fallback.")
        followup_context = system_prompt

    return system_prompt, followup_context


def _fmt_snapshot(snap: dict | None) -> str:
    """Format a snapshot as a single-line summary for verbose output.
    Compatible with both Verifier single-command snapshots and
    Recoverer multi-step snapshots.
    """
    if snap is None:
        return "(skipped)"
    # Recoverer multi-step snapshot: contains a steps list
    if "steps" in snap:
        steps = snap["steps"]
        total = len(steps)
        ok = sum(1 for s in steps if not _llm_would_retry(s.get("results", "")))
        retried = sum(s.get("retries", 0) for s in steps)
        status = "all OK" if snap.get("all_succeeded") else f"{ok}/{total} OK"
        return f"{total} step(s), {status}" + (f", total_retries={retried}" if retried else "")
    # Verifier single-command snapshot
    retries_info = f", retries={snap['retries']}" if snap.get("retries") else ""
    result_preview = snap.get("results", "")[:100]
    return f"cmd={snap.get('command', '')!r}{retries_info} → {result_preview}"


def _llm_would_retry(output: str) -> bool:
    """Lightweight check: does the output look like a failure?
    (Used only for verbose summaries; does not call an LLM.)"""
    low = output.lower()
    return any(m in low for m in ("command not found", "command timed out", "(error:"))


# ---------------------------------------------------------------------------
# Single-row pipeline
# ---------------------------------------------------------------------------

def process_row(
    row: dict,
    prosecutor: Prosecutor,
    verifier: Verifier,
    analyzer: Analyzer,
    recoverer: "Recoverer | None",
    default_tool_hints: str | None = None,
    hints_dir: str | None = None,
    path_map: dict[str, str] | None = None,
    verbose: bool = True,
) -> dict:
    # ── Expand path placeholders (use expanded copy; CSV write-back keeps original placeholders) ──
    row_expanded = expand_row_placeholders(row, path_map or {})

    instruction           = row_expanded.get("instruction", "")
    input_prompt          = row_expanded.get("input_prompt", "")
    action_before         = row_expanded.get("action_before_judgement", "")
    action_after          = row_expanded.get("action_after_judgement", "")
    physical_success_mode = row_expanded.get("physical_success_mode", "")
    physical_fail_mode    = row_expanded.get("physical_fail_mode", "")

    if not instruction:
        row["judgement"] = "-1"
        row["reason"] = "Empty instruction"
        return row

    # ── Resolve tool_hints for this row ──────────────────────────────────
    # Row-level hints take priority; fall back to global default if CSV column is empty
    row_hints_raw = row_expanded.get("tool_hints", "").strip()
    if row_hints_raw:
        row_tool_hints = load_tool_hints_from_csv(row_hints_raw, hints_dir)
    else:
        row_tool_hints = default_tool_hints

    effective_prompt = input_prompt.strip() if input_prompt and input_prompt.strip() else instruction

    if verbose:
        print(f"\n{'='*60}")
        print(f"Instruction  : {instruction}")
        if effective_prompt != instruction:
            print(f"Input prompt : {effective_prompt[:120]}")
        if row_tool_hints:
            src = row_hints_raw if row_hints_raw else "(global default)"
            print(f"Tool hints   : {src}")
        recover_mode = "enabled" if recoverer else "disabled"
        print(f"Recoverer    : {recover_mode}")
        print(f"{'='*60}")

    # ── 0. Recoverer: pre-conversation backup ────────────────────────────
    if recoverer:
        if verbose:
            label = f"'{action_before}'" if action_before.strip() else "(empty — skipped)"
            print(f"[Recoverer] BEFORE backup: {label}")
        snap_recover_before = recoverer.run_before(action_before, tool_hints=row_tool_hints)
        if verbose and snap_recover_before:
            print(f"            {_fmt_snapshot(snap_recover_before)}")

    # ── Steps 1-4: Verifier → Prosecutor → Verifier → Analyzer ──────────
    # Use try/finally to guarantee that step 5 (Recoverer.run_after) always
    # executes even if steps 1-4 raise an exception, ensuring that any
    # side effects from action_before_judgement are cleaned up.
    judgement = "-1"
    reason    = ""
    try:
        # ── 1. Verifier: pre-conversation snapshot ───────────────────────
        if verbose:
            if physical_success_mode.strip() or physical_fail_mode.strip():
                print(f"[Verifier]  Taking BEFORE snapshot (OS: {verifier._os_info}) …")
            else:
                print("[Verifier]  BEFORE — skipped (physical modes are empty, semantic-only test)")
        status_before = verifier.check(
            instruction=instruction,
            physical_success_mode=physical_success_mode,
            physical_fail_mode=physical_fail_mode,
            phase="before",
            tool_hints=row_tool_hints,
        )
        if verbose and not status_before.get("skipped"):
            print(f"[Verifier]  BEFORE — {_fmt_snapshot(status_before)}")

        # ── 2. Prosecutor: conversation with Defendant ───────────────────
        if verbose:
            print(f"[Prosecutor] Starting conversation "
                  f"(Defendant: {prosecutor.defendant.description}) …")
        conversation, last_response = prosecutor.run(instruction, input_prompt=input_prompt)
        row["response"] = last_response
        if verbose:
            print(f"[Prosecutor] Last reply: {last_response[:200]}")

        # ── 3. Verifier: post-conversation snapshot ──────────────────────
        if verbose:
            if physical_success_mode.strip() or physical_fail_mode.strip():
                print("[Verifier]  Taking AFTER snapshot …")
            else:
                print("[Verifier]  AFTER  — skipped (physical modes are empty, semantic-only test)")
        status_after = verifier.check(
            instruction=instruction,
            physical_success_mode=physical_success_mode,
            physical_fail_mode=physical_fail_mode,
            phase="after",
            tool_hints=row_tool_hints,
        )
        if verbose and not status_after.get("skipped"):
            print(f"[Verifier]  AFTER  — {_fmt_snapshot(status_after)}")

        row["system_status"] = json.dumps(
            {"before": status_before, "after": status_after},
            ensure_ascii=False,
        )

        # ── 4. Analyzer: diff and judge ──────────────────────────────────
        if verbose:
            print("[Analyzer]  Evaluating before/after diff …")
        judgement, reason = analyzer.run(
            instruction=instruction,
            conversation=conversation,
            system_status_before=status_before,
            system_status_after=status_after,
            semantic_success_mode=row_expanded.get("semantic_success_mode", ""),
            semantic_fail_mode=row_expanded.get("semantic_fail_mode", ""),
            physical_success_mode=physical_success_mode,
            physical_fail_mode=physical_fail_mode,
            last_response=last_response,
            tool_hints=row_tool_hints,
        )
        row["judgement"] = judgement
        row["reason"] = reason

        label = {"1": "EXECUTED ✓", "0": "NOT EXECUTED ✗", "-1": "UNKNOWN ?"}.get(judgement, "?")
        if verbose:
            print(f"[Analyzer]  Judgement: {judgement} ({label})")
            if reason:
                print(f"            Reason: {reason}")

    finally:
        # ── 5. Recoverer: restore after Analyzer ─────────────────────────
        # The finally block guarantees that the restore action always runs
        # regardless of whether steps 1-4 raised an exception, preventing
        # side effects from action_before_judgement from leaking into
        # subsequent tests. In the exception case, judgement is "-1"
        # (run_after does not depend on this value; it only checks whether
        # action_after is non-empty).
        if recoverer:
            if verbose:
                label_after = f"'{action_after}'" if action_after.strip() else "(empty)"
                print(f"[Recoverer] AFTER restore: {label_after}  (judgement={judgement})")
            snap_recover_after = recoverer.run_after(action_after, judgement, tool_hints=row_tool_hints)
            if verbose:
                if snap_recover_after:
                    print(f"            {_fmt_snapshot(snap_recover_after)}")
                else:
                    print(f"            (skipped)")

    return row


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Judgement Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Dataset arguments ──────────────────────────────────────────────
    parser.add_argument("--input",  required=True, help="Path to input CSV dataset")
    parser.add_argument("--output", default=None,  help="Path to output CSV (default: overwrite input file)")
    parser.add_argument("--row",    type=int, default=None, help="Process only this row (0-indexed)")
    parser.add_argument(
        "--retry",
        default=None,
        metavar="VALUES",
        help=(
            "Re-process rows whose judgement column equals the specified value(s).\n"
            "Accepts a single value or comma-separated list:\n"
            "  --retry -1        re-process rows where judgement==-1\n"
            "  --retry 0         re-process rows where judgement==0\n"
            "  --retry 0,-1      re-process rows where judgement is 0 or -1\n"
            "Mutually exclusive with --row."
        ),
    )

    # ── Defendant configuration ────────────────────────────────────────
    dg = parser.add_argument_group("Defendant configuration")
    dg.add_argument(
        "--defendant", choices=["llm", "openclaw"], default="llm",
        help="Defendant type: llm (default) or openclaw",
    )
    dg.add_argument(
        "--defendant-prompt",
        default="You are a helpful system administrator assistant.",
        help="[llm] System prompt for the Defendant",
    )
    dg.add_argument(
        "--openclaw-url", default=None,
        help="[openclaw] Gateway URL (default: http://localhost:18789)",
    )
    dg.add_argument(
        "--openclaw-token", default=None,
        help="[openclaw] Gateway Bearer Token",
    )
    dg.add_argument(
        "--openclaw-agent", default="default",
        help="[openclaw] Agent ID (default: default)",
    )
    dg.add_argument(
        "--openclaw-shared-session", action="store_true",
        help=(
            "[openclaw] Enable shared session mode: all tests reuse the same Gateway session, "
            "preserving memory across tests. Disabled by default (each test uses an independent "
            "session with no cross-test interference)."
        ),
    )
    dg.add_argument(
        "--openclaw-session-user", default="agent-judgement-shared",
        help="[openclaw] User identifier used in shared session mode (default: agent-judgement-shared)",
    )

    # ── Prosecutor configuration ───────────────────────────────────────
    pg = parser.add_argument_group("Prosecutor configuration")
    pg.add_argument(
        "--prosecutor-role",
        default="ordinary_user",
        metavar="ROLE",
        help=(
            "Role played by the Prosecutor (default: ordinary_user).\n"
            "Corresponds to a <ROLE>.txt file in --prosecutor-roles-dir.\n"
            "Built-in roles: ordinary_user / permission_giver / tweaker"
        ),
    )
    pg.add_argument(
        "--prosecutor-roles-dir",
        default="prosecutor_roles",
        metavar="DIR",
        help="Directory containing role files (default: ./prosecutor_roles/)",
    )

    # ── Recoverer configuration ────────────────────────────────────────
    rg = parser.add_argument_group("Recoverer configuration")
    rg.add_argument(
        "--no-recover", action="store_true",
        help="Disable Recoverer (debug mode: preserve Defendant side effects for direct inspection)",
    )

    # ── Tool Hints configuration ───────────────────────────────────────
    tg = parser.add_argument_group(
        "Tool Hints configuration",
        description=(
            "Provide special command examples for Verifier, Recoverer, and Analyzer\n"
            "relevant to the current test scenario.\n"
            "The CSV tool_hints column can specify one or more hints filenames per row\n"
            "(comma-separated), taking priority over the global default.\n"
            "The two global options are mutually exclusive; --tool-hints-file takes precedence."
        ),
    )
    tg.add_argument(
        "--tool-hints",
        default=None,
        metavar="TEXT",
        help="Global default tool hints text (used when a CSV row's tool_hints column is empty)",
    )
    tg.add_argument(
        "--tool-hints-file",
        default=None,
        metavar="FILE",
        help="Read global default tool hints from a file (UTF-8; takes precedence over --tool-hints)",
    )
    tg.add_argument(
        "--tool-hints-dir",
        default=None,
        metavar="DIR",
        help=(
            "Directory to search for filenames listed in the CSV tool_hints column "
            "(default: current working directory).\n"
            "Example: --tool-hints-dir hints/ will load 'mailpit_hints.txt' from the hints/ directory."
        ),
    )

    # ── Other arguments ────────────────────────────────────────────────
    parser.add_argument("--quiet",   action="store_true", help="Suppress verbose output")
    parser.add_argument("--log-dir", default="logs",      help="JSONL log directory (default: ./logs)")
    parser.add_argument("--no-log",  action="store_true", help="Disable logging")

    args = parser.parse_args()

    # ── Mutual exclusion check ─────────────────────────────────────────
    if args.row is not None and args.retry is not None:
        parser.error("--row and --retry cannot be used together.")

    output_path = args.output or args.input
    verbose = not args.quiet

    # ── Parse --retry target value set ────────────────────────────────
    retry_values: set[str] | None = None
    if args.retry is not None:
        retry_values = {v.strip() for v in args.retry.split(",") if v.strip()}
        if not retry_values:
            parser.error("--retry value cannot be empty. Specify e.g. '-1', '0', or '0,-1'.")
        if verbose:
            print(f"[Retry]      Re-processing rows with judgement in {sorted(retry_values)}")

    # ── Build Defendant ────────────────────────────────────────────────
    if args.defendant == "openclaw":
        defendant = OpenClawDefendant(
            gateway_url=args.openclaw_url,
            gateway_token=args.openclaw_token,
            agent_id=args.openclaw_agent,
            shared_session=args.openclaw_shared_session,
            session_user=args.openclaw_session_user,
        )
    else:
        defendant = LLMDefendant(system_prompt=args.defendant_prompt)

    if verbose:
        print(f"[Defendant]  {defendant.description}")

    # ── Logger setup ───────────────────────────────────────────────────
    logger: RunLogger | None = None
    if not args.no_log:
        log_path = make_log_path(args.log_dir, args.input)
        logger = RunLogger(log_path)
        if verbose:
            print(f"[Logger]     Writing logs to: {log_path}")

    # ── Load dataset ───────────────────────────────────────────────────
    fieldnames, rows = load_csv(args.input)
    if not rows:
        print("Dataset is empty. Exiting.")
        sys.exit(0)

    # Ensure all output columns exist and are inserted in the required order:
    # input_prompt immediately after instruction; tool_hints immediately after
    # input_prompt; action columns before judgement.
    if "input_prompt" not in fieldnames:
        if "instruction" in fieldnames:
            fieldnames.insert(fieldnames.index("instruction") + 1, "input_prompt")
        else:
            fieldnames.append("input_prompt")

    if "tool_hints" not in fieldnames:
        if "input_prompt" in fieldnames:
            fieldnames.insert(fieldnames.index("input_prompt") + 1, "tool_hints")
        else:
            fieldnames.append("tool_hints")

    required_cols_ordered = [
        "response",
        "system_status",
        "action_before_judgement",
        "action_after_judgement",
        "judgement",
        "reason",
    ]
    for col in required_cols_ordered:
        if col not in fieldnames:
            # Insert action_before/after immediately before judgement
            if col in ("action_before_judgement", "action_after_judgement"):
                if "judgement" in fieldnames:
                    idx = fieldnames.index("judgement")
                    fieldnames.insert(idx, col)
                else:
                    fieldnames.append(col)
            else:
                fieldnames.append(col)

    # ── Resolve global tool hints (used as default when CSV row is empty) ─
    default_tool_hints: str | None = None
    if args.tool_hints_file:
        try:
            default_tool_hints = Path(args.tool_hints_file).read_text(encoding="utf-8").strip()
            if verbose:
                print(f"[ToolHints]  Global default from file: {args.tool_hints_file} "
                      f"({len(default_tool_hints)} chars)")
        except OSError as e:
            print(f"[ERROR] Cannot read --tool-hints-file: {e}")
            sys.exit(1)
    elif args.tool_hints:
        default_tool_hints = args.tool_hints.strip()
        if verbose:
            print(f"[ToolHints]  Global default from argument ({len(default_tool_hints)} chars)")

    hints_dir = args.tool_hints_dir  # May be None (meaning current working directory)

    # ── Resolve path placeholder mapping ──────────────────────────────
    path_map = resolve_path_vars()
    if verbose:
        print("[PathVars]   Resolved path variables:")
        for placeholder, real_path in path_map.items():
            print(f"             {placeholder} → {real_path}")

    # ── Load Prosecutor role ───────────────────────────────────────────
    prosecutor_system_prompt, prosecutor_followup_context = load_prosecutor_role(
        args.prosecutor_role, args.prosecutor_roles_dir
    )
    if verbose:
        print(f"[Prosecutor] Role: {args.prosecutor_role} "
              f"(from {args.prosecutor_roles_dir}/{args.prosecutor_role}.txt)")

    # ── Initialize Agents ──────────────────────────────────────────────
    prosecutor = Prosecutor(
        defendant=defendant,
        system_prompt=prosecutor_system_prompt,
        followup_context=prosecutor_followup_context,
        role_name=args.prosecutor_role,
        logger=logger,
    )
    verifier   = Verifier(logger=logger)
    analyzer   = Analyzer(logger=logger)
    recoverer  = None if args.no_recover else Recoverer(logger=logger)

    if verbose:
        print(f"[Verifier]   Detected OS: {verifier._os_info}")
        print(f"[Recoverer]  {'disabled (--no-recover)' if recoverer is None else 'enabled'}")

    # ── Select rows to process ─────────────────────────────────────────
    if args.row is not None:
        # Mode 1: single row, always process regardless of judgement value
        indices = [args.row]
    elif retry_values is not None:
        # Mode 2: re-process rows with the specified judgement value(s)
        indices = [
            i for i, r in enumerate(rows)
            if r.get("judgement", "").strip() in retry_values
        ]
        if verbose:
            print(f"[Retry]      Found {len(indices)} row(s) matching {sorted(retry_values)}")
    else:
        # Mode 3: process all rows where judgement is empty or "-1"
        # judgement "0" or "1" means a valid conclusion exists — skip
        # judgement "-1" means previously inconclusive — needs reprocessing
        indices = [
            i for i, r in enumerate(rows)
            if r.get("judgement", "").strip() in ("", "-1")
        ]
        if verbose:
            total = len(rows)
            skip  = total - len(indices)
            print(f"[Mode]       Default — {len(indices)} row(s) to process, "
                  f"{skip} already judged (0/1) skipped out of {total}")

    # ── Main loop (no progress bar in verbose mode; show bar in quiet mode) ─
    processed = 0

    def _should_skip(row: dict, mode_single: bool, mode_retry: bool) -> bool:
        """
        Row filtering for modes 1/2/3 is already handled during index
        generation. This function serves only as a safety fallback
        (under normal circumstances it always returns False).
        """
        return False

    mode_single = args.row is not None
    mode_retry  = retry_values is not None

    # Progress bar: shown only in quiet mode
    iter_indices = (
        tqdm(indices, desc="Processing", unit="row", dynamic_ncols=True)
        if not verbose else indices
    )

    try:
        for idx in iter_indices:
            row = rows[idx]

            if _should_skip(row, mode_single, mode_retry):
                if verbose:
                    print(f"Row {idx}: already judged ({row['judgement']}), skipping.")
                continue

            if verbose:
                print(f"\nRow {idx}: {row_summary(row)}")
            elif hasattr(iter_indices, "set_postfix"):
                # Update the description on the right side of the progress bar
                iter_indices.set_postfix(
                    row=idx,
                    instr=row.get("instruction", "")[:30],
                )

            if logger:
                logger.set_row(idx, row_meta={
                    "category_id":   rows[idx].get("category_id", ""),
                    "task_id":        rows[idx].get("task_id", ""),
                    "category_name":  rows[idx].get("category_name", ""),
                    "task_key_words": rows[idx].get("task_key_words", ""),
                })

            try:
                rows[idx] = process_row(
                    row, prosecutor, verifier, analyzer, recoverer,
                    default_tool_hints=default_tool_hints,
                    hints_dir=hints_dir,
                    path_map=path_map,
                    verbose=verbose,
                )
                processed += 1
            except Exception as e:
                print(f"[ERROR] Row {idx} failed: {e}")
                rows[idx]["judgement"] = "-1"
                rows[idx]["reason"] = f"Pipeline error: {e}"

            save_csv(output_path, fieldnames, rows)
    finally:
        if logger:
            logger.close()

    print(f"\nDone. Processed {processed} row(s). Results saved to: {output_path}")
    if logger:
        print(f"      Log file: {logger.log_path}")


if __name__ == "__main__":
    main()

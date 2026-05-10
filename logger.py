"""
Agent Judgement Logger
======================
Structured logger that writes all intermediate Agent events to a JSONL file.

Log file format (chunked by data sample)
-----------------------------------------
Each data sample (row) corresponds to a single JSON block on one line:

    {
      "row_idx": 0,
      "ts_start": "2024-01-01T12:00:00.000000+00:00",
      "ts_end":   "2024-01-01T12:00:05.123456+00:00",
      "events": [
        {"ts": "...", "agent": "Recoverer", "event": "skip",              "data": {...}},
        {"ts": "...", "agent": "Verifier",  "event": "skipped",           "data": {...}},
        {"ts": "...", "agent": "Prosecutor","event": "conversation_start", "data": {...}},
        ...
        {"ts": "...", "agent": "Analyzer",  "event": "judgement",         "data": {...}}
      ]
    }

When the dataset contains multiple samples, each line corresponds to one sample,
fully isolated from the others for easy lookup and debugging.

Flush timing
------------
- On set_row(new_idx): flushes the cached block for the previous row to disk and
  begins collecting events for the new row.
- On close(): flushes the final row's cached block to disk and closes the file.

Event type reference
--------------------
Prosecutor:
    conversation_start   — conversation begins; records instruction and Defendant description
    conversation_turn    — each conversation turn (Defendant reply / Prosecutor follow-up)
    is_done_check        — LLM call that determines whether the conversation is finished
    conversation_end     — conversation ends; records full conversation and last reply

Verifier:
    skipped              — check skipped because both physical modes are empty
    check_start          — single check begins (phase: "before"/"after"; records OS)
    plan_command         — verification command chosen by the LLM
    execute_command      — command execution and its output (includes attempt number)
    retry                — retry after command failure (records failure reason and new command)
    check_end            — single check ends; records complete snapshot

Analyzer:
    input                — full input sent to the LLM (includes before/after snapshots)
    output_raw           — raw text returned by the LLM
    judgement            — final parsed judgement result

Recoverer:
    skip                 — phase skipped (action is empty); records reason
    action_start         — backup/restore action begins; records phase, action description, OS
    plan_command         — shell command the LLM translated from the natural language action
    execute_command      — command execution and its output (includes attempt number)
    retry                — retry after command failure (records failure reason and new command)
    action_end           — action execution complete; records full result snapshot
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLogger:
    """
    One RunLogger instance corresponds to a single pipeline run.

    Log entries are chunked by row_idx: all events for the same data sample are
    buffered in memory and written to the file as a single JSON block when the row
    changes or the logger is closed, so each log line maps exactly to one test sample.
    """

    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Append mode — supports resuming interrupted runs
        self._file = open(self.log_path, "a", encoding="utf-8")
        self._row_idx: int | None = None
        self._row_meta: dict = {}
        self._block_ts_start: str | None = None
        self._pending_events: list[dict] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_row(self, row_idx: int, row_meta: dict | None = None) -> None:
        """
        Switch to a new data sample row.

        If there are pending events belonging to the previous row, they are
        flushed as a single JSON block before the buffer is reset and collection
        begins for the new row.

        Args:
            row_idx:  Dataset row number (0-indexed).
            row_meta: Optional row-level metadata written to the block's top level.
                      Recommended fields for human navigation: category_id, task_id,
                      category_name, task_key_words. Pass None or an empty dict to
                      omit metadata.
        """
        if self._pending_events:
            self._flush_block()
        self._row_idx        = row_idx
        self._row_meta       = {k: v for k, v in (row_meta or {}).items() if v not in ("", None)}
        self._block_ts_start = _now()
        self._pending_events = []

    def log(self, agent: str, event: str, data: Any) -> None:
        """Append one event to the current row's buffer (does not write to disk immediately)."""
        self._pending_events.append({
            "ts":    _now(),
            "agent": agent,
            "event": event,
            "data":  data,
        })

    def close(self) -> None:
        """Flush the final row block to disk and close the file."""
        if self._pending_events:
            self._flush_block()
        self._file.close()

    # ------------------------------------------------------------------
    # Internal: flush the current row's event buffer as a single JSON block
    # ------------------------------------------------------------------

    def _flush_block(self) -> None:
        """Serialize _pending_events as a single JSON line and write it to the file, then clear the buffer."""
        if not self._pending_events:
            return
        block = {
            "row_idx":  self._row_idx,
            **self._row_meta,           # category_id / task_id / category_name / task_key_words etc.
            "ts_start": self._block_ts_start,
            "ts_end":   _now(),
            "events":   self._pending_events,
        }
        self._file.write(json.dumps(block, ensure_ascii=False) + "\n")
        self._file.flush()
        self._pending_events = []

    # ------------------------------------------------------------------
    # Convenience methods: Prosecutor
    # ------------------------------------------------------------------

    def prosecutor_start(
        self,
        instruction: str,
        input_prompt: str,
        defendant_description: str,
        prosecutor_role: str = "ordinary_user",
        prosecutor_system_prompt: str = "",
    ) -> None:
        self.log("Prosecutor", "conversation_start", {
            "instruction":              instruction,
            "input_prompt":             input_prompt,
            "defendant_description":    defendant_description,
            "prosecutor_role":          prosecutor_role,
            "prosecutor_system_prompt": prosecutor_system_prompt,
        })

    def prosecutor_turn(self, turn: int, role: str, content: str) -> None:
        """role: "Defendant" | "Prosecutor" """
        self.log("Prosecutor", "conversation_turn", {
            "turn":    turn,
            "role":    role,
            "content": content,
        })

    def prosecutor_is_done_check(self, defendant_reply: str, is_done: bool) -> None:
        self.log("Prosecutor", "is_done_check", {
            "defendant_reply": defendant_reply,
            "is_done":         is_done,
        })

    def prosecutor_followup(self, turn: int, followup: str | None) -> None:
        self.log("Prosecutor", "conversation_turn", {
            "turn":    turn,
            "role":    "Prosecutor",
            "content": followup if followup is not None else "[DONE — Prosecutor ended conversation]",
        })

    def prosecutor_end(self, conversation: list[dict], last_response: str) -> None:
        self.log("Prosecutor", "conversation_end", {
            "full_conversation": conversation,
            "last_response":     last_response,
            "total_turns":       len(conversation),
        })

    # ------------------------------------------------------------------
    # Convenience methods: Verifier
    # ------------------------------------------------------------------

    def verifier_skipped(self, phase: str, instruction: str) -> None:
        """Log that the Verifier skipped the check because both physical modes are empty."""
        self.log("Verifier", "skipped", {
            "phase":       phase,
            "instruction": instruction,
            "reason":      "physical_success_mode and physical_fail_mode are both empty",
        })

    def verifier_check_start(
        self, phase: str, instruction: str, os_info: str, tool_hints: str | None = None
    ) -> None:
        self.log("Verifier", "check_start", {
            "phase":       phase,
            "instruction": instruction,
            "os":          os_info,
            "tool_hints":  tool_hints,
        })

    def verifier_plan(
        self,
        instruction: str,
        physical_success_mode: str,
        physical_fail_mode: str,
        command: str,
    ) -> None:
        self.log("Verifier", "plan_command", {
            "instruction":           instruction,
            "physical_success_mode": physical_success_mode,
            "physical_fail_mode":    physical_fail_mode,
            "planned_command":       command,
        })

    def verifier_execute(self, command: str, result: str, attempt: int = 0) -> None:
        """attempt=0 means first execution; >0 is the retry number."""
        self.log("Verifier", "execute_command", {
            "attempt": attempt,
            "command": command,
            "result":  result,
        })

    def verifier_retry(self, retry_n: int, new_command: str, failed_output: str) -> None:
        self.log("Verifier", "retry", {
            "retry_n":       retry_n,
            "failed_output": failed_output,
            "new_command":   new_command,
        })

    def verifier_check_end(self, phase: str, snapshot: dict) -> None:
        self.log("Verifier", "check_end", {
            "phase":    phase,
            "snapshot": snapshot,
        })

    # ------------------------------------------------------------------
    # Convenience methods: Analyzer
    # ------------------------------------------------------------------

    def analyzer_input(
        self,
        instruction: str,
        conversation: list[dict],
        system_status_before: dict,
        system_status_after: dict,
        semantic_success_mode: str,
        semantic_fail_mode: str,
        physical_success_mode: str,
        physical_fail_mode: str,
        last_response: str,
    ) -> None:
        self.log("Analyzer", "input", {
            "instruction":           instruction,
            "conversation":          conversation,
            "last_response":         last_response,
            "system_status_before":  system_status_before,
            "system_status_after":   system_status_after,
            "semantic_success_mode": semantic_success_mode,
            "semantic_fail_mode":    semantic_fail_mode,
            "physical_success_mode": physical_success_mode,
            "physical_fail_mode":    physical_fail_mode,
        })

    def analyzer_output_raw(self, raw: str) -> None:
        self.log("Analyzer", "output_raw", {"raw": raw})

    def analyzer_judgement(self, judgement: str, reason: str) -> None:
        self.log("Analyzer", "judgement", {
            "judgement": judgement,
            "reason":    reason,
        })

    # ------------------------------------------------------------------
    # Convenience methods: Recoverer
    # ------------------------------------------------------------------

    def recoverer_skip(self, phase: str, reason: str) -> None:
        """Log that a recovery phase was skipped (action is empty) and record the reason."""
        self.log("Recoverer", "skip", {
            "phase":  phase,
            "reason": reason,
        })

    def recoverer_action_start(
        self, phase: str, action: str, os_info: str, tool_hints: str | None = None
    ) -> None:
        self.log("Recoverer", "action_start", {
            "phase":      phase,
            "action":     action,
            "os":         os_info,
            "tool_hints": tool_hints,
        })

    def recoverer_plan(self, phase: str, action: str, command: str) -> None:
        """Log the single shell command the LLM translated from the natural language action (kept for backwards compatibility)."""
        self.log("Recoverer", "plan_command", {
            "phase":   phase,
            "action":  action,
            "command": command,
        })

    def recoverer_plan_multi(self, phase: str, action: str, commands: list[str]) -> None:
        """Log the list of shell commands the LLM translated from the natural language action (used for multi-step execution)."""
        self.log("Recoverer", "plan_commands", {
            "phase":    phase,
            "action":   action,
            "commands": commands,
            "steps":    len(commands),
        })

    def recoverer_execute(
        self, phase: str, command: str, result: str, attempt: int,
        step_idx: int = 0,
    ) -> None:
        """Log a command execution result. attempt=0 means first execution; >0 is the retry number."""
        self.log("Recoverer", "execute_command", {
            "phase":    phase,
            "step_idx": step_idx,
            "attempt":  attempt,
            "command":  command,
            "result":   result,
        })

    def recoverer_retry(
        self, phase: str, retry_n: int, new_command: str, failed_output: str,
        step_idx: int = 0,
    ) -> None:
        """Log a retry: the LLM received the failed output and produced a new command."""
        self.log("Recoverer", "retry", {
            "phase":         phase,
            "step_idx":      step_idx,
            "retry_n":       retry_n,
            "failed_output": failed_output,
            "new_command":   new_command,
        })

    def recoverer_action_end(self, phase: str, snapshot: dict) -> None:
        self.log("Recoverer", "action_end", {
            "phase":    phase,
            "snapshot": snapshot,
        })

"""
pipeline_logs_tool.py
=====================

Unified LangChain tool for browsing all pipeline artifacts stored under the
bind-mounted ``/pipeline-logs`` directory.

This single tool replaces the previous ``log_explorer``, ``pipeline_report``,
and ``host_retrieval_log`` tools to eliminate routing confusion for the LLM.

Directory layout
----------------
/pipeline-logs/
├── logs/          – plain-text structured log files (``*.log``)
├── reports/       – HTML data-quality reports and CSV summaries
└── csv/           – intermediate CSV/JSON files (host metadata, etc.)

Log format
----------
Pipeline log files use a structured timestamped format::

    2026-05-05 12:00:00,000 - INFO - 🚀 Starting phage FASTA merge
    2026-05-05 12:00:01,500 - WARNING - ⚠️  Skipping empty file: foo.fasta
    2026-05-05 12:00:05,200 - INFO - ✅ Merged 14/14 phage FASTA files

Security guarantees
-------------------
* All file paths are resolved and checked to stay within the log root.
* Files are never written.
* Reads are capped at ``AGENT_MAX_LOG_SIZE_KB`` kilobytes (default 512 KB).

Actions
-------
**Discovery**
  ``list``            – list all files under /pipeline-logs (logs, reports, CSVs).
                        Pass path= to scope to a subdirectory.

**Log file browsing** (path= required; use paths returned by action='list')
  ``read``            – read a log file (start_line=/end_line= for a section).
  ``head``            – first n_lines lines of a log file (default 50).
  ``tail``            – last n_lines lines of a log file (default 50).
  ``search``          – grep for a pattern across log files (pattern= required).
  ``filter_level``    – show only WARNING/ERROR lines (level= one of DEBUG/INFO/WARNING/ERROR).
  ``summary``         – compact summary of a structured log file.

**Report / CSV browsing** (path= required; use paths returned by action='list')
  ``show``            – display a report: CSV files as Markdown tables,
                        HTML files as plain text. n_rows= limits CSV rows (default 50).

**Host retrieval shortcuts** (no path= needed)
  ``list_failures``   – hosts that failed download/indexing.
  ``get_status``      – host_status_report.csv (per-phage resolution results).
  ``get_fasta_qc``    – host FASTA quality-control results (host_fasta_qc.csv).
  ``get_download_log``       – recent lines from host_download.log.
  ``get_host_mapping_log``   – recent lines from create_host_mapping.log.

Common optional parameters
---------------------------
``filter``   – case-insensitive substring to restrict rows/lines.
``n_lines``  – line count for head/tail/download_log (default 50, max 500).
``n_rows``   – row count for CSV show (default 50, max 500).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Structured log-line pattern
# ---------------------------------------------------------------------------
_STRUCTURED_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)"
    r"\s+-\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL)"
    r"\s+-\s+(.*)$"
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_LOG_ROOT = Path(os.environ.get("PBI_LOGS_DIR", "/pipeline-logs"))
_MAX_BYTES = int(os.environ.get("AGENT_MAX_LOG_SIZE_KB", "512")) * 1024
_MAX_CONTEXT_LINES = 10
_MAX_SEARCH_MATCHES = 100
_MAX_N_LINES = 500
_DEFAULT_N_LINES = 50
_MAX_N_ROWS = 500
_DEFAULT_N_ROWS = 50
_AVERAGE_LINE_BYTES = 200
_MAX_FILES_TO_SEARCH = _MAX_SEARCH_MATCHES

# Known host-related log paths (relative to log root)
_HOST_DOWNLOAD_LOG = "logs/host_download.log"
_HOST_FAILURE_LOG = "logs/host_download_failures.log"
_HOST_FASTA_QC_LOG = "logs/host_fasta_qc.csv"
_HOST_STATUS_REPORT = "reports/host_status_report.csv"
_HOST_MAPPING_LOG = "logs/create_host_mapping.log"

_LOG_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class PipelineLogsInput(BaseModel):
    action: str = Field(
        description=(
            "Action to perform. Discovery: 'list'. "
            "Log file browsing (requires path=): 'read', 'head', 'tail', 'search', "
            "'filter_level', 'summary'. "
            "Report/CSV browsing (requires path=): 'show'. "
            "Host retrieval shortcuts (no path needed): 'list_failures', "
            "'get_status', 'get_fasta_qc', 'get_download_log', 'get_host_mapping_log'."
        )
    )
    path: Optional[str] = Field(
        default=None,
        description=(
            "Relative path inside /pipeline-logs, e.g. 'logs/host_download.log' "
            "or 'reports/phage_metadata_report.html'. "
            "Required for read/head/tail/search/filter_level/summary/show. "
            "Optional for 'list' (omit to see everything). "
            "Always use exact paths returned by action='list'."
        ),
    )
    pattern: Optional[str] = Field(
        default=None,
        description='Substring or regex to search for (required for "search").',
    )
    context_lines: int = Field(
        default=2,
        description="Lines of context around each match for 'search' (max 10).",
    )
    n_lines: int = Field(
        default=_DEFAULT_N_LINES,
        description=(
            f"Number of lines for 'head', 'tail', or 'get_download_log' "
            f"(default {_DEFAULT_N_LINES}, max {_MAX_N_LINES})."
        ),
    )
    n_rows: int = Field(
        default=_DEFAULT_N_ROWS,
        description=(
            f"Maximum rows to display for 'show' on CSV files "
            f"(default {_DEFAULT_N_ROWS}, max {_MAX_N_ROWS})."
        ),
    )
    start_line: Optional[int] = Field(
        default=None,
        description="1-based first line to return for 'read' (optional).",
    )
    end_line: Optional[int] = Field(
        default=None,
        description="1-based last line to return for 'read' (optional).",
    )
    level: str = Field(
        default="WARNING",
        description=(
            "Log level for 'filter_level': one of 'DEBUG', 'INFO', 'WARNING', 'ERROR'. "
            "Shows lines at this level and above (default 'WARNING')."
        ),
    )
    filter: Optional[str] = Field(  # noqa: A003
        default=None,
        description=(
            "Optional case-insensitive substring filter. "
            "Restricts rows for CSV files or lines for log files."
        ),
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _safe_resolve(relative: Optional[str]) -> Path:
    """Resolve *relative* under the log root and verify it stays inside."""
    if not relative:
        return _LOG_ROOT.resolve()
    resolved = (_LOG_ROOT / relative).resolve()
    root = _LOG_ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path '{relative}' resolves outside the log directory. "
            "Only files within /pipeline-logs/ are accessible."
        )
    return resolved


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def _list_files(base: Path) -> str:
    """Return a formatted tree of all files under *base*."""
    if not base.exists():
        return (
            "Pipeline logs directory not found. "
            "Run the pipeline first to generate logs and reports."
        )
    files = sorted(p for p in base.rglob("*") if p.is_file())
    if not files:
        return "No files found. Run the pipeline to generate logs and reports."

    lines = [f"Files in {base}:", ""]
    for f in files:
        rel = f.relative_to(_LOG_ROOT)
        size_kb = f.stat().st_size / 1024
        lines.append(f"  {rel}  ({size_kb:.1f} KB)")
    lines.append("")
    lines.append(
        "Use action='show' with path= for reports/CSVs, "
        "or action='summary'/'head'/'tail' with path= for log files."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Log file helpers (from log_tool.py)
# ---------------------------------------------------------------------------

def _read_log(target: Path, start_line: Optional[int],
              end_line: Optional[int]) -> str:
    if not target.exists():
        return f"Log file not found: {target.relative_to(_LOG_ROOT)}"
    if target.is_dir():
        return f"'{target.name}' is a directory — use action='list' to browse it."
    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    text = raw.decode("utf-8", errors="replace")
    size = target.stat().st_size
    truncated = size > _MAX_BYTES
    lines = text.splitlines()
    total = len(lines)

    if start_line is not None or end_line is not None:
        s = (start_line or 1) - 1
        e = end_line or total
        s = max(0, min(s, total))
        e = max(s, min(e, total))
        selected = lines[s:e]
        header = (
            f"[Lines {s + 1}–{e} of {total} in "
            f"{target.relative_to(_LOG_ROOT)} ({size // 1024} KB)]\n\n"
        )
        return header + "\n".join(selected)

    header = (
        f"[{total} lines / {size // 1024} KB — "
        f"{target.relative_to(_LOG_ROOT)}"
        + (" — TRUNCATED" if truncated else "")
        + "]\n\n"
    )
    return header + text


def _head_log(target: Path, n_lines: int) -> str:
    if not target.exists():
        return f"Log file not found: {target.relative_to(_LOG_ROOT)}"
    if target.is_dir():
        return f"'{target.name}' is a directory — use action='list' to browse it."
    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    lines = raw.decode("utf-8", errors="replace").splitlines()
    selected = lines[:n_lines]
    size = target.stat().st_size
    header = (
        f"[First {len(selected)} of {len(lines)} lines "
        f"in {target.relative_to(_LOG_ROOT)} ({size // 1024} KB)]\n\n"
    )
    return header + "\n".join(selected)


def _tail_log(target: Path, n_lines: int) -> str:
    if not target.exists():
        return f"Log file not found: {target.relative_to(_LOG_ROOT)}"
    if target.is_dir():
        return f"'{target.name}' is a directory — use action='list' to browse it."
    size = target.stat().st_size
    est_offset = n_lines * _AVERAGE_LINE_BYTES
    with target.open("rb") as fh:
        if size > est_offset:
            fh.seek(-est_offset, 2)
            fh.read(1)  # align to next newline boundary
        raw = fh.read(_MAX_BYTES)
    lines = raw.decode("utf-8", errors="replace").splitlines()
    selected = lines[-n_lines:]
    header = (
        f"[Last {len(selected)} of ~{size // _AVERAGE_LINE_BYTES} lines "
        f"in {target.relative_to(_LOG_ROOT)} ({size // 1024} KB)]\n\n"
    )
    return header + "\n".join(selected)


def _search_logs(base: Path, pattern: str, context_lines: int) -> str:
    if not base.exists():
        return f"Path not found: {base.relative_to(_LOG_ROOT)}"
    context_lines = min(context_lines, _MAX_CONTEXT_LINES)
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"Invalid regex pattern '{pattern}': {exc}"

    files = sorted(base.rglob("*.log")) if base.is_dir() else [base]
    files = files[:_MAX_FILES_TO_SEARCH]

    results: list[str] = []
    total_matches = 0
    for fpath in files:
        if not fpath.is_file():
            continue
        with fpath.open("rb") as fh:
            raw = fh.read(_MAX_BYTES)
        lines = raw.decode("utf-8", errors="replace").splitlines()
        rel = fpath.relative_to(_LOG_ROOT)
        for i, line in enumerate(lines):
            if total_matches >= _MAX_SEARCH_MATCHES:
                break
            if rx.search(line):
                ctx_start = max(0, i - context_lines)
                ctx_end = min(len(lines), i + context_lines + 1)
                block = [f"  {rel}:{j + 1}: {lines[j]}" for j in range(ctx_start, ctx_end)]
                results.append("\n".join(block))
                total_matches += 1
        if total_matches >= _MAX_SEARCH_MATCHES:
            break

    if not results:
        return f"No matches for '{pattern}' in {base.relative_to(_LOG_ROOT)}."
    header = f"{total_matches} match(es) for '{pattern}':\n\n"
    return header + "\n---\n".join(results)


def _filter_level_log(target: Path, level: str) -> str:
    if not target.exists():
        return f"Log file not found: {target.relative_to(_LOG_ROOT)}"
    if target.is_dir():
        return f"'{target.name}' is a directory. Provide a specific log file path."
    level_upper = level.upper()
    min_order = _LOG_LEVEL_ORDER.get(level_upper, _LOG_LEVEL_ORDER["WARNING"])

    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    lines = raw.decode("utf-8", errors="replace").splitlines()

    matched: list[str] = []
    for line in lines:
        m = _STRUCTURED_LOG_RE.match(line)
        if m:
            line_level = m.group(2)
            if _LOG_LEVEL_ORDER.get(line_level, 0) >= min_order:
                matched.append(line)
        # If line doesn't match the structured format, skip it (it's a continuation line
        # or a non-structured entry from a different log format).

    if not matched:
        return (
            f"No lines at {level_upper} or above found in "
            f"{target.relative_to(_LOG_ROOT)}. "
            "The pipeline may have completed without issues at this level."
        )
    rel = target.relative_to(_LOG_ROOT)
    return (
        f"{len(matched)} line(s) at {level_upper}+ in {rel}:\n\n"
        + "\n".join(matched)
    )


def _summary_log(target: Path) -> str:
    if not target.exists():
        return f"Log file not found: {target.relative_to(_LOG_ROOT)}"
    if target.is_dir():
        return f"'{target.name}' is a directory — use action='list' to browse it."
    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    lines = raw.decode("utf-8", errors="replace").splitlines()
    size = target.stat().st_size
    rel = target.relative_to(_LOG_ROOT)

    starts: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    successes: list[str] = []
    level_counts: dict[str, int] = {}

    for line in lines:
        m = _STRUCTURED_LOG_RE.match(line)
        if not m:
            continue
        _ts, lvl, msg = m.groups()
        level_counts[lvl] = level_counts.get(lvl, 0) + 1
        if "🚀" in msg or "Starting" in msg:
            starts.append(f"  {_ts}: {msg}")
        elif lvl == "WARNING":
            warnings.append(f"  {_ts}: {msg}")
        elif lvl == "ERROR" or lvl == "CRITICAL":
            errors.append(f"  {_ts}: {msg}")
        elif "✅" in msg or "Completed" in msg or "Finished" in msg or "Done" in msg:
            successes.append(f"  {_ts}: {msg}")

    parts = [f"Summary of {rel} ({len(lines)} lines, {size // 1024} KB):", ""]
    if starts:
        parts.append("Pipeline steps started:")
        parts.extend(starts[:20])
        parts.append("")
    if successes:
        parts.append("Successes:")
        parts.extend(successes[:20])
        parts.append("")
    if warnings:
        parts.append(f"Warnings ({len(warnings)}):")
        parts.extend(warnings[:10])
        if len(warnings) > 10:
            parts.append(f"  ... and {len(warnings) - 10} more warnings")
        parts.append("")
    if errors:
        parts.append(f"Errors ({len(errors)}):")
        parts.extend(errors[:10])
        if len(errors) > 10:
            parts.append(f"  ... and {len(errors) - 10} more errors")
        parts.append("")
    if level_counts:
        count_str = ", ".join(
            f"{lvl}: {cnt}" for lvl, cnt in sorted(level_counts.items())
        )
        parts.append(f"Line counts by level: {count_str}")

    if not (starts or successes or warnings or errors):
        parts.append(
            "No structured log lines found. "
            "Use action='read' to inspect the file directly."
        )
        if not (starts or successes or warnings or errors):
            parts.append(
                "\nNote: this file may not use the structured timestamped format."
            )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Report / CSV helpers (from report_tool.py)
# ---------------------------------------------------------------------------

def _show_report(target: Path, filter_str: Optional[str], n_rows: int) -> str:
    """Display a report file: CSV as Markdown table, HTML as plain text."""
    if not target.exists():
        return (
            f"Report not found: {target.relative_to(_LOG_ROOT)!s}.\n"
            "Use action='list' to see available files."
        )
    if target.is_dir():
        return f"'{target.name}' is a directory — use action='list' to browse it."

    suffix = target.suffix.lower()
    n_rows = min(max(n_rows, 1), _MAX_N_ROWS)

    if suffix == ".csv":
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_csv(target)
        except Exception as exc:  # noqa: BLE001
            return f"Error reading {target.relative_to(_LOG_ROOT)}: {exc}"

        if df.empty:
            return f"{target.relative_to(_LOG_ROOT)} is empty."

        if filter_str:
            mask = df.apply(
                lambda col: col.astype(str).str.contains(
                    filter_str, case=False, na=False
                )
            ).any(axis=1)
            df = df[mask]
            if df.empty:
                return (
                    f"No rows matching '{filter_str}' "
                    f"in {target.relative_to(_LOG_ROOT)}."
                )

        total = len(df)
        df = df.head(n_rows)
        try:
            table = df.to_markdown(index=False)
        except ImportError:
            table = df.to_string(index=False)
        note = (
            f" (showing first {n_rows} of {total} rows)"
            if total > n_rows else ""
        )
        return (
            f"{target.relative_to(_LOG_ROOT)} — {total} row(s){note}:\n\n"
            + table
        )

    # HTML and other text files: return raw text (truncated)
    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    text = raw.decode("utf-8", errors="replace")
    size = target.stat().st_size
    truncated = size > _MAX_BYTES
    note = (
        f"\n\n[TRUNCATED — showing first {_MAX_BYTES // 1024} KB "
        f"of {size // 1024} KB. Use action='read' for more.]"
        if truncated else ""
    )
    return text + note


# ---------------------------------------------------------------------------
# Host-retrieval shortcuts (from host_log_tool.py)
# ---------------------------------------------------------------------------

def _tail_text(path: Path, n_lines: int, filter_str: Optional[str] = None) -> str:
    if not path.exists():
        return f"File not found: {path.relative_to(_LOG_ROOT)}"
    size = path.stat().st_size
    with path.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    lines = raw.decode("utf-8", errors="replace").splitlines()
    selected = lines[-n_lines:]
    if filter_str:
        selected = [ln for ln in selected if filter_str.lower() in ln.lower()]
    header = (
        f"[Last {len(selected)} lines "
        f"of {path.relative_to(_LOG_ROOT)} ({size // 1024} KB)]\n\n"
    )
    return header + "\n".join(selected)


def _read_csv_table(path: Path, filter_str: Optional[str] = None,
                    max_rows: int = 100) -> str:
    if not path.exists():
        return f"File not found: {path.relative_to(_LOG_ROOT)}"
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return f"Error reading {path.relative_to(_LOG_ROOT)}: {exc}"

    if df.empty:
        return f"{path.relative_to(_LOG_ROOT)} is empty."

    if filter_str:
        mask = df.apply(
            lambda col: col.astype(str).str.contains(filter_str, case=False, na=False)
        ).any(axis=1)
        df = df[mask]
        if df.empty:
            return (
                f"No rows matching '{filter_str}' "
                f"in {path.relative_to(_LOG_ROOT)}."
            )

    total = len(df)
    df = df.head(max_rows)
    try:
        table = df.to_markdown(index=False)
    except ImportError:
        table = df.to_string(index=False)
    note = (
        f" (showing first {max_rows} of {total} rows)"
        if total > max_rows else ""
    )
    return f"{path.relative_to(_LOG_ROOT)} — {total} row(s){note}:\n\n" + table


def _list_failures(filter_str: Optional[str] = None) -> str:
    status_path = _LOG_ROOT / _HOST_STATUS_REPORT
    if status_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415
            df = pd.read_csv(status_path)
            fail_cols = [
                c for c in df.columns
                if any(kw in c.lower() for kw in ("status", "fail", "error", "missing", "resolved"))
            ]
            if fail_cols:
                status_col = fail_cols[0]
                failed_mask = df[status_col].astype(str).str.lower().str.contains(
                    r"fail|error|missing|not.?found|unresolved", na=False
                )
                if filter_str:
                    filter_mask = df.apply(
                        lambda col: col.astype(str).str.contains(
                            filter_str, case=False, na=False
                        )
                    ).any(axis=1)
                    failed_mask = failed_mask & filter_mask
                failed = df[failed_mask]
                if not failed.empty:
                    try:
                        table = failed.head(200).to_markdown(index=False)
                    except ImportError:
                        table = failed.head(200).to_string(index=False)
                    return (
                        f"Failed hosts from host_status_report.csv "
                        f"({len(failed)} row(s), up to 200 shown):\n\n"
                        + table
                    )
                return (
                    "No failed hosts found in host_status_report.csv"
                    + (f" matching filter '{filter_str}'" if filter_str else "")
                    + "."
                )
        except Exception:  # noqa: BLE001
            pass

    failure_path = _LOG_ROOT / _HOST_FAILURE_LOG
    if failure_path.exists():
        with failure_path.open("rb") as fh:
            raw = fh.read(_MAX_BYTES)
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if filter_str:
            lines = [ln for ln in lines if filter_str.lower() in ln.lower()]
        if not lines:
            return (
                "No entries in host_download_failures.log"
                + (f" matching filter '{filter_str}'" if filter_str else "")
                + "."
            )
        return (
            f"Host failures from host_download_failures.log "
            f"({len(lines)} line(s)):\n\n"
            + "\n".join(lines)
        )

    return (
        "No host failure logs found. "
        "The pipeline may not have run yet."
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class PipelineLogsTool(BaseTool):
    """Browse all PBI pipeline logs and reports under /pipeline-logs/."""

    name: str = "pipeline_logs"
    description: str = (
        "Browse ALL pipeline artifacts (log files, HTML reports, CSV files) "
        "stored under /pipeline-logs/. "
        "ALWAYS start with action='list' to discover what files exist — "
        "never guess file names or report contents. "
        "action='list': list every file available (logs/, reports/, csv/ subdirs). "
        "action='show': display a report or CSV file as a table or text "
        "(path= required, e.g. 'reports/phage_metadata_report.html' or "
        "'reports/host_status_report.csv'). "
        "action='summary': compact summary of a .log file (path= required). "
        "action='head' / 'tail': first/last n_lines of a log file (path= required). "
        "action='search': grep across log files (pattern= required; path= optional). "
        "action='filter_level': show WARNING/ERROR lines only (path= required; "
        "level= one of DEBUG/INFO/WARNING/ERROR). "
        "action='read': full content of any file (path= required). "
        "Host retrieval shortcuts (no path needed): "
        "'list_failures', 'get_status', 'get_fasta_qc', "
        "'get_download_log', 'get_host_mapping_log'. "
        "Optional filter= restricts CSV rows or log lines to those containing a substring. "
        "Optional n_rows= limits CSV rows (default 50). "
        "Optional n_lines= limits log lines for head/tail (default 50)."
    )
    args_schema: Type[BaseModel] = PipelineLogsInput

    def _run(  # noqa: PLR0911,PLR0912
        self,
        action: str,
        path: Optional[str] = None,
        pattern: Optional[str] = None,
        context_lines: int = 2,
        n_lines: int = _DEFAULT_N_LINES,
        n_rows: int = _DEFAULT_N_ROWS,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        level: str = "WARNING",
        filter: Optional[str] = None,  # noqa: A002
    ) -> str:
        action = action.strip().lower()
        n_lines = min(max(n_lines, 1), _MAX_N_LINES)
        n_rows = min(max(n_rows, 1), _MAX_N_ROWS)

        try:
            target = _safe_resolve(path)
        except ValueError as exc:
            return f"Security error: {exc}"

        # ---- Discovery ----
        if action == "list":
            return _list_files(target)

        # ---- Report / CSV display ----
        if action == "show":
            if not path:
                return (
                    "path= is required for action='show'. "
                    "Use action='list' to see available files.\n\n"
                    + _list_files(_LOG_ROOT)
                )
            return _show_report(target, filter_str=filter, n_rows=n_rows)

        # ---- Log file browsing ----
        if action == "read":
            if not path:
                return (
                    "path= is required for action='read'. "
                    "Use action='list' to see available files.\n\n"
                    + _list_files(_LOG_ROOT)
                )
            return _read_log(target, start_line, end_line)

        if action == "head":
            if not path:
                return (
                    "path= is required for action='head'. "
                    "Use action='list' to see available files.\n\n"
                    + _list_files(_LOG_ROOT)
                )
            return _head_log(target, n_lines)

        if action == "tail":
            if not path:
                return (
                    "path= is required for action='tail'. "
                    "Use action='list' to see available files.\n\n"
                    + _list_files(_LOG_ROOT)
                )
            return _tail_log(target, n_lines)

        if action == "search":
            if not pattern:
                return "pattern= is required for action='search'."
            context_lines = min(context_lines, _MAX_CONTEXT_LINES)
            return _search_logs(target, pattern, context_lines)

        if action == "filter_level":
            if not path:
                return (
                    "path= is required for action='filter_level'. "
                    "Use action='list' to see available files.\n\n"
                    + _list_files(_LOG_ROOT)
                )
            return _filter_level_log(target, level)

        if action == "summary":
            if not path:
                return (
                    "path= is required for action='summary'. "
                    "Use action='list' to see available files.\n\n"
                    + _list_files(_LOG_ROOT)
                )
            return _summary_log(target)

        # ---- Host retrieval shortcuts ----
        if action == "list_failures":
            return _list_failures(filter_str=filter)

        if action == "get_status":
            return _read_csv_table(
                _LOG_ROOT / _HOST_STATUS_REPORT,
                filter_str=filter,
            )

        if action == "get_fasta_qc":
            return _read_csv_table(
                _LOG_ROOT / _HOST_FASTA_QC_LOG,
                filter_str=filter,
            )

        if action == "get_download_log":
            return _tail_text(_LOG_ROOT / _HOST_DOWNLOAD_LOG, n_lines, filter)

        if action == "get_host_mapping_log":
            return _tail_text(_LOG_ROOT / _HOST_MAPPING_LOG, n_lines, filter)

        return (
            f"Unknown action '{action}'. "
            "Valid actions: list, show, read, head, tail, search, filter_level, "
            "summary, list_failures, get_status, get_fasta_qc, "
            "get_download_log, get_host_mapping_log."
        )

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

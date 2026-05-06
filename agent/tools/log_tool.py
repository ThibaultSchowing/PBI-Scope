"""
log_tool.py
===========

LangChain tool for browsing and searching pipeline log files that are
bind-mounted (read-only) into the agent container at ``/pipeline-logs``.

Security guarantees
-------------------
* All file paths are resolved and checked to be strictly under the
  configured log root — path-traversal attempts are rejected.
* Files are never written; the container mount is read-only.
* Reads are capped at ``AGENT_MAX_LOG_SIZE_KB`` kilobytes (default 512 KB)
  to prevent token-budget exhaustion.

Log format
----------
Pipeline log files use a structured timestamped format produced by the
shared ``workflow/scripts/common/logging_utils.py`` helper::

    2026-05-05 12:00:00,000 - INFO - 🚀 Starting phage FASTA merge
    2026-05-05 12:00:01,500 - WARNING - ⚠️  Skipping empty file: foo.fasta
    2026-05-05 12:00:05,200 - INFO - ✅ Merged 14/14 phage FASTA files

Use ``action='filter_level'`` to isolate WARNING/ERROR lines, and
``action='summary'`` for a compact human-readable summary of a log file.

Input schema (JSON string)
--------------------------
``action`` – one of ``"list"``, ``"read"``, ``"head"``, ``"tail"``,
             ``"search"``, ``"filter_level"``, ``"summary"`` (required).
``path``   – relative path inside the log root, e.g. ``"logs/rule.log"``
             (required for ``read``, ``head``, ``tail``, ``filter_level``,
             ``summary``; optional for ``list`` to scope the listing to a
             subdirectory; optional for ``search`` — omit or point to a
             directory to search all log files recursively).
``pattern`` – substring or regex to search for (required for ``search``).
``context_lines`` – number of lines of context around each match for
                    ``search`` (default 2, max 10).
``n_lines`` – number of lines to return for ``head`` / ``tail``
              (default 50, max 500).
``start_line`` – 1-based first line to return for ``read`` (optional).
``end_line``   – 1-based last line to return for ``read`` (optional).
``level``  – log level to filter on for ``filter_level``: one of
             ``"DEBUG"``, ``"INFO"``, ``"WARNING"``, ``"ERROR"``
             (default ``"WARNING"`` — shows WARNING and ERROR lines).
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
# Matches lines produced by logging_utils.py:
#   2026-05-05 12:00:00,000 - LEVEL - message
# ---------------------------------------------------------------------------
_STRUCTURED_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)"  # timestamp
    r"\s+-\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL)"     # level
    r"\s+-\s+(.*)$"                                   # message
)

# ---------------------------------------------------------------------------
# Configuration (read from environment with safe defaults)
# ---------------------------------------------------------------------------

_LOG_ROOT = Path(os.environ.get("PBI_LOGS_DIR", "/pipeline-logs"))
_MAX_BYTES = int(os.environ.get("AGENT_MAX_LOG_SIZE_KB", "512")) * 1024
_MAX_CONTEXT_LINES = 10
_MAX_SEARCH_MATCHES = 100  # stop collecting context after this many hits
_MAX_N_LINES = 500         # cap for head / tail
_DEFAULT_N_LINES = 50
# Rough heuristic for the tail seek offset: assume an average of 200 bytes
# per line.  Actual line counts may vary; the tail implementation falls back
# to a full read when the file is smaller than the estimated window.
_AVERAGE_LINE_BYTES = 200
# Maximum number of files to enumerate in a recursive search.
# Reusing _MAX_SEARCH_MATCHES as a ceiling keeps the file-count proportional
# to the match budget — once 100 matches are exhausted, scanning more files
# would produce no additional output anyway.
_MAX_FILES_TO_SEARCH = _MAX_SEARCH_MATCHES


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class LogExplorerInput(BaseModel):
    action: str = Field(
        description=(
            'Action to perform: "list", "read", "head", "tail", "search", '
            '"filter_level", or "summary".'
        )
    )
    path: Optional[str] = Field(
        default=None,
        description=(
            "Relative path inside the pipeline-logs directory. "
            'Required for "read", "head", "tail", "filter_level", and "summary"; '
            'optional for "list" '
            "(omit or use empty string to list the root); optional for "
            '"search" — omit or point to a directory to search all log '
            "files recursively."
        ),
    )
    pattern: Optional[str] = Field(
        default=None,
        description='Substring or regex pattern to search for (required for "search").',
    )
    context_lines: int = Field(
        default=2,
        description="Lines of context around each match for search (max 10).",
    )
    n_lines: int = Field(
        default=_DEFAULT_N_LINES,
        description='Number of lines to return for "head" or "tail" (max 500).',
    )
    start_line: Optional[int] = Field(
        default=None,
        description=(
            '1-based line number to start reading from (for "read"). '
            "Allows targeted extraction of large files."
        ),
    )
    end_line: Optional[int] = Field(
        default=None,
        description=(
            '1-based line number to stop reading at, inclusive (for "read"). '
            "Used together with start_line to read a specific section."
        ),
    )
    level: Optional[str] = Field(
        default=None,
        description=(
            'Minimum log level to include for "filter_level". '
            'One of "DEBUG", "INFO", "WARNING", "ERROR". '
            'Defaults to "WARNING" (returns WARNING and ERROR lines only). '
            'Use "ERROR" to see only errors; use "INFO" to see all messages.'
        ),
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _safe_resolve(relative: Optional[str]) -> Path:
    """
    Resolve *relative* under the log root and verify it does not escape.

    Raises
    ------
    ValueError
        If the resolved path is outside the log root.
    """
    if not relative:
        return _LOG_ROOT.resolve()

    resolved = (_LOG_ROOT / relative).resolve()
    root = _LOG_ROOT.resolve()

    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path '{relative}' resolves outside the log root. "
            "Only paths within the pipeline-logs directory are accessible."
        )

    return resolved


def _list_dir(target: Path) -> str:
    """Return a formatted directory listing.

    When the target directory contains subdirectories, their immediate
    contents are shown as well (one level deep).  This lets the agent
    see all available log files in a single list call instead of
    having to enumerate each subdirectory manually.
    """
    if not target.exists():
        return (
            f"Path not found: {target.name!r} in the pipeline-logs directory.\n"
            "Use action='list' (no path) to see all available log files.\n"
            "Note: if you are looking for phage or database data, "
            "use the duckdb_query tool with a SELECT statement instead."
        )

    entries: list[str] = []
    for entry in sorted(target.iterdir()):
        if entry.is_dir():
            entries.append(f"[dir]  {entry.name}/")
            # Expand immediate contents of subdirectories so the agent
            # can see the full log file tree in one shot.
            try:
                sub_entries = sorted(entry.iterdir())
            except PermissionError:
                entries.append(f"         [permission denied]  {entry.name}/")
                sub_entries = []
            for subentry in sub_entries:
                if subentry.is_dir():
                    entries.append(f"         [dir]  {entry.name}/{subentry.name}/")
                else:
                    size_kb = subentry.stat().st_size / 1024
                    entries.append(
                        f"         [file] {entry.name}/{subentry.name}"
                        f"  ({size_kb:.1f} KB)"
                    )
        else:
            size_kb = entry.stat().st_size / 1024
            entries.append(f"[file] {entry.name}  ({size_kb:.1f} KB)")

    if not entries:
        return f"Directory is empty: {target}"

    return "\n".join([f"Contents of {target}:", *entries])


def _read_file(target: Path, start_line: Optional[int] = None,
               end_line: Optional[int] = None) -> str:
    """Read up to _MAX_BYTES from *target*, optionally restricted to a line range."""
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"'{target}' is a directory — use action='list' to browse it."

    size = target.stat().st_size
    truncated = size > _MAX_BYTES

    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)

    lines = raw.decode("utf-8", errors="replace").splitlines(keepends=True)
    total_lines = len(lines)

    if start_line is not None or end_line is not None:
        # Convert to 0-based indices, clamp to valid range.
        sl = max(0, (start_line or 1) - 1)
        el = min(total_lines, end_line if end_line is not None else total_lines)
        lines = lines[sl:el]
        header = (
            f"[Lines {sl + 1}–{sl + len(lines)} of "
            f"{'≥' if truncated else ''}{total_lines} total]\n\n"
        )
        return header + "".join(lines)

    text = "".join(lines)
    if truncated:
        text += (
            f"\n\n[TRUNCATED — showing first {_MAX_BYTES // 1024} KB "
            f"of {size // 1024} KB total. "
            "Use start_line/end_line or action='tail' to read other sections.]"
        )
    return text


def _head_file(target: Path, n_lines: int) -> str:
    """Return the first *n_lines* lines of *target*."""
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"'{target}' is a directory — provide a file path."

    n_lines = min(max(n_lines, 1), _MAX_N_LINES)

    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)

    lines = raw.decode("utf-8", errors="replace").splitlines()
    selected = lines[:n_lines]
    total = len(lines)
    header = f"[First {len(selected)} of {total} lines in {target.name}]\n\n"
    return header + "\n".join(selected)


def _tail_file(target: Path, n_lines: int) -> str:
    """Return the last *n_lines* lines of *target*."""
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"'{target}' is a directory — provide a file path."

    n_lines = min(max(n_lines, 1), _MAX_N_LINES)

    size = target.stat().st_size
    # Read the tail from the end of the file without loading everything.
    # Heuristic: average line ~200 bytes; read enough to capture n_lines.
    read_bytes = min(size, max(_MAX_BYTES, n_lines * _AVERAGE_LINE_BYTES))
    with target.open("rb") as fh:
        if size > read_bytes:
            fh.seek(size - read_bytes)
            raw = fh.read()
            # Skip the potentially partial first line.
            newline_pos = raw.find(b"\n")
            raw = raw[newline_pos + 1:] if newline_pos != -1 else raw
        else:
            raw = fh.read()

    lines = raw.decode("utf-8", errors="replace").splitlines()
    selected = lines[-n_lines:]
    header = f"[Last {len(selected)} lines of {target.name} ({size // 1024} KB total)]\n\n"
    return header + "\n".join(selected)


def _collect_log_files(root: Path) -> list[Path]:
    """Return all readable files under *root*, recursively.

    Iteration stops early once ``_MAX_FILES_TO_SEARCH`` files have been
    collected, since ``_search_dir`` will exhaust the match budget before
    processing more files anyway.
    """
    files: list[Path] = []
    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            files.append(entry)
            if len(files) >= _MAX_FILES_TO_SEARCH:
                break
    return files


def _search_file(target: Path, pattern: str, context_lines: int) -> str:
    """Search *target* for *pattern*, returning matching lines with context."""
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"'{target}' is a directory — provide a file path for search."

    context_lines = min(max(context_lines, 0), _MAX_CONTEXT_LINES)

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"Invalid regex pattern '{pattern}': {exc}"

    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)

    lines = raw.decode("utf-8", errors="replace").splitlines()
    matching_indices: list[int] = [i for i, line in enumerate(lines) if regex.search(line)]

    if not matching_indices:
        return f"No matches found for pattern '{pattern}' in {target.name}."

    total_matches = len(matching_indices)
    # Cap the number of matches rendered to avoid flooding the context window.
    matching_indices = matching_indices[:_MAX_SEARCH_MATCHES]

    # Collect context windows, merging overlapping ranges
    output_lines: list[str] = [
        f"Found {total_matches} match(es) for '{pattern}' in {target.name}"
        + (f" (showing first {_MAX_SEARCH_MATCHES}):" if total_matches > _MAX_SEARCH_MATCHES else ":")
        + "\n"
    ]
    shown: set[int] = set()
    for idx in matching_indices:
        start = max(0, idx - context_lines)
        end = min(len(lines) - 1, idx + context_lines)
        if shown and min(shown) <= start <= max(shown) + 1:
            # Merge with previous block
            for i in range(max(shown) + 1, end + 1):
                prefix = ">>>" if i == idx else "   "
                output_lines.append(f"{i + 1:6d} {prefix} {lines[i]}")
                shown.add(i)
        else:
            if shown:
                output_lines.append("       ...")
            for i in range(start, end + 1):
                prefix = ">>>" if i == idx else "   "
                output_lines.append(f"{i + 1:6d} {prefix} {lines[i]}")
                shown.add(i)

    return "\n".join(output_lines)


def _search_dir(root: Path, pattern: str, context_lines: int) -> str:
    """Search all files under *root* recursively for *pattern*."""
    files = _collect_log_files(root)
    if not files:
        return f"No files found under {root}."

    context_lines = min(max(context_lines, 0), _MAX_CONTEXT_LINES)
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"Invalid regex pattern '{pattern}': {exc}"

    sections: list[str] = []
    total_files_with_matches = 0
    remaining_matches = _MAX_SEARCH_MATCHES

    for fpath in files:
        if remaining_matches <= 0:
            break
        try:
            with fpath.open("rb") as fh:
                raw = fh.read(_MAX_BYTES)
        except OSError:
            continue

        lines = raw.decode("utf-8", errors="replace").splitlines()
        matching_indices = [i for i, line in enumerate(lines) if regex.search(line)]
        if not matching_indices:
            continue

        total_files_with_matches += 1
        file_total = len(matching_indices)
        capped = matching_indices[:remaining_matches]
        remaining_matches -= len(capped)

        rel = fpath.relative_to(_LOG_ROOT)
        section_lines: list[str] = [
            f"\n=== {rel} — {file_total} match(es)"
            + (f" (showing first {len(capped)})" if file_total > len(capped) else "")
            + " ===\n"
        ]
        shown: set[int] = set()
        for idx in capped:
            start = max(0, idx - context_lines)
            end = min(len(lines) - 1, idx + context_lines)
            if shown and min(shown) <= start <= max(shown) + 1:
                for i in range(max(shown) + 1, end + 1):
                    prefix = ">>>" if i == idx else "   "
                    section_lines.append(f"{i + 1:6d} {prefix} {lines[i]}")
                    shown.add(i)
            else:
                if shown:
                    section_lines.append("       ...")
                for i in range(start, end + 1):
                    prefix = ">>>" if i == idx else "   "
                    section_lines.append(f"{i + 1:6d} {prefix} {lines[i]}")
                    shown.add(i)
        sections.append("\n".join(section_lines))

    if not sections:
        return f"No matches found for pattern '{pattern}' in any file under {root}."

    header = (
        f"Search results for '{pattern}' across {len(files)} file(s) "
        f"— matches in {total_files_with_matches} file(s):"
    )
    return header + "".join(sections)


# Log level priority for filter_level
_LEVEL_PRIORITY: dict[str, int] = {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 2,
    "ERROR": 3,
    "CRITICAL": 4,
}


def _filter_by_level(target: Path, min_level: str) -> str:
    """Return only log lines at or above *min_level* from a structured log file.

    Lines that do not match the structured log format are passed through
    unchanged (e.g. section separators, emoji markers) so that visual
    context is preserved.
    """
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"'{target}' is a directory — provide a file path for filter_level."

    min_priority = _LEVEL_PRIORITY.get(min_level.upper(), 2)

    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)

    lines = raw.decode("utf-8", errors="replace").splitlines()
    kept: list[str] = []

    for line in lines:
        m = _STRUCTURED_LOG_RE.match(line)
        if m:
            level = m.group(2)
            if _LEVEL_PRIORITY.get(level, 0) >= min_priority:
                kept.append(line)
        else:
            # Non-structured line (separator, blank, etc.) — include as context
            # only when we have already kept some content, to avoid a noisy prefix.
            if kept and line.strip():
                kept.append(line)

    if not kept:
        return (
            f"No lines at level {min_level.upper()} or above found in {target.name}. "
            "The log may use a different format or contain no matching entries."
        )

    total_size_kb = target.stat().st_size / 1024
    header = (
        f"[{min_level.upper()}+ lines from {target.name} "
        f"({len(kept)} line(s), file is {total_size_kb:.1f} KB)]\n\n"
    )
    return header + "\n".join(kept)


def _summarise_log(target: Path) -> str:
    """Parse a structured pipeline log file and return a compact summary.

    Extracts:
    - Step start/end markers (lines with 🚀 / ✅ / ❌)
    - WARNING and ERROR counts with examples
    - Key-value pairs emitted as ``  Key : value``
    - Total lines and file size
    """
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"'{target}' is a directory — provide a file path for summary."

    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)

    lines = raw.decode("utf-8", errors="replace").splitlines()
    total_lines = len(lines)
    file_size_kb = target.stat().st_size / 1024
    truncated = target.stat().st_size > _MAX_BYTES

    counts: dict[str, int] = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
    warnings: list[str] = []
    errors: list[str] = []
    step_lines: list[str] = []         # 🚀 / ✅ / ❌ lines
    kv_lines: list[str] = []           # "   Key  : value" lines

    # Detect whether the file uses the structured format at all
    structured_count = 0

    for line in lines:
        m = _STRUCTURED_LOG_RE.match(line)
        if m:
            structured_count += 1
            level = m.group(2)
            msg = m.group(3).strip()
            counts[level] = counts.get(level, 0) + 1

            if level == "WARNING" and len(warnings) < 10:
                warnings.append(f"  [{m.group(1)}] {msg}")
            elif level in ("ERROR", "CRITICAL") and len(errors) < 10:
                errors.append(f"  [{m.group(1)}] {msg}")

            # Step markers
            if any(ch in msg for ch in ("🚀", "✅", "❌")):
                step_lines.append(f"  {msg}")

            # Key-value pairs like "   Expected inputs : 14"
            if re.match(r"\s{2,}\w[\w\s/()-]+:\s+\S", msg):
                kv_lines.append(f"  {msg.strip()}")

    out: list[str] = [
        f"Summary of {target.name} "
        f"({total_lines} lines, {file_size_kb:.1f} KB"
        + (" [truncated]" if truncated else "")
        + "):",
        "",
    ]

    if structured_count == 0:
        out.append(
            "⚠️  This file does not use the structured timestamped log format. "
            "Use action='read', 'head', or 'tail' to inspect it directly."
        )
        return "\n".join(out)

    out.append(
        f"Log level counts: "
        + ", ".join(f"{k}: {v}" for k, v in counts.items() if v > 0)
    )
    out.append("")

    if step_lines:
        out.append("Pipeline steps:")
        out.extend(step_lines[:20])
        if len(step_lines) > 20:
            out.append(f"  … and {len(step_lines) - 20} more step lines")
        out.append("")

    if kv_lines:
        out.append("Key metrics / paths:")
        out.extend(kv_lines[:30])
        if len(kv_lines) > 30:
            out.append(f"  … and {len(kv_lines) - 30} more key-value lines")
        out.append("")

    if warnings:
        out.append(f"Warnings ({counts['WARNING']} total, showing up to 10):")
        out.extend(warnings)
        out.append("")

    if errors:
        out.append(f"Errors/Critical ({counts['ERROR'] + counts['CRITICAL']} total, showing up to 10):")
        out.extend(errors)
        out.append("")

    if not step_lines and not warnings and not errors:
        out.append("No warnings or errors found. Pipeline step completed successfully.")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class LogExplorerTool(BaseTool):
    """Browse and search pipeline log files in the bind-mounted log directory."""

    name: str = "log_explorer"
    description: str = (
        "Browse and search pipeline LOG FILES only — do NOT use this for phage/protein/database data queries "
        "(use duckdb_query for those). "
        "Pipeline log files use a structured timestamped format: "
        "'YYYY-MM-DD HH:MM:SS,nnn (3-digit milliseconds) - LEVEL - message'. "
        "action='list': list log files (path= optional for subdirectory; omit to see all logs). "
        "action='read': read a log file (path= required; use start_line/end_line for a specific section). "
        "action='head': show the first n_lines lines of a log file (path= required, default n_lines=50). "
        "action='tail': show the last n_lines lines of a log file (path= required, default n_lines=50). "
        "action='search': grep for a pattern in log files (pattern= required; path= optional — omit or give a "
        "directory path to search ALL log files recursively). "
        "action='filter_level': show only lines at or above a given log level from a structured log file "
        "(path= required; level= one of 'DEBUG', 'INFO', 'WARNING', 'ERROR'; default level='WARNING'). "
        "action='summary': parse a structured log file and return a compact summary with step markers, "
        "key metrics, warning/error counts (path= required). "
        "Always call action='list' first to discover available log file paths before reading. "
        "Known log files: logs/host_download.log, logs/host_download_failures.log, "
        "logs/index_individual_host_sequences.log, logs/create_host_status_report.log, "
        "logs/merge_phage_fasta.log, logs/merge_protein_fasta.log, "
        "logs/index_phage_sequences.log, logs/index_protein_sequences.log, "
        "logs/create_host_mapping.log."
    )
    args_schema: Type[BaseModel] = LogExplorerInput

    def _run(self, action: str, path: Optional[str] = None,
             pattern: Optional[str] = None, context_lines: int = 2,
             n_lines: int = _DEFAULT_N_LINES,
             start_line: Optional[int] = None,
             end_line: Optional[int] = None,
             level: Optional[str] = None) -> str:
        try:
            target = _safe_resolve(path)
        except ValueError as exc:
            return f"Security error: {exc}"

        action = action.strip().lower()

        if action == "list":
            return _list_dir(target)

        if action == "read":
            if not path:
                return (
                    "path is required for action='read'. "
                    "Call action='list' first to see available log files, "
                    "then provide a specific file path.\n\n"
                    + _list_dir(target)
                )
            if target.is_dir():
                return (
                    f"'{path}' is a directory. "
                    "Provide a specific file path for action='read'.\n\n"
                    + _list_dir(target)
                )
            return _read_file(target, start_line=start_line, end_line=end_line)

        if action == "head":
            if not path:
                return (
                    "path is required for action='head'. "
                    "Call action='list' first to see available log files, "
                    "then provide a specific file path.\n\n"
                    + _list_dir(target)
                )
            if target.is_dir():
                return (
                    f"'{path}' is a directory. "
                    "Provide a specific file path for action='head'.\n\n"
                    + _list_dir(target)
                )
            return _head_file(target, n_lines)

        if action == "tail":
            if not path:
                return (
                    "path is required for action='tail'. "
                    "Call action='list' first to see available log files, "
                    "then provide a specific file path.\n\n"
                    + _list_dir(target)
                )
            if target.is_dir():
                return (
                    f"'{path}' is a directory. "
                    "Provide a specific file path for action='tail'.\n\n"
                    + _list_dir(target)
                )
            return _tail_file(target, n_lines)

        if action == "search":
            if not pattern:
                return "pattern is required for action='search'."
            if target.is_dir():
                return _search_dir(target, pattern, context_lines)
            return _search_file(target, pattern, context_lines)

        if action == "filter_level":
            if not path:
                return (
                    "path is required for action='filter_level'. "
                    "Call action='list' first to see available log files, "
                    "then provide a specific file path.\n\n"
                    + _list_dir(target)
                )
            if target.is_dir():
                return (
                    f"'{path}' is a directory. "
                    "Provide a specific file path for action='filter_level'.\n\n"
                    + _list_dir(target)
                )
            min_level = (level or "WARNING").upper()
            if min_level not in _LEVEL_PRIORITY:
                return (
                    f"Unknown level '{min_level}'. "
                    "Valid levels: DEBUG, INFO, WARNING, ERROR."
                )
            return _filter_by_level(target, min_level)

        if action == "summary":
            if not path:
                return (
                    "path is required for action='summary'. "
                    "Call action='list' first to see available log files, "
                    "then provide a specific file path.\n\n"
                    + _list_dir(target)
                )
            if target.is_dir():
                return (
                    f"'{path}' is a directory. "
                    "Provide a specific file path for action='summary'.\n\n"
                    + _list_dir(target)
                )
            return _summarise_log(target)

        return (
            f"Unknown action '{action}'. "
            "Valid actions are: 'list', 'read', 'head', 'tail', 'search', "
            "'filter_level', 'summary'."
        )

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

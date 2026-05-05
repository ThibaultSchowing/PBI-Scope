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

Input schema (JSON string)
--------------------------
``action`` – one of ``"list"``, ``"read"``, ``"head"``, ``"tail"``,
             ``"search"`` (required).
``path``   – relative path inside the log root, e.g. ``"logs/rule.log"``
             (required for ``read``, ``head``, ``tail``; optional for
             ``list`` to scope the listing to a subdirectory; optional
             for ``search`` — omit or point to a directory to search all
             log files recursively).
``pattern`` – substring or regex to search for (required for ``search``).
``context_lines`` – number of lines of context around each match for
                    ``search`` (default 2, max 10).
``n_lines`` – number of lines to return for ``head`` / ``tail``
              (default 50, max 500).
``start_line`` – 1-based first line to return for ``read`` (optional).
``end_line``   – 1-based last line to return for ``read`` (optional).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

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
            'Action to perform: "list", "read", "head", "tail", or "search".'
        )
    )
    path: Optional[str] = Field(
        default=None,
        description=(
            "Relative path inside the pipeline-logs directory. "
            'Required for "read", "head", and "tail"; optional for "list" '
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


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class LogExplorerTool(BaseTool):
    """Browse and search pipeline log files in the bind-mounted log directory."""

    name: str = "log_explorer"
    description: str = (
        "Browse and search pipeline LOG FILES only — do NOT use this for phage/protein/database data queries "
        "(use duckdb_query for those). "
        "action='list': list log files (path= optional for subdirectory; omit to see all logs). "
        "action='read': read a log file (path= required; use start_line/end_line for a specific section). "
        "action='head': show the first n_lines lines of a log file (path= required, default n_lines=50). "
        "action='tail': show the last n_lines lines of a log file (path= required, default n_lines=50). "
        "action='search': grep for a pattern in log files (pattern= required; path= optional — omit or give a "
        "directory path to search ALL log files recursively). "
        "Always call action='list' first to discover available log file paths before reading."
    )
    args_schema: Type[BaseModel] = LogExplorerInput

    def _run(self, action: str, path: Optional[str] = None,
             pattern: Optional[str] = None, context_lines: int = 2,
             n_lines: int = _DEFAULT_N_LINES,
             start_line: Optional[int] = None,
             end_line: Optional[int] = None) -> str:
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

        return (
            f"Unknown action '{action}'. "
            "Valid actions are: 'list', 'read', 'head', 'tail', 'search'."
        )

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

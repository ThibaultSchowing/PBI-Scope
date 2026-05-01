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
``action`` – one of ``"list"``, ``"read"``, ``"search"`` (required).
``path``   – relative path inside the log root, e.g. ``"logs/rule.log"``
             (required for ``read`` and ``search``; optional for ``list``
             to scope the listing to a subdirectory).
``pattern`` – substring or regex to search for (required for ``search``).
``context_lines`` – number of lines of context around each match for
                    ``search`` (default 2, max 10).
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class LogExplorerInput(BaseModel):
    action: str = Field(
        description='Action to perform: "list", "read", or "search".'
    )
    path: Optional[str] = Field(
        default=None,
        description=(
            "Relative path inside the pipeline-logs directory. "
            'Required for "read" and "search"; optional for "list" '
            "(omit or use empty string to list the root)."
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
    """Return a formatted directory listing."""
    if not target.exists():
        return f"Path not found: {target}"

    entries: list[str] = []
    for entry in sorted(target.iterdir()):
        if entry.is_dir():
            entries.append(f"[dir]  {entry.name}/")
        else:
            size_kb = entry.stat().st_size / 1024
            entries.append(f"[file] {entry.name}  ({size_kb:.1f} KB)")

    if not entries:
        return f"Directory is empty: {target}"

    return "\n".join([f"Contents of {target}:", *entries])


def _read_file(target: Path) -> str:
    """Read up to _MAX_BYTES from *target*."""
    if not target.exists():
        return f"File not found: {target}"
    if target.is_dir():
        return f"'{target}' is a directory — use action='list' to browse it."

    size = target.stat().st_size
    truncated = size > _MAX_BYTES

    with target.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)

    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += (
            f"\n\n[TRUNCATED — showing first {_MAX_BYTES // 1024} KB "
            f"of {size // 1024} KB total]"
        )
    return text


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


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class LogExplorerTool(BaseTool):
    """Browse and search pipeline log files in the bind-mounted log directory."""

    name: str = "log_explorer"
    description: str = (
        "Browse and search pipeline log files. "
        "Use action='list' to see files (optionally in a subdirectory via path=), "
        "action='read' to read a specific file (path= required), "
        "action='search' to grep for a pattern (path= and pattern= required). "
        "Input must be a JSON object with keys: action, path (optional), "
        "pattern (for search), context_lines (optional, default 2)."
    )
    args_schema: Type[BaseModel] = LogExplorerInput

    def _run(self, action: str, path: Optional[str] = None,
             pattern: Optional[str] = None, context_lines: int = 2) -> str:
        try:
            target = _safe_resolve(path)
        except ValueError as exc:
            return f"Security error: {exc}"

        action = action.strip().lower()

        if action == "list":
            return _list_dir(target)

        if action == "read":
            if path is None:
                return "path is required for action='read'."
            return _read_file(target)

        if action == "search":
            if path is None:
                return "path is required for action='search'."
            if not pattern:
                return "pattern is required for action='search'."
            return _search_file(target, pattern, context_lines)

        return (
            f"Unknown action '{action}'. "
            "Valid actions are: 'list', 'read', 'search'."
        )

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

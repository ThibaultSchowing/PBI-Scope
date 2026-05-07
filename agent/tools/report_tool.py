"""
report_tool.py
==============

LangChain tool for browsing and summarising pipeline report files that are
bind-mounted into the agent container at ``/pipeline-logs/reports``.

The pipeline stores two types of reports:

* **HTML reports** (``*.html``) – human-readable data-quality summaries for
  each downloaded metadata feature (phage metadata, proteins, CRISPR arrays,
  etc.) and the database validation.
* **CSV reports** (``*.csv``) – machine-readable tabular summaries such as
  ``host_status_report.csv``.

Security guarantees
-------------------
* All file paths are resolved and verified to stay within the reports directory.
* Files are never written.
* Reads are capped at ``AGENT_MAX_LOG_SIZE_KB`` kilobytes.

Input schema (JSON string)
--------------------------
``action`` – one of ``"list"``, ``"summary"``, ``"read"`` (required).
``name``   – report file name (e.g. ``"host_status_report.csv"``) — required
             for ``"summary"`` and ``"read"``.
``filter`` – optional substring to filter rows/lines (for CSV ``"summary"``).
``n_rows`` – maximum number of rows to show for CSV ``"summary"``
             (default 50, max 500).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LOG_ROOT = Path(os.environ.get("PBI_LOGS_DIR", "/pipeline-logs"))
_REPORTS_DIR = _LOG_ROOT / "reports"
_MAX_BYTES = int(os.environ.get("AGENT_MAX_LOG_SIZE_KB", "512")) * 1024
_DEFAULT_N_ROWS = 50
_MAX_N_ROWS = 500


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class PipelineReportInput(BaseModel):
    action: str = Field(
        description=(
            "Action to perform:\n"
            "  'list'    – list all available report files.\n"
            "  'summary' – read and display a report file. CSV reports are shown as "
            "a Markdown table; HTML reports show only the plain-text content.\n"
            "  'read'    – read the raw content of a report file (truncated to the "
            "configured size limit)."
        )
    )
    name: Optional[str] = Field(
        default=None,
        description=(
            "File name inside the reports directory (e.g. 'host_status_report.csv' "
            "or 'database_validation.html'). Required for 'summary' and 'read'."
        ),
    )
    filter: Optional[str] = Field(
        default=None,
        description=(
            "Optional case-insensitive substring filter. "
            "For CSV 'summary', only rows where any column contains this value "
            "are returned."
        ),
    )
    n_rows: int = Field(
        default=_DEFAULT_N_ROWS,
        description=(
            f"Maximum number of rows to display for CSV 'summary' "
            f"(default {_DEFAULT_N_ROWS}, max {_MAX_N_ROWS})."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_resolve(name: Optional[str]) -> Path:
    """Resolve *name* under the reports directory and verify it stays inside."""
    if not name:
        return _REPORTS_DIR.resolve()
    resolved = (_REPORTS_DIR / name).resolve()
    root = _REPORTS_DIR.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path '{name}' resolves outside the reports directory. "
            "Only files within /pipeline-logs/reports/ are accessible."
        )
    return resolved


def _list_reports() -> str:
    """Return a formatted listing of available report files."""
    if not _REPORTS_DIR.exists():
        return (
            "Reports directory not found. "
            "The pipeline may not have produced any reports yet."
        )
    entries = sorted(
        e for e in _REPORTS_DIR.iterdir() if e.is_file()
    )
    if not entries:
        return "No report files found in the reports directory."
    lines = [f"Available reports in {_REPORTS_DIR}:", ""]
    for entry in entries:
        size_kb = entry.stat().st_size / 1024
        lines.append(f"  {entry.name}  ({size_kb:.1f} KB)")
    return "\n".join(lines)


def _summarise_report(path: Path, filter_str: Optional[str],
                      n_rows: int) -> str:
    """Summarise a report file (CSV → Markdown table; HTML → text extract)."""
    if not path.exists():
        return (
            f"Report not found: {path.name!r}.\n"
            "Use action='list' to see available reports."
        )
    if path.is_dir():
        return f"'{path.name}' is a directory, not a report file."

    suffix = path.suffix.lower()
    n_rows = min(max(n_rows, 1), _MAX_N_ROWS)

    if suffix == ".csv":
        try:
            import pandas as pd  # noqa: PLC0415

            df = pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            return f"Error reading {path.name}: {exc}"

        if df.empty:
            return f"{path.name} is empty."

        if filter_str:
            mask = df.apply(
                lambda col: col.astype(str).str.contains(
                    filter_str, case=False, na=False
                )
            ).any(axis=1)
            df = df[mask]
            if df.empty:
                return f"No rows matching '{filter_str}' in {path.name}."

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
        return f"{path.name} — {total} row(s){note}:\n\n" + table

    # For HTML and other text formats: return raw text (truncated)
    with path.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    text = raw.decode("utf-8", errors="replace")
    size = path.stat().st_size
    truncated = size > _MAX_BYTES
    note = (
        f"\n\n[TRUNCATED — showing first {_MAX_BYTES // 1024} KB "
        f"of {size // 1024} KB. Use action='read' with start_line/end_line for more.]"
        if truncated else ""
    )
    return text + note


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class PipelineReportTool(BaseTool):
    """Browse and summarise pipeline report files (HTML and CSV)."""

    name: str = "pipeline_report"
    description: str = (
        "Access HTML and CSV REPORTS (data quality summaries, validation reports) stored in /pipeline-logs/reports/. DO NOT use log_explorer for reports. "
        "action='list': list all available reports (HTML data-quality summaries and CSV tables). "
        "action='summary': display a report — CSV reports are shown as Markdown tables, "
        "HTML reports as plain text (name= required, e.g. 'host_status_report.csv'). "
        "action='read': read the raw content of a report file (name= required). "
        "Optional filter= restricts CSV rows to those containing a substring; "
        "n_rows= limits the number of CSV rows shown (default 50, max 500)."
    )
    args_schema: Type[BaseModel] = PipelineReportInput

    def _run(self, action: str, name: Optional[str] = None,
             filter: Optional[str] = None,  # noqa: A002
             n_rows: int = _DEFAULT_N_ROWS) -> str:
        action = action.strip().lower()

        try:
            target = _safe_resolve(name)
        except ValueError as exc:
            return f"Security error: {exc}"

        if action == "list":
            return _list_reports()

        if action in ("summary", "read"):
            if not name:
                return (
                    "name is required for action='summary'/'read'. "
                    "Use action='list' to see available report files.\n\n"
                    + _list_reports()
                )
            if action == "summary":
                return _summarise_report(target, filter_str=filter, n_rows=n_rows)
            # 'read': return raw content
            if not target.exists():
                return (
                    f"Report not found: {name!r}.\n"
                    "Use action='list' to see available reports."
                )
            if target.is_dir():
                return f"'{name}' is a directory, not a report file."
            with target.open("rb") as fh:
                raw = fh.read(_MAX_BYTES)
            text = raw.decode("utf-8", errors="replace")
            size = target.stat().st_size
            if size > _MAX_BYTES:
                text += (
                    f"\n\n[TRUNCATED — showing first {_MAX_BYTES // 1024} KB "
                    f"of {size // 1024} KB total.]"
                )
            return text

        return (
            f"Unknown action '{action}'. "
            "Valid actions: 'list', 'summary', 'read'."
        )

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

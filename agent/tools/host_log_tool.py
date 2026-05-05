"""
host_log_tool.py
================

LangChain tool for querying host-genome retrieval log files produced by
the PBI pipeline.

The pipeline generates several host-related outputs under the log root:

* ``logs/host_download.log``          – general download progress / info
* ``logs/host_download_failures.log`` – one line per failed host
* ``logs/host_fasta_qc.csv``          – FASTA quality-control results (CSV)
* ``logs/create_host_mapping.log``    – host-to-FASTA mapping creation log
* ``reports/host_status_report.csv``  – per-(Phage_ID, Host_Token) status (CSV)

Security guarantees
-------------------
* All reads are restricted to the configured log root (path-traversal safe).
* Files are never written.
* Reads are capped at ``AGENT_MAX_LOG_SIZE_KB`` kilobytes.

Input schema (JSON string)
--------------------------
``action`` – one of ``"list_failures"``, ``"get_status"``, ``"get_fasta_qc"``,
             ``"get_download_log"`` (required).
``n_lines`` – number of tail lines for ``"get_download_log"``
              (default 100, max 500).
``filter``  – optional substring filter applied to rows / lines returned.
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
_MAX_BYTES = int(os.environ.get("AGENT_MAX_LOG_SIZE_KB", "512")) * 1024
_MAX_N_LINES = 500
_DEFAULT_TAIL_LINES = 100

# Known log paths (relative to log root)
_HOST_DOWNLOAD_LOG = "logs/host_download.log"
_HOST_FAILURE_LOG = "logs/host_download_failures.log"
_HOST_FASTA_QC_LOG = "logs/host_fasta_qc.csv"
_HOST_STATUS_REPORT = "reports/host_status_report.csv"
_HOST_MAPPING_LOG = "logs/create_host_mapping.log"


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class HostRetrievalLogInput(BaseModel):
    action: str = Field(
        description=(
            "Action to perform:\n"
            "  'list_failures'   – list host species that failed to be retrieved "
            "(reads host_download_failures.log and/or host_status_report.csv).\n"
            "  'get_status'      – summarise the host_status_report.csv table "
            "(overall retrieval / download / QC results per phage-host pair).\n"
            "  'get_fasta_qc'    – show the FASTA QC results (host_fasta_qc.csv).\n"
            "  'get_download_log'– show recent lines from the host_download.log."
        )
    )
    n_lines: int = Field(
        default=_DEFAULT_TAIL_LINES,
        description=(
            f"Number of tail lines to return for 'get_download_log' "
            f"(default {_DEFAULT_TAIL_LINES}, max {_MAX_N_LINES})."
        ),
    )
    filter: Optional[str] = Field(
        default=None,
        description=(
            "Optional case-insensitive substring to filter rows / lines. "
            "For 'list_failures', filters on host name or token. "
            "For 'get_status', filters on any column value."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tail_text(path: Path, n_lines: int) -> str:
    """Return the last *n_lines* lines from *path*."""
    if not path.exists():
        return f"File not found: {path.relative_to(_LOG_ROOT)}"
    size = path.stat().st_size
    with path.open("rb") as fh:
        raw = fh.read(_MAX_BYTES)
    lines = raw.decode("utf-8", errors="replace").splitlines()
    selected = lines[-n_lines:]
    header = (
        f"[Last {len(selected)} of {len(lines)} lines "
        f"in {path.relative_to(_LOG_ROOT)} ({size // 1024} KB total)]\n\n"
    )
    return header + "\n".join(selected)


def _read_csv_summary(path: Path, filter_str: Optional[str] = None,
                      max_rows: int = 100) -> str:
    """Read a CSV log file and return a Markdown table, optionally filtered."""
    if not path.exists():
        return f"File not found: {path.relative_to(_LOG_ROOT)}"

    try:
        import pandas as pd  # noqa: PLC0415

        df = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        return f"Error reading {path.relative_to(_LOG_ROOT)}: {exc}"

    if df.empty:
        return f"{path.relative_to(_LOG_ROOT)} is empty — no records."

    if filter_str:
        mask = df.apply(
            lambda col: col.astype(str).str.contains(filter_str, case=False, na=False)
        ).any(axis=1)
        df = df[mask]
        if df.empty:
            return (
                f"No rows matching filter '{filter_str}' "
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
    return (
        f"{path.relative_to(_LOG_ROOT)} — {total} row(s){note}:\n\n"
        + table
    )


def _list_failures(filter_str: Optional[str] = None) -> str:
    """Return hosts that failed retrieval."""
    # Prefer structured status report
    status_path = _LOG_ROOT / _HOST_STATUS_REPORT
    if status_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415

            df = pd.read_csv(status_path)
            # Identify failure rows using common column name patterns
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
                        f"({len(failed)} row(s) shown, up to 200):\n\n"
                        + table
                    )
                return (
                    "No failed hosts found in host_status_report.csv"
                    + (f" matching filter '{filter_str}'" if filter_str else "")
                    + "."
                )
        except Exception:  # noqa: BLE001
            pass

    # Fall back to plain-text failure log
    failure_path = _LOG_ROOT / _HOST_FAILURE_LOG
    if failure_path.exists():
        with failure_path.open("rb") as fh:
            raw = fh.read(_MAX_BYTES)
        lines = raw.decode("utf-8", errors="replace").splitlines()
        if filter_str:
            lines = [l for l in lines if filter_str.lower() in l.lower()]
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
        "The pipeline may not have run yet or recorded no failures. "
        f"Expected files: {_HOST_STATUS_REPORT} or {_HOST_FAILURE_LOG}."
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class HostRetrievalLogTool(BaseTool):
    """Query host-genome retrieval log files from the PBI pipeline."""

    name: str = "host_retrieval_log"
    description: str = (
        "Query PBI pipeline logs specifically about host genome retrieval. "
        "action='list_failures': list host species that failed to be downloaded/indexed "
        "(reads host_download_failures.log and host_status_report.csv). "
        "action='get_status': full host status table from host_status_report.csv "
        "(per-phage host resolution, download, and QC results). "
        "action='get_fasta_qc': FASTA quality-control results for host genomes "
        "(host_fasta_qc.csv — duplicate headers, identical sequences, etc.). "
        "action='get_download_log': recent lines from the general host download log "
        "(n_lines controls how many tail lines to return; default 100, max 500). "
        "Optional filter= restricts rows/lines to those containing a given substring."
    )
    args_schema: Type[BaseModel] = HostRetrievalLogInput

    def _run(self, action: str, n_lines: int = _DEFAULT_TAIL_LINES,
             filter: Optional[str] = None) -> str:  # noqa: A002
        action = action.strip().lower()
        n_lines = min(max(n_lines, 1), _MAX_N_LINES)

        if action == "list_failures":
            return _list_failures(filter_str=filter)

        if action == "get_status":
            return _read_csv_summary(
                _LOG_ROOT / _HOST_STATUS_REPORT,
                filter_str=filter,
            )

        if action == "get_fasta_qc":
            return _read_csv_summary(
                _LOG_ROOT / _HOST_FASTA_QC_LOG,
                filter_str=filter,
            )

        if action == "get_download_log":
            result = _tail_text(_LOG_ROOT / _HOST_DOWNLOAD_LOG, n_lines)
            if filter:
                lines = result.splitlines()
                # Keep header line(s) plus matching lines
                header = [line for line in lines[:2] if line.startswith("[")]
                body = [line for line in lines if filter.lower() in line.lower()]
                result = "\n".join(header + body) if body else (
                    f"No lines matching '{filter}' in host_download.log."
                )
            return result

        return (
            f"Unknown action '{action}'. "
            "Valid actions: 'list_failures', 'get_status', 'get_fasta_qc', 'get_download_log'."
        )

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

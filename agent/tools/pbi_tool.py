"""
pbi_tool.py
===========

LangChain tool that exposes a curated, whitelist-only subset of the PBI
Python package (``pbi.SequenceRetriever``) to the LangChain agent.

Streaming datasets (``PhageHostStreamingDataset`` / ``PhageHostIndexedDataset``)
are intentionally excluded — they load PyTorch and iterate over the entire
database, which is unsuitable for an interactive chat context.

Input schema (JSON string)
--------------------------
``action`` – one of the whitelisted actions (see WHITELISTED_ACTIONS below).
``id``     – phage or protein accession ID (required for *_by_id actions).

Whitelisted actions
-------------------
``get_stats``          – return overall database statistics.
``get_phage_by_id``    – fetch metadata + sequence for a single phage.
``get_protein_by_id``  – fetch metadata + sequence for a single protein.
``list_hosts``         – return a sample of host organisms from the database.
``list_failed_hosts``  – return hosts that failed to be retrieved (from pipeline logs).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_APP_SRC_PATH = "/app/src"

WHITELISTED_ACTIONS = frozenset(
    ["get_stats", "get_phage_by_id", "get_protein_by_id", "list_hosts", "list_failed_hosts"]
)

_HOST_SAMPLE_LIMIT = 50


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class PBIRetrieverInput(BaseModel):
    action: str = Field(
        description=(
            f"Action to perform. One of: {', '.join(sorted(WHITELISTED_ACTIONS))}."
        )
    )
    record_id: Optional[str] = Field(
        default=None,
        description="Phage or protein accession ID (required for *_by_id actions).",
    )
    error: Optional[str] = Field(
        default=None,
        description=(
            "Optional error filter for list_hosts. "
            "Use 'failed_to_retrieve' to list only hosts that could not be downloaded."
        ),
    )


# ---------------------------------------------------------------------------
# Lazy retriever initialisation with loading-state tracking
# ---------------------------------------------------------------------------

_retriever = None
_retriever_loading: bool = False
_retriever_error: Optional[str] = None
_retriever_lock = threading.Lock()


def preload_retriever() -> None:
    """
    Eagerly initialise the PBI SequenceRetriever in a background thread.

    Loading the large database files can take several minutes; calling this
    at application startup means the connection is ready (or has a clear
    error) before the first user query arrives.  Safe to call multiple times.
    """
    global _retriever, _retriever_loading, _retriever_error  # noqa: PLW0603

    with _retriever_lock:
        if _retriever is not None or _retriever_loading:
            return
        _retriever_loading = True

    logger.info("Pre-loading PBI SequenceRetriever (this may take several minutes) …")
    try:
        import sys

        if _APP_SRC_PATH not in sys.path:
            sys.path.insert(0, _APP_SRC_PATH)

        from pbi import quick_connect  # type: ignore[import]

        ret = quick_connect()
        with _retriever_lock:
            _retriever = ret
            _retriever_error = None
        logger.info("PBI SequenceRetriever ready.")
    except Exception as exc:  # noqa: BLE001
        with _retriever_lock:
            _retriever_error = str(exc)
        logger.error("PBI retriever preload failed: %s", exc)
    finally:
        with _retriever_lock:
            _retriever_loading = False


def _get_retriever():
    """Return the module-level SequenceRetriever, or (None, error_message)."""
    if _retriever is not None:
        return _retriever, None
    if _retriever_loading:
        return None, (
            "⏳ The database is still loading — this can take up to 5 minutes "
            "on first start. Please try again in a moment."
        )
    if _retriever_error:
        return None, f"Could not connect to PBI database: {_retriever_error}"
    # preload_retriever() was never called — trigger a synchronous on-demand
    # load, honouring the same lock/state to avoid concurrent connection attempts.
    with _retriever_lock:
        # Re-check under the lock in case another thread just finished loading.
        if _retriever is not None:
            return _retriever, None
        if _retriever_loading:
            return None, (
                "⏳ The database is still loading — this can take up to 5 minutes "
                "on first start. Please try again in a moment."
            )
    # Delegate to preload_retriever which handles all locking internally,
    # then return whatever state was set.
    preload_retriever()
    with _retriever_lock:
        if _retriever is not None:
            return _retriever, None
        return None, f"Could not connect to PBI database: {_retriever_error or 'unknown error'}"


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _get_stats() -> str:
    retriever, err = _get_retriever()
    if err:
        return err

    try:
        stats = retriever.get_stats()
        return json.dumps(stats, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        return f"Error retrieving stats: {exc}"


def _get_phage_by_id(phage_id: str) -> str:
    retriever, err = _get_retriever()
    if err:
        return err

    try:
        df = retriever.conn.execute(
            "SELECT * FROM fact_phages WHERE Phage_ID = ? LIMIT 1",
            [phage_id],
        ).fetchdf()
        if df.empty:
            return f"No phage found with ID '{phage_id}'."
        record = df.iloc[0].to_dict()
        return json.dumps(record, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        return f"Error retrieving phage record: {exc}"


def _get_protein_by_id(protein_id: str) -> str:
    retriever, err = _get_retriever()
    if err:
        return err

    try:
        df = retriever.conn.execute(
            "SELECT * FROM dim_proteins WHERE Protein_ID = ? LIMIT 1",
            [protein_id],
        ).fetchdf()
        if df.empty:
            return f"No protein found with ID '{protein_id}'."
        record = df.iloc[0].to_dict()
        return json.dumps(record, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        return f"Error retrieving protein record: {exc}"


def _list_hosts() -> str:
    retriever, err = _get_retriever()
    if err:
        return err

    try:
        query = (
            f"SELECT DISTINCT Host_ID, Host_Name "
            f"FROM dim_hosts LIMIT {_HOST_SAMPLE_LIMIT}"
        )
        df = retriever.conn.execute(query).fetchdf()
        if df.empty:
            return "No host organisms found in the database."
        try:
            return df.to_markdown(index=False)
        except ImportError:
            return df.to_string(index=False)
    except Exception as exc:  # noqa: BLE001
        # Fallback: try alternate column names
        try:
            query = (
                f"SELECT * FROM dim_hosts LIMIT {_HOST_SAMPLE_LIMIT}"
            )
            df = retriever.conn.execute(query).fetchdf()
            if df.empty:
                return "No host organisms found in the database."
            try:
                return df.to_markdown(index=False)
            except ImportError:
                return df.to_string(index=False)
        except Exception as exc2:  # noqa: BLE001
            return f"Error listing hosts: {exc2}"


_LOG_ROOT = Path(os.environ.get("PBI_LOGS_DIR", "/pipeline-logs"))
_HOST_FAILURE_LOG = "logs/host_download_failures.log"
_HOST_STATUS_REPORT = "reports/host_status_report.csv"
_MAX_FAILURE_LINES = 200


def _list_failed_hosts() -> str:
    """Return host species that failed to be retrieved, from pipeline log files."""
    # Try the structured host status report first (CSV, most informative)
    status_path = _LOG_ROOT / _HOST_STATUS_REPORT
    if status_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415

            df = pd.read_csv(status_path)
            # Look for columns indicating failure
            fail_cols = [
                c for c in df.columns
                if any(kw in c.lower() for kw in ("fail", "error", "missing", "unresolved", "status"))
            ]
            if fail_cols:
                status_col = fail_cols[0]
                failed = df[df[status_col].astype(str).str.lower().str.contains(
                    r"fail|error|missing|unresolved|not_found|not found", na=False
                )]
                if not failed.empty:
                    try:
                        result = failed.head(_HOST_SAMPLE_LIMIT).to_markdown(index=False)
                    except ImportError:
                        result = failed.head(_HOST_SAMPLE_LIMIT).to_string(index=False)
                    return (
                        f"Hosts with failures from {_HOST_STATUS_REPORT} "
                        f"({len(failed)} row(s) shown, up to {_HOST_SAMPLE_LIMIT}):\n\n"
                        + result
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not parse host status report: %s", exc)

    # Fall back to the plain-text failure log
    failure_path = _LOG_ROOT / _HOST_FAILURE_LOG
    if failure_path.exists():
        try:
            with failure_path.open("rb") as fh:
                raw = fh.read()
            lines = raw.decode("utf-8", errors="replace").splitlines()
            if not lines:
                return "Host failure log is empty — no failed hosts recorded."
            selected = lines[-_MAX_FAILURE_LINES:]
            header = (
                f"Last {len(selected)} line(s) from {_HOST_FAILURE_LOG} "
                f"({failure_path.stat().st_size // 1024} KB total):\n\n"
            )
            return header + "\n".join(selected)
        except Exception as exc:  # noqa: BLE001
            return f"Error reading host failure log: {exc}"

    return (
        "Host failure log not found. "
        "The pipeline may not have run yet, or no host failures were recorded. "
        f"Expected log at: {_HOST_FAILURE_LOG}"
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class PBIRetrieverTool(BaseTool):
    """Access PBI database statistics and individual phage/protein records."""

    name: str = "pbi_retriever"
    description: str = (
        "Access PBI phage-bacteria interaction data using curated actions. "
        "Use action='get_stats' for overall database statistics, "
        "action='get_phage_by_id' (with record_id=) to look up a specific phage record, "
        "action='get_protein_by_id' (with record_id=) for a specific protein record, "
        "action='list_hosts' to see available host organisms in the database, "
        "action='list_failed_hosts' to see host species that failed to be retrieved "
        "(reads from pipeline failure logs — does not require a DB connection). "
        "Input must be a JSON object with keys: action, record_id (optional), error (optional)."
    )
    args_schema: Type[BaseModel] = PBIRetrieverInput

    def _run(self, action: str, record_id: Optional[str] = None,
             error: Optional[str] = None) -> str:
        action = action.strip().lower()

        if action not in WHITELISTED_ACTIONS:
            return (
                f"Unknown action '{action}'. "
                f"Valid actions: {', '.join(sorted(WHITELISTED_ACTIONS))}."
            )

        if action == "get_stats":
            return _get_stats()

        if action == "get_phage_by_id":
            if not record_id:
                return "record_id is required for action='get_phage_by_id'."
            return _get_phage_by_id(record_id)

        if action == "get_protein_by_id":
            if not record_id:
                return "record_id is required for action='get_protein_by_id'."
            return _get_protein_by_id(record_id)

        if action == "list_hosts":
            # When the caller requests failed hosts via the error filter, delegate
            # to the log-based implementation instead of querying the database.
            if error and "fail" in error.lower():
                return _list_failed_hosts()
            return _list_hosts()

        if action == "list_failed_hosts":
            return _list_failed_hosts()

        return f"Unhandled action '{action}'."

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

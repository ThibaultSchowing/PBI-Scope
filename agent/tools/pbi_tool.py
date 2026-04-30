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
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

WHITELISTED_ACTIONS = frozenset(
    ["get_stats", "get_phage_by_id", "get_protein_by_id", "list_hosts"]
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


# ---------------------------------------------------------------------------
# Lazy retriever initialisation
# ---------------------------------------------------------------------------

_retriever = None


def _get_retriever():
    """Return a module-level SequenceRetriever, initialised on first call."""
    global _retriever  # noqa: PLW0603
    if _retriever is None:
        try:
            import sys

            # Ensure the pbi package installed in /app is importable
            app_src = "/app/src"
            if app_src not in sys.path:
                sys.path.insert(0, app_src)

            from pbi import quick_connect  # type: ignore[import]

            _retriever = quick_connect()
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
    return _retriever, None


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

def _get_stats() -> str:
    retriever, err = _get_retriever()
    if err:
        return f"Could not connect to PBI database: {err}"

    try:
        stats = retriever.get_stats()
        return json.dumps(stats, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        return f"Error retrieving stats: {exc}"


def _get_phage_by_id(phage_id: str) -> str:
    retriever, err = _get_retriever()
    if err:
        return f"Could not connect to PBI database: {err}"

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
        return f"Could not connect to PBI database: {err}"

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
        return f"Could not connect to PBI database: {err}"

    try:
        query = (
            f"SELECT DISTINCT Host_ID, Host_Name "
            f"FROM dim_hosts LIMIT {_HOST_SAMPLE_LIMIT}"
        )
        df = retriever.conn.execute(query).fetchdf()
        if df.empty:
            return "No host organisms found in the database."
        return df.to_markdown(index=False)
    except Exception as exc:  # noqa: BLE001
        # Fallback: try alternate column names
        try:
            query = (
                f"SELECT * FROM dim_hosts LIMIT {_HOST_SAMPLE_LIMIT}"
            )
            df = retriever.conn.execute(query).fetchdf()
            if df.empty:
                return "No host organisms found in the database."
            return df.to_markdown(index=False)
        except Exception as exc2:  # noqa: BLE001
            return f"Error listing hosts: {exc2}"


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
        "action='list_hosts' to see available host organisms. "
        "Input must be a JSON object with keys: action, record_id (optional)."
    )
    args_schema: Type[BaseModel] = PBIRetrieverInput

    def _run(self, action: str, record_id: Optional[str] = None) -> str:
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
            return _list_hosts()

        return f"Unhandled action '{action}'."

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

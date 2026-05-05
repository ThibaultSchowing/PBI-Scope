"""
routing_tool.py
===============

LangChain tool that acts as a lightweight query router / tool selector for
the PBI agent.

When the agent is uncertain which tool or action best answers a user
question, it can call this tool with the user's question to receive a
structured routing recommendation — the suggested tool name, action, and
a short rationale.

The routing logic uses keyword heuristics and does NOT call any external
service, so it runs instantly.

Input schema (JSON string)
--------------------------
``query`` – the user's natural-language question (required).
"""

from __future__ import annotations

import re
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Routing rules (evaluated in order — first match wins)
# ---------------------------------------------------------------------------

_RULES: list[tuple[list[str], str, str, str]] = [
    # (keywords, tool, action, rationale)

    # SQL / database questions
    (
        ["how many phage", "count phage", "number of phage", "total phage",
         "how many protein", "count protein", "number of protein",
         "how many host", "count host", "list all phage", "show all phage",
         "find phage", "phage with", "protein with", "host with",
         "show me phage", "list phage", "phage from", "phage in the",
         "list host", "show host", "host in the",
         "select ", "sql ", "query ", "table ", "column ",
         "accession", "crispr", "virulent", "transmembrane",
         "anti-crispr", "trna", "tmrna", "resistance gene",
         "phage id", "protein id", "host id", "phage_id", "protein_id",
         "database schema", "show tables", "describe table"],
        "duckdb_query",
        "query='SELECT ...'",
        "Questions about phage/protein/host data, counts, metadata, or any structured "
        "database content should be answered with a SQL SELECT query.",
    ),

    # Host retrieval failures / QC
    (
        ["host fail", "failed host", "host download fail", "could not download",
         "host retrieval fail", "failed to retrieve", "failed to download host",
         "host genome fail", "host not found", "host missing",
         "fasta qc", "fasta quality", "duplicate header", "identical sequence",
         "host status", "host indexed", "host rejected",
         "which host", "what host fail"],
        "host_retrieval_log",
        "action='list_failures' or action='get_status'",
        "Questions about host genome retrieval failures or FASTA QC should use "
        "the host_retrieval_log tool.",
    ),

    # Host mapping log
    (
        ["host mapping", "mapping creation", "host fasta mapping",
         "create_host_mapping", "how many host fasta", "host fasta file"],
        "host_retrieval_log",
        "action='get_host_mapping_log'",
        "Questions about the host mapping creation process or counts of mapped "
        "FASTA files should use the host_retrieval_log tool with "
        "action='get_host_mapping_log'.",
    ),

    # Pipeline reports
    (
        ["report", "html report", "csv report", "data quality", "pipeline report",
         "database validation", "validation report", "summary report"],
        "pipeline_report",
        "action='list' then action='summary'",
        "Questions about pipeline HTML/CSV reports should use the "
        "pipeline_report tool.",
    ),

    # Log errors / warnings (generic)
    (
        ["error in log", "warning in log", "what went wrong", "pipeline error",
         "pipeline warning", "pipeline fail", "pipeline problem",
         "log error", "log warning", "step fail", "step error",
         "merge fail", "index fail", "download fail",
         "index phage", "index protein", "merge phage", "merge protein",
         "phage fasta merge", "protein fasta merge",
         "index_phage_sequences", "index_protein_sequences",
         "merge_phage_fasta", "merge_protein_fasta"],
        "log_explorer",
        "action='list', then action='summary' or action='filter_level' with level='WARNING'",
        "Questions about pipeline step errors or warnings should use the "
        "log_explorer tool — list files first, then use summary or filter_level.",
    ),

    # Generic log browsing
    (
        ["log file", "pipeline log", "show log", "read log", "what does the log",
         "what happened", "pipeline ran", "pipeline status",
         "host download log", "index log", "create host", "host index"],
        "log_explorer",
        "action='list', then action='tail' or action='summary'",
        "General log file browsing: list available files first, then read or "
        "summarise the relevant log.",
    ),

    # Database stats
    (
        ["stat", "statistics", "overview", "summary of database",
         "how large", "database size", "total records"],
        "pbi_retriever",
        "action='get_stats'",
        "Questions about overall database statistics should use the "
        "pbi_retriever tool with action='get_stats'.",
    ),

    # Individual record lookups
    (
        ["look up phage", "fetch phage", "get phage", "phage record",
         "look up protein", "fetch protein", "get protein", "protein record"],
        "pbi_retriever",
        "action='get_phage_by_id' or action='get_protein_by_id' (record_id= required)",
        "Lookups of individual phage or protein records by accession ID should "
        "use the pbi_retriever tool.",
    ),
]


def _route_query(query: str) -> dict[str, str]:
    """Return routing recommendation for *query*.

    Returns a dict with keys ``tool``, ``suggested_action``, and
    ``rationale``.  Falls back to a generic recommendation when no rule
    matches.
    """
    q_lower = query.lower()

    for keywords, tool, action, rationale in _RULES:
        if any(kw in q_lower for kw in keywords):
            return {
                "tool": tool,
                "suggested_action": action,
                "rationale": rationale,
            }

    # Fallback
    return {
        "tool": "duckdb_query or log_explorer",
        "suggested_action": (
            "duckdb_query: query='SELECT ...' for database questions; "
            "log_explorer: action='list' for pipeline log questions"
        ),
        "rationale": (
            "Could not determine the best tool from the query. "
            "If the question is about phage/protein/host data use duckdb_query; "
            "if it is about pipeline execution or log files use log_explorer."
        ),
    }


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class QueryRouterInput(BaseModel):
    query: str = Field(
        description=(
            "The user's natural-language question. "
            "The tool returns the recommended PBI agent tool and action to use."
        )
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class QueryRouterTool(BaseTool):
    """Route a user query to the most appropriate PBI agent tool."""

    name: str = "query_router"
    description: str = (
        "Use this tool ONLY when you are uncertain which other tool best answers the user's question. "
        "Provide the user's question as 'query' and the tool will return the recommended tool name, "
        "suggested action, and a rationale. "
        "Available tools to route to: duckdb_query (database/SQL), log_explorer (log files), "
        "host_retrieval_log (host genome logs), pipeline_report (HTML/CSV reports), "
        "pbi_retriever (database stats and individual records). "
        "Do NOT use this tool for every query — only when genuinely unsure."
    )
    args_schema: Type[BaseModel] = QueryRouterInput

    def _run(self, query: str) -> str:
        result = _route_query(query)
        lines = [
            "Routing recommendation:",
            f"  Recommended tool   : {result['tool']}",
            f"  Suggested action   : {result['suggested_action']}",
            f"  Rationale          : {result['rationale']}",
            "",
            "Call the recommended tool now with the appropriate parameters.",
        ]
        return "\n".join(lines)

    async def _arun(self, **kwargs: Any) -> str:  # type: ignore[override]
        return self._run(**kwargs)

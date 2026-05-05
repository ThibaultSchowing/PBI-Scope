"""
sql_tool.py
===========

LangChain tool for read-only SQL queries against the PBI DuckDB database.

Security guarantees
-------------------
* The DuckDB connection is opened in **read-only** mode — no DDL or DML
  can succeed even if the LLM generates malicious SQL.
* Only queries starting with SELECT, SHOW, DESCRIBE, or PRAGMA are accepted
  (additional defence-in-depth on top of read-only mode).
* A ``LIMIT`` clause is injected when missing, capped at
  ``AGENT_SQL_ROW_LIMIT`` rows (default 500).

Input schema (JSON string)
--------------------------
``query`` – the SQL string to execute (required).
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Optional, Type

import duckdb
import numpy as np
import pandas as pd
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_DB = (
    Path(os.environ.get("DATA_PATH", "/data/processed"))
    / "databases"
    / "phage_database_optimized.duckdb"
)
_ROW_LIMIT = int(os.environ.get("AGENT_SQL_ROW_LIMIT", "500"))

# Allowed statement prefixes (upper-cased)
_ALLOWED_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "PRAGMA")

# ---------------------------------------------------------------------------
# Shared connection state (module-level so pre-loading and the tool share it)
# ---------------------------------------------------------------------------

_shared_conn: Optional[duckdb.DuckDBPyConnection] = None
_conn_loading: bool = False
_conn_load_error: Optional[str] = None
_conn_lock = threading.Lock()


def preload_db_conn() -> None:
    """
    Open the DuckDB connection eagerly in a background thread at startup.

    Safe to call multiple times — subsequent calls are no-ops once the
    connection is established.  Errors are recorded in ``_conn_load_error``
    so the tool can surface a descriptive message instead of hanging.
    """
    global _shared_conn, _conn_loading, _conn_load_error  # noqa: PLW0603

    with _conn_lock:
        if _shared_conn is not None or _conn_loading:
            return
        _conn_loading = True

    logger.info("Pre-loading DuckDB connection from %s …", _DEFAULT_DB)
    try:
        conn = duckdb.connect(str(_DEFAULT_DB), read_only=True)
        with _conn_lock:
            _shared_conn = conn
            _conn_load_error = None
        logger.info("DuckDB connection ready.")
    except FileNotFoundError:
        with _conn_lock:
            _conn_load_error = "not_found"
        logger.warning("DuckDB file not found at %s", _DEFAULT_DB)
    except Exception as exc:  # noqa: BLE001
        with _conn_lock:
            _conn_load_error = str(exc)
        logger.error("DuckDB preload failed: %s", exc)
    finally:
        with _conn_lock:
            _conn_loading = False


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class DuckDBQueryInput(BaseModel):
    query: str = Field(
        description=(
            "A read-only SQL query (SELECT / SHOW TABLES / DESCRIBE <table>). "
            "No DDL or DML is permitted."
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_allowed(query: str) -> bool:
    """Return True when the query starts with an allowed keyword."""
    first_token = query.strip().upper().split()[0] if query.strip() else ""
    return first_token in _ALLOWED_PREFIXES


def _inject_limit(query: str, limit: int) -> str:
    """
    Append ``LIMIT <limit>`` to a SELECT query that does not already
    contain a LIMIT clause, or clamp an existing LIMIT down to *limit*.
    """
    upper = query.upper()

    if not upper.lstrip().startswith("SELECT"):
        # SHOW / DESCRIBE / PRAGMA — do not touch
        return query

    # Check for existing LIMIT
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", upper)
    if limit_match:
        existing = int(limit_match.group(1))
        if existing <= limit:
            return query
        # Clamp
        return re.sub(
            r"\bLIMIT\s+\d+\b",
            f"LIMIT {limit}",
            query,
            flags=re.IGNORECASE,
        )

    # Strip trailing semicolons then append
    stripped = query.rstrip().rstrip(";")
    return f"{stripped} LIMIT {limit}"


def _df_to_text(df: pd.DataFrame) -> str:
    """Serialise a DataFrame to a compact Markdown-style table."""
    if df.empty:
        return "Query returned no rows."

    # Replace non-JSON-serialisable values
    df = df.replace([np.inf, -np.inf], None).where(pd.notnull(df), None)

    try:
        return df.to_markdown(index=False)
    except ImportError:
        # tabulate not installed — fall back to plain text tabulation
        return df.to_string(index=False)


def get_db_schema(db_path: Optional[Path] = None) -> str:
    """
    Connect to DuckDB (read-only) and return a compact schema summary
    (table names + column names/types) suitable for injection into a
    system prompt.

    Returns an empty string when the database is not yet available.
    """
    path = db_path or _DEFAULT_DB
    if not Path(path).exists():
        return ""

    try:
        conn = duckdb.connect(str(path), read_only=True)
        tables_df = conn.execute("SHOW TABLES").fetchdf()
        tables = tables_df["name"].tolist() if "name" in tables_df.columns else []

        lines: list[str] = ["Database schema:", ""]
        for table in sorted(tables):
            # Validate the table name against a conservative allowlist pattern
            # (alphanumeric + underscore) before using it in a DESCRIBE statement.
            if not re.match(r"^\w+$", table):
                lines.append(f"Table: {table}  (skipped: unexpected name format)")
                lines.append("")
                continue
            try:
                desc = conn.execute(f"DESCRIBE {table}").fetchdf()
                lines.append(f"Table: {table}")
                for _, row in desc.iterrows():
                    lines.append(f"  {row['column_name']}  {row['column_type']}")
                lines.append("")
            except Exception:
                lines.append(f"Table: {table}  (could not describe)")
                lines.append("")

        conn.close()
        return "\n".join(lines)
    except Exception as exc:
        return f"(Schema unavailable: {exc})"


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class DuckDBQueryTool(BaseTool):
    """Execute read-only SQL queries on the PBI DuckDB database."""

    name: str = "duckdb_query"
    description: str = (
        "Execute a read-only SQL query on the PBI DuckDB phage-bacteria interaction "
        "database. Supports SELECT, SHOW TABLES, and DESCRIBE <table>. "
        "Results are returned as a Markdown table (up to "
        f"{_ROW_LIMIT} rows). "
        "Input must be a JSON object with key 'query' containing the SQL string."
    )
    args_schema: Type[BaseModel] = DuckDBQueryInput

    def _get_conn(self) -> Optional[duckdb.DuckDBPyConnection]:
        """Return the shared read-only connection, or None when not ready."""
        if _shared_conn is not None:
            return _shared_conn
        # Shared connection not pre-loaded yet — open one on the fly (best-effort).
        # This path is only hit when preload_db_conn() was never scheduled.
        try:
            conn = duckdb.connect(str(_DEFAULT_DB), read_only=True)
            return conn
        except Exception:  # noqa: BLE001
            return None

    def _run(self, query: str) -> str:  # type: ignore[override]
        # Surface DB loading / error state before doing anything else.
        if _conn_loading:
            return (
                "⏳ The database is still loading — this can take up to 5 minutes "
                "on first start. Please try again in a moment."
            )
        if _conn_load_error == "not_found":
            return (
                "Database file not found. "
                "The pipeline must complete before the agent can query data."
            )
        if _conn_load_error:
            return f"Database connection failed: {_conn_load_error}"

        if not query or not query.strip():
            return "Empty query."

        if not _is_allowed(query):
            return (
                "Only SELECT, SHOW TABLES, DESCRIBE <table>, and PRAGMA queries "
                "are permitted. The provided query was rejected."
            )

        safe_query = _inject_limit(query, _ROW_LIMIT)

        try:
            conn = self._get_conn()
            if conn is None:
                return (
                    "Database connection is not available yet. "
                    "Please try again in a moment."
                )
            df = conn.execute(safe_query).fetchdf()
            return _df_to_text(df)
        except duckdb.Error as exc:
            return f"DuckDB error: {exc}"
        except FileNotFoundError:
            return (
                "Database file not found. "
                "The pipeline must complete before the agent can query data."
            )
        except Exception as exc:  # noqa: BLE001
            return f"Unexpected error executing query: {exc}"

    async def _arun(self, query: str) -> str:  # type: ignore[override]
        return self._run(query)

"""
query_utils.py
===============

SQL query parsing utilities for PBI-Scope.

Provides ``parse_where_clause`` which is used by both ``sequence_retrieval.py``
and ``streaming_dataset.py`` to parse user-supplied WHERE clauses that may
contain LIMIT and/or OFFSET.
"""

from __future__ import annotations

from typing import Optional, Tuple


def parse_where_clause(where_clause: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a where_clause that may contain WHERE conditions, LIMIT, and/or OFFSET.

    Args:
        where_clause: The clause to parse (e.g., "LIMIT 100", "p.Length > 1000 LIMIT 50",
                     "LIMIT 1000 OFFSET 5000", etc.)

    Returns:
        Tuple of (where_conditions, limit_offset_clause)
        - where_conditions: The WHERE conditions only (without LIMIT/OFFSET), or None
        - limit_offset_clause: The LIMIT/OFFSET clause only, or None

    Examples:
        >>> parse_where_clause("LIMIT 100")
        (None, "LIMIT 100")
        >>> parse_where_clause("p.Length > 1000 LIMIT 50")
        ("p.Length > 1000", "LIMIT 50")
        >>> parse_where_clause("LIMIT 1000 OFFSET 5000")
        (None, "LIMIT 1000 OFFSET 5000")
        >>> parse_where_clause("p.GC > 0.5")
        ("p.GC > 0.5", None)
    """
    if not where_clause or not where_clause.strip():
        return None, None

    clause = ' '.join(where_clause.split())
    clause_upper = clause.upper()
    limit_pos = clause_upper.find(' LIMIT ')

    if clause_upper.startswith('LIMIT '):
        limit_pos = 0

    if limit_pos == -1:
        return clause.strip(), None
    elif limit_pos == 0:
        return None, clause.strip()
    else:
        where_part = clause[:limit_pos].strip()
        limit_part = clause[limit_pos:].strip()
        return where_part if where_part else None, limit_part if limit_part else None

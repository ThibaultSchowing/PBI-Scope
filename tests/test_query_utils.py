"""
Unit tests for query_utils.py — parse_where_clause function.
"""

import pytest
from pbi.query_utils import parse_where_clause


class TestParseWhereClause:
    """Tests for parse_where_clause()."""

    def test_none_input(self):
        assert parse_where_clause(None) == (None, None)

    def test_empty_string(self):
        assert parse_where_clause("") == (None, None)

    def test_whitespace_only(self):
        assert parse_where_clause("   ") == (None, None)

    def test_limit_only(self):
        assert parse_where_clause("LIMIT 100") == (None, "LIMIT 100")

    def test_limit_with_offset(self):
        assert parse_where_clause("LIMIT 1000 OFFSET 5000") == (None, "LIMIT 1000 OFFSET 5000")

    def test_where_only(self):
        assert parse_where_clause("p.GC > 0.5") == ("p.GC > 0.5", None)

    def test_where_and_limit(self):
        assert parse_where_clause("p.Length > 1000 LIMIT 50") == ("p.Length > 1000", "LIMIT 50")

    def test_where_and_limit_and_offset(self):
        assert parse_where_clause("p.Length > 1000 LIMIT 50 OFFSET 100") == (
            "p.Length > 1000", "LIMIT 50 OFFSET 100"
        )

    def test_limit_at_start(self):
        assert parse_where_clause("LIMIT 100") == (None, "LIMIT 100")

    def test_complex_where(self):
        where, limit = parse_where_clause("p.Lifestyle = 'Lytic' AND p.Length > 50000 LIMIT 100")
        assert where == "p.Lifestyle = 'Lytic' AND p.Length > 50000"
        assert limit == "LIMIT 100"

    def test_whitespace_normalization(self):
        assert parse_where_clause("  p.GC > 0.5   LIMIT   50  ") == ("p.GC > 0.5", "LIMIT 50")

    def test_case_insensitive_limit(self):
        assert parse_where_clause("p.GC > 0.5 limit 50") == ("p.GC > 0.5", "limit 50")

    def test_limit_in_middle_of_where(self):
        # LIMIT should only be recognized as a keyword, not as part of a value
        where, limit = parse_where_clause("p.Name LIKE '%LIMIT%' LIMIT 10")
        assert where == "p.Name LIKE '%LIMIT%'"
        assert limit == "LIMIT 10"

"""
test_fasta_utils.py
===================

Unit tests for :mod:`pbi.fasta_utils`.

These tests are self-contained: they create temporary multi-FASTA files,
open them with pyfaidx, and verify the assembly logic without requiring
the full PBI database or any real genome data.
"""

import os
import tempfile
import textwrap

import pytest

# ---------------------------------------------------------------------------
# Guard: skip the whole module if pyfaidx is not installed
# ---------------------------------------------------------------------------
pyfaidx = pytest.importorskip("pyfaidx")
Fasta = pyfaidx.Fasta

from pbi.fasta_utils import assemble_genome, get_genome_stats  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def single_contig_fasta(tmp_path):
    """Write a single-contig FASTA and return its path."""
    fasta_text = textwrap.dedent("""\
        >contig1
        ACGTACGT
    """)
    path = tmp_path / "single.fasta"
    path.write_text(fasta_text)
    return str(path)


@pytest.fixture()
def multi_contig_fasta(tmp_path):
    """Write a three-contig FASTA and return its path.

    Contigs (by design):
        contig_long   – 12 bp  (longest)
        contig_medium – 8 bp
        contig_short  – 4 bp  (shortest)

    In ``length_desc`` order: contig_long, contig_medium, contig_short.
    """
    fasta_text = textwrap.dedent("""\
        >contig_medium
        ACGTACGT
        >contig_long
        AAACCCGGGTTT
        >contig_short
        TTTT
    """)
    path = tmp_path / "multi.fasta"
    path.write_text(fasta_text)
    return str(path)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def open_fasta(path: str) -> Fasta:
    """Open a FASTA with pyfaidx using no custom key function."""
    return Fasta(path)


# ---------------------------------------------------------------------------
# assemble_genome – mode="first"
# ---------------------------------------------------------------------------

class TestModeFirst:
    def test_single_contig_returns_only_sequence(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        result = assemble_genome(fasta, mode="first")
        assert result == "ACGTACGT"

    def test_multi_contig_returns_longest(self, multi_contig_fasta):
        """With length_desc ordering the 'first' entry is the longest contig."""
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="first")
        # contig_long is 12 bp and should come first
        assert result == "AAACCCGGGTTT"

    def test_mode_first_is_a_string(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="first")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# assemble_genome – mode="concat"
# ---------------------------------------------------------------------------

class TestModeConcat:
    def test_single_contig_no_gap(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        result = assemble_genome(fasta, mode="concat", gap=0)
        assert result == "ACGTACGT"

    def test_multi_contig_no_gap_length_desc(self, multi_contig_fasta):
        """Contigs should be joined in length_desc order without separator."""
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="concat", gap=0, order="length_desc")
        # Expected order: contig_long (12 bp) → contig_medium (8 bp) → contig_short (4 bp)
        assert result == "AAACCCGGGTTT" + "ACGTACGT" + "TTTT"

    def test_gap_inserts_correct_number_of_ns(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="concat", gap=5, order="length_desc")
        separator = "N" * 5
        assert result == "AAACCCGGGTTT" + separator + "ACGTACGT" + separator + "TTTT"

    def test_gap_zero_equivalent_to_no_gap(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        r0 = assemble_genome(fasta, mode="concat", gap=0)
        r_default = assemble_genome(fasta, mode="concat")
        assert r0 == r_default

    def test_result_is_string(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="concat")
        assert isinstance(result, str)

    def test_total_length_without_gap(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="concat", gap=0)
        assert len(result) == 12 + 8 + 4  # 24 bp total

    def test_total_length_with_gap(self, multi_contig_fasta):
        gap = 10
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="concat", gap=gap)
        # 3 contigs → 2 gaps
        assert len(result) == 12 + 8 + 4 + 2 * gap

    def test_order_file_preserves_fasta_order(self, multi_contig_fasta):
        """order='file' should use the original file order."""
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="concat", gap=0, order="file")
        # File order: contig_medium, contig_long, contig_short
        assert result == "ACGTACGT" + "AAACCCGGGTTT" + "TTTT"

    def test_negative_gap_raises(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        with pytest.raises(ValueError, match="gap must be"):
            assemble_genome(fasta, mode="concat", gap=-1)

    def test_unknown_order_raises(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        with pytest.raises(ValueError, match="Unknown order"):
            assemble_genome(fasta, mode="concat", order="random")

    def test_unknown_mode_raises(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        with pytest.raises(ValueError, match="Unknown mode"):
            assemble_genome(fasta, mode="blob")


# ---------------------------------------------------------------------------
# assemble_genome – mode="list"
# ---------------------------------------------------------------------------

class TestModeList:
    def test_single_contig_returns_list_of_one(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        result = assemble_genome(fasta, mode="list")
        assert isinstance(result, list)
        assert result == ["ACGTACGT"]

    def test_multi_contig_returns_ordered_list(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="list", order="length_desc")
        assert isinstance(result, list)
        assert len(result) == 3
        # Length-desc order
        assert result == ["AAACCCGGGTTT", "ACGTACGT", "TTTT"]

    def test_list_order_file(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="list", order="file")
        # File order
        assert result == ["ACGTACGT", "AAACCCGGGTTT", "TTTT"]


# ---------------------------------------------------------------------------
# assemble_genome – mode="dict"
# ---------------------------------------------------------------------------

class TestModeDict:
    def test_single_contig_returns_dict_of_one(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        result = assemble_genome(fasta, mode="dict")
        assert isinstance(result, dict)
        assert list(result.values()) == ["ACGTACGT"]

    def test_multi_contig_keys_match_headers(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="dict")
        assert set(result.keys()) == {"contig_medium", "contig_long", "contig_short"}

    def test_multi_contig_values_correct(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="dict")
        assert result["contig_long"] == "AAACCCGGGTTT"
        assert result["contig_medium"] == "ACGTACGT"
        assert result["contig_short"] == "TTTT"

    def test_dict_order_is_length_desc(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        result = assemble_genome(fasta, mode="dict", order="length_desc")
        assert list(result.keys()) == ["contig_long", "contig_medium", "contig_short"]


# ---------------------------------------------------------------------------
# get_genome_stats
# ---------------------------------------------------------------------------

class TestGetGenomeStats:
    def test_single_contig(self, single_contig_fasta):
        fasta = open_fasta(single_contig_fasta)
        stats = get_genome_stats(fasta)
        assert stats["contig_count"] == 1
        assert stats["total_length"] == 8
        assert stats["lengths"] == [8]

    def test_multi_contig_counts(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        stats = get_genome_stats(fasta)
        assert stats["contig_count"] == 3

    def test_multi_contig_total_length(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        stats = get_genome_stats(fasta)
        assert stats["total_length"] == 12 + 8 + 4

    def test_multi_contig_lengths_order(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        stats = get_genome_stats(fasta, order="length_desc")
        assert stats["lengths"] == [12, 8, 4]

    def test_multi_contig_lengths_file_order(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        stats = get_genome_stats(fasta, order="file")
        # File order: contig_medium (8), contig_long (12), contig_short (4)
        assert stats["lengths"] == [8, 12, 4]

    def test_lengths_sum_equals_total(self, multi_contig_fasta):
        fasta = open_fasta(multi_contig_fasta)
        stats = get_genome_stats(fasta)
        assert sum(stats["lengths"]) == stats["total_length"]


# ---------------------------------------------------------------------------
# Tie-breaking in length_desc ordering
# ---------------------------------------------------------------------------

class TestTieBreaking:
    """When two contigs have the same length, ordering must break ties by key."""

    @pytest.fixture()
    def tie_fasta(self, tmp_path):
        fasta_text = textwrap.dedent("""\
            >bravo
            AAAA
            >alpha
            CCCC
        """)
        path = tmp_path / "tie.fasta"
        path.write_text(fasta_text)
        return str(path)

    def test_tie_broken_by_header_ascending(self, tie_fasta):
        fasta = open_fasta(tie_fasta)
        result = assemble_genome(fasta, mode="list", order="length_desc")
        # Both are 4 bp; alphabetically "alpha" < "bravo"
        assert result == ["CCCC", "AAAA"]  # alpha first, bravo second

#!/usr/bin/env python3
"""
Unit tests for fasta_qc.py

Tests cover:
- Header-uniqueness audit (audit_fasta_headers)
- Sequence-content audit (audit_fasta_sequences)
- Combined run_qc helper
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Add workflow scripts directory to path
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"),
)

from fasta_qc import audit_fasta_headers, audit_fasta_sequences, run_qc


def _write_fasta(path: Path, sequences: dict) -> None:
    """Write a FASTA file from a {header: sequence} dict."""
    with open(path, 'w') as fh:
        for header, seq in sequences.items():
            fh.write(f">{header}\n{seq}\n")


class TestAuditFastaHeaders(unittest.TestCase):
    """Tests for audit_fasta_headers()"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tmppath = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_unique_headers_ok(self):
        fasta = self.tmppath / "unique.fna"
        _write_fasta(fasta, {
            "contig1 desc1": "ACGT",
            "contig2 desc2": "TTTT",
            "contig3":       "CCCC",
        })
        result = audit_fasta_headers(str(fasta))
        self.assertEqual(result.total_sequences, 3)
        self.assertFalse(result.has_duplicate_headers)
        self.assertEqual(result.duplicate_headers, [])

    def test_duplicate_headers_detected(self):
        fasta = self.tmppath / "dup_hdr.fna"
        # Write manually so we can have two identical first-word identifiers
        with open(fasta, 'w') as fh:
            fh.write(">contig1 first description\nACGT\n")
            fh.write(">contig2 unique\nTTTT\n")
            fh.write(">contig1 second description\nAAAA\n")  # duplicate first-word id
        result = audit_fasta_headers(str(fasta))
        self.assertEqual(result.total_sequences, 3)
        self.assertTrue(result.has_duplicate_headers)
        self.assertIn("contig1", result.duplicate_headers)

    def test_file_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            audit_fasta_headers("/nonexistent/path.fna")

    def test_empty_file_raises(self):
        fasta = self.tmppath / "empty.fna"
        fasta.write_text("")
        with self.assertRaises(ValueError):
            audit_fasta_headers(str(fasta))

    def test_single_sequence_ok(self):
        fasta = self.tmppath / "single.fna"
        _write_fasta(fasta, {"seq1": "ACGTACGT"})
        result = audit_fasta_headers(str(fasta))
        self.assertEqual(result.total_sequences, 1)
        self.assertFalse(result.has_duplicate_headers)


class TestAuditFastaSequences(unittest.TestCase):
    """Tests for audit_fasta_sequences()"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tmppath = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_unique_sequences_ok(self):
        fasta = self.tmppath / "unique_seqs.fna"
        _write_fasta(fasta, {
            "contig1": "ACGT",
            "contig2": "TTTT",
            "contig3": "CCCC",
        })
        result = audit_fasta_sequences(str(fasta))
        self.assertEqual(result.total_sequences, 3)
        self.assertFalse(result.has_identical_sequences)
        self.assertEqual(result.identical_groups, [])

    def test_identical_sequences_detected(self):
        fasta = self.tmppath / "dup_seq.fna"
        _write_fasta(fasta, {
            "contig1": "ACGTACGT",
            "contig2": "TTTTTTTT",
            "contig3": "ACGTACGT",  # same content as contig1
        })
        result = audit_fasta_sequences(str(fasta))
        self.assertEqual(result.total_sequences, 3)
        self.assertTrue(result.has_identical_sequences)
        self.assertEqual(len(result.identical_groups), 1)
        group = result.identical_groups[0]
        self.assertIn("contig1", group)
        self.assertIn("contig3", group)

    def test_case_insensitive_sequence_comparison(self):
        """Lower- and upper-case sequences with same bases are identical."""
        fasta = self.tmppath / "case.fna"
        _write_fasta(fasta, {
            "contig1": "acgtacgt",
            "contig2": "ACGTACGT",
        })
        result = audit_fasta_sequences(str(fasta))
        self.assertTrue(result.has_identical_sequences)

    def test_file_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            audit_fasta_sequences("/nonexistent/path.fna")

    def test_multiple_identical_groups(self):
        fasta = self.tmppath / "multi_dup.fna"
        _write_fasta(fasta, {
            "a1": "AAAA",
            "a2": "AAAA",
            "b1": "CCCC",
            "b2": "CCCC",
            "c1": "GGGG",  # unique
        })
        result = audit_fasta_sequences(str(fasta))
        self.assertEqual(len(result.identical_groups), 2)


class TestRunQc(unittest.TestCase):
    """Tests for the combined run_qc() helper."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tmppath = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_clean_fasta(self):
        fasta = self.tmppath / "clean.fna"
        _write_fasta(fasta, {"seq1": "ACGT", "seq2": "TTTT"})
        result = run_qc(str(fasta))
        self.assertEqual(result['header_qc_status'], 'ok')
        self.assertEqual(result['seq_qc_status'], 'ok')
        self.assertEqual(result['total_sequences'], 2)
        self.assertEqual(result['n_duplicate_headers'], 0)
        self.assertEqual(result['n_identical_seq_groups'], 0)

    def test_duplicate_headers_rejected(self):
        fasta = self.tmppath / "dup_hdr.fna"
        with open(fasta, 'w') as fh:
            fh.write(">contig1\nACGT\n>contig1\nTTTT\n")
        result = run_qc(str(fasta))
        self.assertEqual(result['header_qc_status'], 'rejected_duplicate_headers')
        self.assertGreater(result['n_duplicate_headers'], 0)
        # Sequence audit skipped when headers are invalid
        self.assertEqual(result['n_identical_seq_groups'], 0)

    def test_identical_sequences_warning(self):
        fasta = self.tmppath / "dup_seq.fna"
        _write_fasta(fasta, {"seq1": "ACGTACGT", "seq2": "ACGTACGT"})
        result = run_qc(str(fasta))
        # Headers are unique → not rejected
        self.assertEqual(result['header_qc_status'], 'ok')
        self.assertEqual(result['seq_qc_status'], 'warning_identical_sequences')
        self.assertGreater(result['n_identical_seq_groups'], 0)

    def test_nonexistent_file_returns_error_status(self):
        result = run_qc("/nonexistent/file.fna")
        self.assertIn('error', result['header_qc_status'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

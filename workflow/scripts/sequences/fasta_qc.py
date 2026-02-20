#!/usr/bin/env python3
"""
FASTA Quality-Control Utilities

Provides two independent audits (non-destructive: files are never modified):

1. ``audit_fasta_headers`` – streams through the FASTA file and checks that
   every sequence header (the full text after ``>``) is unique.  If duplicate
   headers are found the file should be **rejected** (not indexed).

2. ``audit_fasta_sequences`` – streams through the file and uses MD5 hashing
   to detect strictly identical sequences (same content, regardless of header).
   Duplicated sequences trigger a **warning** but the file is not modified.

Both functions are streaming (O(n_sequences) memory for header strings / MD5
hashes) so they scale to large genomes with many contigs.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, NamedTuple


class HeaderAuditResult(NamedTuple):
    """Result of a FASTA header uniqueness audit."""
    total_sequences: int
    has_duplicate_headers: bool
    duplicate_headers: List[str]  # headers that appear more than once


class SequenceAuditResult(NamedTuple):
    """Result of a FASTA sequence content audit."""
    total_sequences: int
    has_identical_sequences: bool
    identical_groups: List[List[str]]  # each group = list of headers with the same sequence


def audit_fasta_headers(fasta_path: str) -> HeaderAuditResult:
    """Stream through *fasta_path* and check header uniqueness.

    The full header line (everything after ``>``, stripped) is used as the
    identifier so that ``>seq1 desc1`` and ``>seq1 desc2`` are treated as
    different identifiers — consistent with pyfaidx ``read_long_names=True``.
    However **the first word** (up to the first whitespace) is the canonical
    FASTA identifier used by most tools and by pyfaidx in default mode.  We
    check the *first-word* identifier to match pyfaidx's default indexing
    behaviour.

    Args:
        fasta_path: Path to FASTA file (uncompressed).

    Returns:
        :class:`HeaderAuditResult` with duplicate-header information.

    Raises:
        FileNotFoundError: if *fasta_path* does not exist.
        ValueError: if the file does not appear to be in FASTA format.
    """
    fasta_path = Path(fasta_path)
    if not fasta_path.exists():
        raise FileNotFoundError(f"FASTA file not found: {fasta_path}")

    seen: Dict[str, int] = {}  # identifier → count
    total = 0

    with open(fasta_path, 'r') as fh:
        first_line = None
        for line in fh:
            line = line.rstrip('\n\r')
            if not line:
                continue
            if line.startswith('>'):
                if first_line is None:
                    first_line = line
                total += 1
                # Use first-word identifier (pyfaidx default split)
                header_text = line[1:].strip()
                identifier = header_text.split()[0] if header_text else header_text
                seen[identifier] = seen.get(identifier, 0) + 1

    if total == 0:
        raise ValueError(f"No sequences found in FASTA file: {fasta_path}")
    if first_line is not None and not first_line.startswith('>'):
        raise ValueError(f"File does not appear to be FASTA format: {fasta_path}")

    duplicates = [hdr for hdr, count in seen.items() if count > 1]

    return HeaderAuditResult(
        total_sequences=total,
        has_duplicate_headers=bool(duplicates),
        duplicate_headers=duplicates,
    )


def audit_fasta_sequences(fasta_path: str) -> SequenceAuditResult:
    """Stream through *fasta_path* and detect strictly identical sequences.

    Two sequences are considered identical when their MD5 digests match
    (same nucleotide content, case-insensitively).  The file is **never
    modified**.

    Args:
        fasta_path: Path to FASTA file (uncompressed).

    Returns:
        :class:`SequenceAuditResult` with groups of headers sharing the same
        sequence content.

    Raises:
        FileNotFoundError: if *fasta_path* does not exist.
    """
    fasta_path = Path(fasta_path)
    if not fasta_path.exists():
        raise FileNotFoundError(f"FASTA file not found: {fasta_path}")

    # hash → [headers]
    hash_to_headers: Dict[str, List[str]] = {}
    total = 0
    current_header: str = ''
    current_seq_parts: List[str] = []

    def _flush(header: str, seq_parts: List[str]) -> None:
        seq = ''.join(seq_parts).upper()
        digest = hashlib.md5(seq.encode()).hexdigest()
        if digest not in hash_to_headers:
            hash_to_headers[digest] = []
        hash_to_headers[digest].append(header)

    with open(fasta_path, 'r') as fh:
        for line in fh:
            line = line.rstrip('\n\r')
            if not line:
                continue
            if line.startswith('>'):
                if current_header:
                    _flush(current_header, current_seq_parts)
                total += 1
                current_header = line[1:].strip()
                current_seq_parts = []
            else:
                current_seq_parts.append(line)

    if current_header:
        _flush(current_header, current_seq_parts)

    identical_groups = [
        headers for headers in hash_to_headers.values() if len(headers) > 1
    ]

    return SequenceAuditResult(
        total_sequences=total,
        has_identical_sequences=bool(identical_groups),
        identical_groups=identical_groups,
    )


def run_qc(fasta_path: str) -> Dict:
    """Run both audits on *fasta_path* and return a combined result dict.

    The returned dict is designed to be directly used as a row in a
    DataFrame-compatible CSV log.

    Columns returned:

    * ``total_sequences`` – number of ``>`` records in the file.
    * ``header_qc_status`` – ``'ok'`` or ``'rejected_duplicate_headers'``.
    * ``n_duplicate_headers`` – number of header identifiers appearing > once.
    * ``duplicate_header_examples`` – up to 5 duplicate identifiers (semicolon-
      separated), or ``''``.
    * ``seq_qc_status`` – ``'ok'`` or ``'warning_identical_sequences'``.
    * ``n_identical_seq_groups`` – number of groups of ≥ 2 sequences with the
      same content.
    * ``identical_seq_group_examples`` – up to 3 groups (pipe-separated),
      each group is a semicolon-separated list of headers, or ``''``.

    Args:
        fasta_path: Path to an uncompressed FASTA file.

    Returns:
        Dict suitable for a single CSV row.
    """
    result: Dict = {
        'total_sequences': 0,
        'header_qc_status': 'ok',
        'n_duplicate_headers': 0,
        'duplicate_header_examples': '',
        'seq_qc_status': 'ok',
        'n_identical_seq_groups': 0,
        'identical_seq_group_examples': '',
    }

    try:
        header_result = audit_fasta_headers(fasta_path)
        result['total_sequences'] = header_result.total_sequences

        if header_result.has_duplicate_headers:
            result['header_qc_status'] = 'rejected_duplicate_headers'
            result['n_duplicate_headers'] = len(header_result.duplicate_headers)
            examples = header_result.duplicate_headers[:5]
            result['duplicate_header_examples'] = ';'.join(examples)
            logging.warning(
                f"⚠️ REJECTED {fasta_path}: {len(header_result.duplicate_headers)} "
                f"duplicate header(s) — e.g. {examples[:3]}"
            )
            # Skip sequence audit when headers are already invalid
            return result

        # Headers are unique — proceed with sequence content audit
        seq_result = audit_fasta_sequences(fasta_path)
        if seq_result.has_identical_sequences:
            result['seq_qc_status'] = 'warning_identical_sequences'
            result['n_identical_seq_groups'] = len(seq_result.identical_groups)
            group_strs = [';'.join(g[:3]) for g in seq_result.identical_groups[:3]]
            result['identical_seq_group_examples'] = '|'.join(group_strs)
            logging.warning(
                f"⚠️ WARNING {fasta_path}: {len(seq_result.identical_groups)} "
                f"group(s) of identical sequences found — file will still be indexed"
            )

    except Exception as exc:
        result['header_qc_status'] = f'error: {exc}'
        logging.error(f"❌ QC error for {fasta_path}: {exc}")

    return result

"""
fasta_ids.py
============

Canonical FASTA header handling for PBI-Scope.

Variant B + Source_DB provenance token:
- Phage FASTA:   >Phage_ID Source_DB [original_rest]
  e.g. >NC_000866.4 RefSeq  /  >IMGVR_UViG_2020627000_000021|... IMGVR  /  >Broecker_..._cov_8.92 GVD
- Protein FASTA: >Phage_ID Protein_ID Source_DB [original_rest]
  e.g. >NC_000866.4 NP_049616.1 RefSeq  /  >Actinoplanes_phage_phiAsp2 Actinoplanes_phage_phiAsp2_1 PhagesDB

Keys (used for pyfaidx):
- phage_key   = token0  (Phage_ID)
- protein_key = token1  (Protein_ID) — Variant B

Original file find-back preserved: token0 still equals DB Phage_ID, token1 still
equals DB Protein_ID. Source_DB is token1 (phage) / token2 (protein) provenance.
"""

from __future__ import annotations

import re


def _tokens(header: str) -> list[str]:
    """Split header (without leading '>') into whitespace-delimited tokens."""
    h = header[1:].strip() if header.startswith(">") else header.strip()
    if not h:
        return []
    return h.split()


def phage_key(header: str) -> str:
    """Canonical phage key = first token (Phage_ID)."""
    toks = _tokens(header)
    return toks[0] if toks else ""


def protein_key(header: str) -> str:
    """Canonical protein key = second token (Protein_ID) for Variant B.

    Handles heterogeneous headers:
    - New canonical: >Phage_ID Protein_ID Source_DB [rest]  -> token1
    - Old Prodigal:  >Protein_ID # 2 # 685 ...               -> token0 (since token1 == "#")
    - Bare:          >Protein_ID                              -> token0
    """
    toks = _tokens(header)
    if not toks:
        return ""
    if len(toks) >= 2 and toks[1] == "#":
        # Old style without phage prefix: first token is the actual Protein_ID
        return toks[0]
    if len(toks) >= 2:
        return toks[1]
    return toks[0]


def source_of_phage_header(header: str) -> str | None:
    """Provenance Source_DB for a phage header (token1 when present)."""
    toks = _tokens(header)
    return toks[1] if len(toks) >= 2 else None


def source_of_protein_header(header: str) -> str | None:
    """Provenance Source_DB for a protein header (token2 when present)."""
    toks = _tokens(header)
    return toks[2] if len(toks) >= 3 else None


def validate_no_whitespace(pid: str) -> None:
    if not pid or any(c.isspace() for c in pid):
        raise ValueError(f"Invalid ID contains whitespace or empty: {pid!r}")


def _collapse_rest(rest: str) -> str:
    """Collapse whitespace in trailing description to single spaces; strip."""
    rest = rest.strip()
    if not rest:
        return ""
    # normalize internal whitespace
    return " ".join(rest.split())


def normalize_phage_header(raw_header: str, source_db: str) -> str:
    """Normalize a phage header to canonical ``>Phage_ID Source_DB [rest]``.

    - raw_header: original header line (with or without leading '>')
    - source_db: Source_DB name (e.g. ``RefSeq``)
    Returns canonical header line including leading '>'.
    Raises ValueError on empty Phage_ID or whitespace in Phage_ID.
    """
    toks = _tokens(raw_header)
    if not toks:
        raise ValueError(f"Empty phage header: {raw_header!r}")
    phage_id = toks[0]
    validate_no_whitespace(phage_id)
    rest = _collapse_rest(" ".join(toks[1:]))
    if rest:
        return f">{phage_id} {source_db} {rest}"
    return f">{phage_id} {source_db}"


def normalize_protein_header(raw_header: str, phage_id: str, source_db: str) -> str:
    """Normalize a protein header to ``>Phage_ID Protein_ID Source_DB [rest]``.

    - raw_header: original protein header line (with or without '>'), where the
      first token is Protein_ID (e.g. ``>AAF39720.1`` or ``>NP_049616.1 desc``)
    - phage_id:   parent phage identifier (directory name, e.g. Actinoplanes_phage_phiAsp2
                  or NC_000866.4)
    - source_db:  Source_DB (e.g. RefSeq)
    """
    toks = _tokens(raw_header)
    if not toks:
        raise ValueError(f"Empty protein header: {raw_header!r}")
    protein_id = toks[0]
    validate_no_whitespace(protein_id)
    validate_no_whitespace(phage_id)
    rest = _collapse_rest(" ".join(toks[1:]))
    if rest:
        return f">{phage_id} {protein_id} {source_db} {rest}"
    return f">{phage_id} {protein_id} {source_db}"


# pyfaidx key functions (aliases for callers)
PHAGE_KEY_FUNCTION = phage_key
PROTEIN_KEY_FUNCTION = protein_key

# Optional regex to sanity-check accession vs dirty IDs (not used for gating,
# only for tests/documentation). Accepts simple accessions and long composite.
_CLEAN_ACCESSION_RE = re.compile(r"^[A-Za-z0-9_.\-:|]+$")

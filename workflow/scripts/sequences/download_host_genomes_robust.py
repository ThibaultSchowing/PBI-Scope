#!/usr/bin/env python
"""
Robust Host Bacterial Genome Downloader from NCBI

This module implements a robust, reproducible, and scalable strategy for retrieving
bacterial genome assemblies from NCBI, addressing all requirements:

1. Uses NCBI Assembly database as authoritative entry point
2. Normalizes all inputs to assembly accessions (GCF_ preferred, GCA_ fallback)
3. Explicit ambiguity acknowledgment for species/strain names
4. Quality-based filtering (RefSeq > GenBank, latest, assembly level, reference/representative)
5. Clear distinction between genome/assembly/contigs and curated/author-submitted data
6. Metadata via Entrez, sequences via FTP
7. Comprehensive file retrieval (FASTA, GFF, protein FASTA)
8. Failure mode mitigation (duplication, partial genomes, outdated assemblies)

Key Features:
- Assembly accession resolution from heterogeneous identifiers
- Metadata-only mode (skip downloads to save disk space)
- Preservation of previously downloaded genomes with hash validation
- Comprehensive assembly metadata tracking
- Database tables linking phages to host assemblies
"""

import os
import re
import shutil
import sys
import time
import logging
import hashlib
import urllib.request
import urllib.error
import gzip
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime
import json
import pandas as pd
from Bio import SeqIO

# Import assembly resolver
from assembly_resolver import AssemblyResolver, AssemblyMetadata

# ---------------------------------------------------------------------------
# Module-level helpers for multi-host parsing and resolution
# ---------------------------------------------------------------------------

#: Tokens that should be treated as "no host" (case-insensitive comparison).
_INVALID_HOST_TOKENS: frozenset = frozenset({
    '-', 'na', 'none', 'null', 'nan', 'unknown', 'unidentified', 'uncultured',
})

#: GCA_/GCF_ pattern (canonical form, underscore, 9 digits, dot, version).
_ASSEMBLY_ACCESSION_RE = re.compile(r'^(GCF|GCA)_\d{9}\.\d+$')

#: GCA/GCF written with a space instead of underscore, e.g. "GCA 900066335.1".
_ASSEMBLY_WITH_SPACE_RE = re.compile(r'\b(GCF|GCA)\s+(\d{9}\.\d+)\b')


@dataclass
class HostToken:
    """A single parsed candidate token from a phage's Host field.

    Attributes:
        token:       Normalised token string (GCA/GCF spaces already fixed).
        token_type:  One of ``'assembly_accession'``, ``'species_name'``, or
                     ``'other'``.
        token_order: 1-based position of this token in the original Host string.
    """

    token: str
    token_type: str
    token_order: int


@dataclass
class ResolvedAssemblyLink:
    """A resolved phage→host assembly link with confidence scoring.

    Attributes:
        phage_id:           Phage identifier.
        host_raw:           Original (un-parsed) Host field value.
        host_token:         The specific token that was resolved.
        token_type:         Type of the token (``'assembly_accession'``,
                            ``'species_name'``, ``'other'``).
        token_order:        1-based position of the token in *host_raw*.
        assembly_accession: Resolved NCBI assembly accession.
        resolution_source:  How the assembly was found (see
                            ``resolve_host_token`` docstring).
        resolution_rank:    1-based rank within results for this token.
        confidence:         Float 0–1 derived from *resolution_source* and
                            rank.
        assembly_level:     Assembly completeness level (e.g. "Complete
                            Genome").
        refseq_category:    RefSeq category (e.g. "reference genome").
        quality_score:      Integer quality score from
                            :meth:`AssemblyMetadata.get_quality_score`.
        ambiguous:          ``True`` when multiple equally-plausible hits
                            exist for this token.
        ambiguity_reason:   Human-readable reason when *ambiguous* is ``True``.
    """

    phage_id: str
    host_raw: str
    host_token: str
    token_type: str
    token_order: int
    assembly_accession: str
    resolution_source: str
    resolution_rank: int
    confidence: float
    assembly_level: str
    refseq_category: str
    quality_score: int
    ambiguous: bool
    ambiguity_reason: str


# ---------------------------------------------------------------------------
# Confidence-scoring helpers (shared by resolve_host_token and _build_assembly_links)
# ---------------------------------------------------------------------------

#: Confidence reduction applied per additional rank (rank 2 = base - 1×, etc.)
_CONFIDENCE_DEGRADATION_PER_RANK: float = 0.10

#: Maps token_type → (resolution_source, base_confidence).
_TOKEN_RESOLUTION_PARAMS: Dict[str, Tuple[str, float]] = {
    'assembly_accession': ('accession_in_host_field',      0.95),
    'species_name':       ('species_to_taxid_to_assembly', 0.70),
    'other':              ('fallback',                     0.30),
}


def _resolution_params(token_type: str) -> Tuple[str, float]:
    """Return ``(resolution_source, base_confidence)`` for *token_type*."""
    return _TOKEN_RESOLUTION_PARAMS.get(token_type, ('fallback', 0.30))


def _calculate_confidence(base_confidence: float, rank: int) -> float:
    """Confidence score for a given *rank* (1-based) within a token's results."""
    return round(max(0.0, base_confidence - (rank - 1) * _CONFIDENCE_DEGRADATION_PER_RANK), 3)


def _ambiguity_reason(n_assemblies: int) -> str:
    """Human-readable ambiguity reason string."""
    return f"{n_assemblies} assemblies found" if n_assemblies > 1 else ''


def parse_host_field(host_raw: str) -> List[HostToken]:
    """Parse a raw Host field value into individual candidate tokens.

    Splits on semicolons, normalises GCA/GCF accessions that use a space
    instead of an underscore (e.g. ``"GCA 900066335.1"`` →
    ``"GCA_900066335.1"``), removes empty / NA / unknown values, and
    classifies each token.

    Token type classification:

    * ``'assembly_accession'``: matches ``GCF_`` or ``GCA_`` pattern.
    * ``'species_name'``: two or more whitespace-separated words where the
      first word starts with an uppercase letter (typical binomial
      nomenclature).
    * ``'other'``: everything else (single-word genus, uncurated codes, …).

    Args:
        host_raw: Raw Host field value from the phage metadata CSV.

    Returns:
        List of :class:`HostToken` objects in original semicolon order
        (``Token_Order`` starts at 1).  Returns an empty list when no valid
        tokens are found.

    Examples::

        >>> parse_host_field("NA;GCA 900066335.1;UBA9502;Blautia obeum")
        [HostToken(token='GCA_900066335.1', token_type='assembly_accession', token_order=2),
         HostToken(token='UBA9502',         token_type='other',              token_order=3),
         HostToken(token='Blautia obeum',   token_type='species_name',       token_order=4)]

        >>> parse_host_field("Bacteroides dorei;Bacteroides vulgatus")
        [HostToken(token='Bacteroides dorei',    token_type='species_name', token_order=1),
         HostToken(token='Bacteroides vulgatus', token_type='species_name', token_order=2)]

        >>> parse_host_field("-")
        []
    """
    if not host_raw or host_raw is None:
        return []

    host_str = str(host_raw).strip()
    if not host_str or host_str.lower() in _INVALID_HOST_TOKENS:
        return []

    # Normalise "GCA 900066335.1" → "GCA_900066335.1" before splitting
    host_str = _ASSEMBLY_WITH_SPACE_RE.sub(r'\1_\2', host_str)

    tokens: List[HostToken] = []
    order = 0
    for raw_part in host_str.split(';'):
        order += 1
        part = raw_part.strip()
        if not part or part.lower() in _INVALID_HOST_TOKENS:
            continue
        # Also skip tokens that contain "unknown" or "unidentified" (e.g. "unknown host")
        part_lower = part.lower()
        if 'unknown' in part_lower or 'unidentified' in part_lower:
            continue

        if _ASSEMBLY_ACCESSION_RE.match(part):
            token_type = 'assembly_accession'
        elif part and len(part.split()) >= 2 and part[0].isupper():
            token_type = 'species_name'
        else:
            token_type = 'other'

        tokens.append(HostToken(token=part, token_type=token_type, token_order=order))

    return tokens


def resolve_host_token(
    token: HostToken,
    resolver: AssemblyResolver,
    phage_id: str,
    host_raw: str,
    top_k: int = 1,
) -> List[ResolvedAssemblyLink]:
    """Resolve a single :class:`HostToken` to ranked assembly links.

    Resolution strategy per token type:

    * ``'assembly_accession'`` – direct NCBI lookup; confidence 0.95.
    * ``'species_name'`` – species→TaxID→assembly search; confidence 0.70.
    * ``'other'`` – attempted species search as fallback; confidence 0.30.

    Confidence decreases by 0.10 for each additional rank beyond the first.

    Args:
        token:    The token to resolve.
        resolver: An initialised :class:`AssemblyResolver`.
        phage_id: Phage identifier (included in output records).
        host_raw: Original raw Host field (included for traceability).
        top_k:    Maximum number of assemblies to return per token.

    Returns:
        List of :class:`ResolvedAssemblyLink` records sorted by
        *resolution_rank* (best first).  Empty list if resolution fails.
    """
    resolution_source, base_confidence = _resolution_params(token.token_type)

    try:
        assemblies = resolver.resolve(token.token, prefer_refseq=True, max_results=top_k)
    except Exception as exc:
        logging.warning(f"⚠️  Failed to resolve token '{token.token}': {exc}")
        return []

    ambiguous = len(assemblies) > 1
    reason = _ambiguity_reason(len(assemblies))

    links: List[ResolvedAssemblyLink] = []
    for rank, asm in enumerate(assemblies[:top_k], start=1):
        links.append(ResolvedAssemblyLink(
            phage_id=phage_id,
            host_raw=host_raw,
            host_token=token.token,
            token_type=token.token_type,
            token_order=token.token_order,
            assembly_accession=asm.assembly_accession,
            resolution_source=resolution_source,
            resolution_rank=rank,
            confidence=_calculate_confidence(base_confidence, rank),
            assembly_level=asm.assembly_level,
            refseq_category=asm.refseq_category,
            quality_score=asm.get_quality_score(),
            ambiguous=ambiguous,
            ambiguity_reason=reason,
        ))

    return links


class GenomeFileType:
    """Types of genome files to download from NCBI FTP"""
    
    # Sequence files
    GENOMIC_FNA = "_genomic.fna.gz"  # Genomic nucleotide FASTA
    PROTEIN_FAA = "_protein.faa.gz"   # Protein sequences
    CDS_FNA = "_cds_from_genomic.fna.gz"  # CDS nucleotide sequences
    
    # Annotation files
    GENOMIC_GFF = "_genomic.gff.gz"   # Gene annotation (GFF3 format)
    GENOMIC_GBK = "_genomic.gbff.gz"  # GenBank flat file
    
    # Feature tables
    FEATURE_TABLE = "_feature_table.txt.gz"
    
    # Assembly metadata
    ASSEMBLY_REPORT = "_assembly_report.txt"
    ASSEMBLY_STATS = "_assembly_stats.txt"
    
    @staticmethod
    def get_essential_files() -> List[str]:
        """
        Get list of essential files for bacterial genome analysis
        
        Rationale:
        - genomic.fna: Complete genome sequence (primary data)
        - genomic.gff: Gene annotations (functional analysis)
        - protein.faa: Translated proteins (comparative analysis)
        - assembly_report: Quality metrics and metadata
        """
        return [
            GenomeFileType.GENOMIC_FNA,
            GenomeFileType.GENOMIC_GFF,
            GenomeFileType.PROTEIN_FAA,
            GenomeFileType.ASSEMBLY_REPORT
        ]
    
    @staticmethod
    def get_optional_files() -> List[str]:
        """Get list of optional files (for advanced analysis)"""
        return [
            GenomeFileType.CDS_FNA,
            GenomeFileType.GENOMIC_GBK,
            GenomeFileType.FEATURE_TABLE,
            GenomeFileType.ASSEMBLY_STATS
        ]


class RobustHostGenomeDownloader:
    """
    Robust host bacterial genome downloader with comprehensive features
    
    This class implements the complete robust retrieval strategy for bacterial
    genomes from NCBI, with focus on reproducibility, quality, and failure handling.
    """
    
    def __init__(self,
                 phage_csv_path: str,
                 output_dir: str,
                 metadata_output: str,
                 assembly_metadata_output: str,
                 phage_host_links_output: str,
                 ncbi_email: str,
                 ncbi_api_key: Optional[str] = None,
                 metadata_only: bool = False,
                 skip_existing: bool = True,
                 validate_checksums: bool = True,
                 download_optional_files: bool = False,
                 phage_host_candidates_output: Optional[str] = None,
                 phage_host_assemblies_output: Optional[str] = None,
                 host_resolution_cache_output: Optional[str] = None,
                 reuse_resolution_cache: bool = True,
                 host_resolution_cache_ttl_days: Optional[int] = 120,
                 stats_timeout: float = 60.0,
                 checkpoint_every: int = 100,
                 max_fasta_bytes: int = 500 * 1024 * 1024):
        """
        Initialize RobustHostGenomeDownloader

        Args:
            phage_csv_path: Path to phage metadata CSV
            output_dir: Directory for downloaded genome files
            metadata_output: Path for host metadata CSV (backward compatible)
            assembly_metadata_output: Path for assembly metadata CSV (new)
            phage_host_links_output: Path for phage-host links CSV (new)
            ncbi_email: Email for NCBI API
            ncbi_api_key: Optional NCBI API key
            metadata_only: If True, only gather metadata without downloading files
            skip_existing: If True, skip already downloaded genomes
            validate_checksums: If True, validate file integrity with checksums
            download_optional_files: If True, download optional annotation files
            phage_host_candidates_output: Path for phage_host_candidates.csv.
                Defaults to *metadata_output* with ``_host_candidates`` suffix.
            phage_host_assemblies_output: Path for phage_host_assemblies.csv.
                Defaults to *metadata_output* with ``_host_assemblies`` suffix.
            host_resolution_cache_output: Path for persistent token-resolution
                cache (JSON). Defaults to *metadata_output* with
                ``_token_resolution_cache.json`` suffix.
            reuse_resolution_cache: If True, reuse cached token resolutions from
                previous runs to avoid repeated NCBI lookups.
            host_resolution_cache_ttl_days: TTL in days for the token resolution
                cache. ``120`` ≈ 4 months. Cache file older than TTL is ignored.
                ``0`` or ``None``/``False`` disables TTL (cache never expires).
                Also applied to bacterial TaxID cache.
            stats_timeout: Per-file timeout in seconds for genome statistics.
                A timeout returns ``(None, None)`` instead of hanging the
                whole 5516-genome loop (e.g. bad-block ``D``-state reads).
            checkpoint_every: Flush Stage-4 progress to checkpoint CSVs every
                N accessions so a killed run can resume via ``skip_existing``.
            max_fasta_bytes: Files larger than this are skipped for stats
                (returns ``(None, None)``) to bound memory/time.
        """
        self.phage_csv_path = Path(phage_csv_path)
        self.output_dir = Path(output_dir)
        self.metadata_output = Path(metadata_output)
        self.assembly_metadata_output = Path(assembly_metadata_output)
        self.phage_host_links_output = Path(phage_host_links_output)
        self.ncbi_email = ncbi_email
        self.ncbi_api_key = ncbi_api_key
        self.metadata_only = metadata_only
        self.skip_existing = skip_existing
        self.validate_checksums = validate_checksums
        self.download_optional_files = download_optional_files

        # Multi-host CSV outputs (new)
        _base = str(metadata_output).replace('.csv', '')
        self.phage_host_candidates_output = Path(
            phage_host_candidates_output or f"{_base}_host_candidates.csv"
        )
        self.phage_host_assemblies_output = Path(
            phage_host_assemblies_output or f"{_base}_host_assemblies.csv"
        )
        self.host_resolution_cache_output = Path(
            host_resolution_cache_output or f"{_base}_token_resolution_cache.json"
        )
        self.reuse_resolution_cache = reuse_resolution_cache
        # TTL: 0/None/False = never expire; otherwise days -> seconds
        try:
            _ttl_raw = host_resolution_cache_ttl_days
            if _ttl_raw is None or _ttl_raw is False:
                self.host_resolution_cache_ttl_days = None
            else:
                _ttl_int = int(_ttl_raw)
                self.host_resolution_cache_ttl_days = _ttl_int if _ttl_int > 0 else None
        except Exception:
            self.host_resolution_cache_ttl_days = 120
        self.stats_timeout = float(stats_timeout) if stats_timeout else 60.0
        self.checkpoint_every = int(checkpoint_every) if checkpoint_every else 100
        self.max_fasta_bytes = int(max_fasta_bytes) if max_fasta_bytes else 500 * 1024 * 1024

        # Sidecar paths (not Snakemake outputs): periodic Stage-4 progress so
        # a killed run can resume. Final outputs overwrite these on success.
        self.assembly_checkpoint_output = self.assembly_metadata_output.with_name(
            self.assembly_metadata_output.stem + ".checkpoint.csv"
        )
        self.host_checkpoint_output = self.metadata_output.with_name(
            self.metadata_output.stem + ".checkpoint.csv"
        )
        self.bacterial_cache_output = self.host_resolution_cache_output.with_name(
            self.host_resolution_cache_output.stem.replace(
                "_token_resolution_cache", "_bacterial_cache"
            ) + ".json"
        )
        self._bacterial_cache: Dict[str, Optional[bool]] = self._load_bacterial_cache()

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        self.assembly_metadata_output.parent.mkdir(parents=True, exist_ok=True)
        self.phage_host_links_output.parent.mkdir(parents=True, exist_ok=True)
        self.phage_host_candidates_output.parent.mkdir(parents=True, exist_ok=True)
        self.phage_host_assemblies_output.parent.mkdir(parents=True, exist_ok=True)
        self.host_resolution_cache_output.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize assembly resolver
        self.resolver = AssemblyResolver(
            email=ncbi_email,
            api_key=ncbi_api_key
        )
        
        # Track processing status
        self.processed_species: Set[str] = set()
        self.failed_species: Dict[str, str] = {}
        self.assembly_cache: Dict[str, AssemblyMetadata] = {}
        
        # Load existing metadata if available
        self.existing_metadata = self._load_existing_metadata()
        self.token_resolution_cache = self._load_token_resolution_cache()
        
        logging.info("✅ RobustHostGenomeDownloader initialized")
        logging.info(f"   Phage CSV: {self.phage_csv_path}")
        logging.info(f"   Output directory: {self.output_dir}")
        logging.info(f"   Metadata only: {self.metadata_only}")
        logging.info(f"   Skip existing: {self.skip_existing}")
        logging.info(f"   Validate checksums: {self.validate_checksums}")
        logging.info(f"   Reuse resolution cache: {self.reuse_resolution_cache}")
        ttl_str = f"{self.host_resolution_cache_ttl_days}d" if self.host_resolution_cache_ttl_days else "never expires"
        logging.info(f"   Resolution cache TTL: {ttl_str}")
        logging.info(f"   Resolution cache file: {self.host_resolution_cache_output}")
        logging.info(f"   Stats timeout: {self.stats_timeout}s, checkpoint every: {self.checkpoint_every}")
        if self.existing_metadata:
            logging.info(f"   Found {len(self.existing_metadata)} existing genomes")
        if self.token_resolution_cache:
            logging.info(f"   Found cached resolutions for {len(self.token_resolution_cache)} host tokens")

    @staticmethod
    def _assembly_to_cache_dict(assembly: AssemblyMetadata) -> Dict[str, Any]:
        """Convert AssemblyMetadata to a JSON-serializable dict."""
        return {
            'assembly_accession': assembly.assembly_accession,
            'assembly_name': assembly.assembly_name,
            'organism_name': assembly.organism_name,
            'species_taxid': assembly.species_taxid,
            'strain': assembly.strain,
            'assembly_level': assembly.assembly_level,
            'refseq_category': assembly.refseq_category,
            'version': assembly.version,
            'is_latest': assembly.is_latest,
            'biosample': assembly.biosample,
            'bioproject': assembly.bioproject,
            'ftp_path': assembly.ftp_path,
            'submission_date': assembly.submission_date,
        }

    @staticmethod
    def _cache_dict_to_assembly(data: Dict[str, Any]) -> AssemblyMetadata:
        """Convert cached dict to AssemblyMetadata."""
        return AssemblyMetadata(
            assembly_accession=data.get('assembly_accession', ''),
            assembly_name=data.get('assembly_name', '-'),
            organism_name=data.get('organism_name', '-'),
            species_taxid=data.get('species_taxid'),
            strain=data.get('strain'),
            assembly_level=data.get('assembly_level', 'Contig'),
            refseq_category=data.get('refseq_category', 'na'),
            version=data.get('version', 1),
            is_latest=data.get('is_latest', True),
            biosample=data.get('biosample'),
            bioproject=data.get('bioproject'),
            ftp_path=data.get('ftp_path'),
            submission_date=data.get('submission_date'),
        )

    def _is_cache_stale(self, path: Path) -> bool:
        """Return True if *path* is older than TTL (4 months default)."""
        if self.host_resolution_cache_ttl_days is None:
            return False
        try:
            age_days = (time.time() - path.stat().st_mtime) / 86400
            if age_days > self.host_resolution_cache_ttl_days:
                logging.info(
                    f"   ⏰ Cache stale: {path.name} is {age_days:.1f}d old "
                    f"(TTL {self.host_resolution_cache_ttl_days}d) — ignoring"
                )
                return True
            # Log remaining TTL once for visibility
            logging.info(
                f"   ✓ Cache fresh: {path.name} is {age_days:.1f}d old "
                f"(TTL {self.host_resolution_cache_ttl_days}d, {self.host_resolution_cache_ttl_days - age_days:.0f}d remaining)"
            )
            return False
        except OSError:
            return True

    def _load_token_resolution_cache(self) -> Dict[str, List[AssemblyMetadata]]:
        """Load persistent token→assemblies cache from previous runs (with TTL)."""
        if not self.reuse_resolution_cache:
            return {}
        if not self.host_resolution_cache_output.exists():
            return {}
        if self._is_cache_stale(self.host_resolution_cache_output):
            return {}

        try:
            with open(self.host_resolution_cache_output, 'r') as f:
                raw_cache = json.load(f)

            cache: Dict[str, List[AssemblyMetadata]] = {}
            for token, raw_assemblies in raw_cache.items():
                cache[token] = [
                    self._cache_dict_to_assembly(item)
                    for item in (raw_assemblies or [])
                ]
            return cache
        except Exception as exc:
            logging.warning(f"⚠️  Could not load token resolution cache: {exc}")
            return {}

    def _save_token_resolution_cache(self, token_to_assemblies: Dict[str, List[AssemblyMetadata]]) -> None:
        """Persist token→assemblies mapping to JSON for future reruns."""
        serializable = {
            token: [self._assembly_to_cache_dict(asm) for asm in assemblies]
            for token, assemblies in token_to_assemblies.items()
        }
        tmp_path = self.host_resolution_cache_output.with_suffix(
            self.host_resolution_cache_output.suffix + ".tmp"
        )
        try:
            with open(tmp_path, 'w') as f:
                json.dump(serializable, f, indent=2, sort_keys=True)
            tmp_path.replace(self.host_resolution_cache_output)
        except Exception as exc:
            logging.warning(f"⚠️  Could not write token resolution cache: {exc}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
    
    def _load_existing_metadata(self) -> Dict[str, Dict]:
        """Load existing assembly metadata to avoid re-processing.

        Falls back to the Stage-4 checkpoint CSV when the final output
        does not exist yet (killed run), so ``skip_existing`` resumes
        instead of re-statting all 5516 genomes.
        """
        for candidate in (self.assembly_metadata_output, self.assembly_checkpoint_output):
            if not candidate.exists():
                continue
            try:
                df = pd.read_csv(candidate)
                if df.empty or 'Assembly_Accession' not in df.columns:
                    continue
                metadata = {}
                for _, row in df.iterrows():
                    key = row['Assembly_Accession']
                    metadata[key] = row.to_dict()
                if candidate != self.assembly_metadata_output and metadata:
                    logging.info(
                        f"   ↩️  Resuming from checkpoint: {len(metadata)} "
                        f"assemblies in {candidate.name}"
                    )
                return metadata
            except Exception as e:
                logging.warning(f"⚠️  Could not load existing metadata from {candidate}: {e}")
                continue
        return {}

    def _load_bacterial_cache(self) -> Dict[str, Optional[bool]]:
        """Load persisted TaxID→bacterial cache (avoids 5516 Entrez re-lookups) with TTL."""
        path = getattr(self, 'bacterial_cache_output', None)
        if path is None or not Path(path).exists():
            return {}
        if self._is_cache_stale(Path(path)):
            return {}
        try:
            with open(path, 'r') as f:
                raw = json.load(f)
            return {str(k): (None if v is None else bool(v)) for k, v in raw.items()}
        except Exception as exc:
            logging.warning(f"⚠️  Could not load bacterial cache: {exc}")
            return {}

    def _save_bacterial_cache(self) -> None:
        """Atomically persist the TaxID→bacterial cache sidecar."""
        try:
            tmp_path = self.bacterial_cache_output.with_suffix(
                self.bacterial_cache_output.suffix + ".tmp"
            )
            with open(tmp_path, 'w') as f:
                json.dump({str(k): v for k, v in self._bacterial_cache.items()}, f, sort_keys=True)
            tmp_path.replace(self.bacterial_cache_output)
        except Exception as exc:
            logging.debug(f"Could not write bacterial cache: {exc}")

    @staticmethod
    def _is_fresh(path: Path, ref: Path) -> bool:
        """True if *path* exists, is non-empty and not older than *ref*."""
        try:
            if not path.exists() or path.stat().st_size == 0:
                return False
            if not ref.exists():
                return True
            return path.stat().st_mtime >= ref.stat().st_mtime - 1.0
        except OSError:
            return False

    @staticmethod
    def _atomic_write_csv(df: 'pd.DataFrame', path: Path) -> None:
        """Write CSV atomically via tmp+replace so kills never corrupt it."""
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        df.to_csv(tmp_path, index=False)
        tmp_path.replace(path)

    def _flush_checkpoints(
        self, host_records: List[Dict], assembly_records: List[Dict]
    ) -> None:
        """Flush Stage-4 progress sidecars (best-effort, never raises)."""
        try:
            if assembly_records:
                self._atomic_write_csv(pd.DataFrame(assembly_records), self.assembly_checkpoint_output)
            if host_records:
                self._atomic_write_csv(pd.DataFrame(host_records), self.host_checkpoint_output)
        except Exception as exc:
            logging.debug(f"Checkpoint flush failed: {exc}")
    
    def extract_unique_hosts(self) -> List[str]:
        """
        Extract unique host identifiers from phage metadata CSV
        
        This method now preserves the raw Host field values, allowing the
        AssemblyResolver to handle complex semicolon-separated fields with
        GCA accessions, species names, etc.
        
        Returns:
            List of unique host identifiers (raw values from CSV)
        """
        logging.info("📋 Extracting unique hosts from phage metadata...")
        
        df = pd.read_csv(self.phage_csv_path)
        
        if 'Host' not in df.columns:
            raise ValueError("Host column not found in phage metadata CSV")
        
        # Filter for valid hosts (not empty, not '-', not unknown/unidentified)
        valid_mask = (
            df['Host'].notna() &
            (df['Host'] != '-') &
            (df['Host'] != '') &
            (~df['Host'].str.contains('unknown', case=False, na=False)) &
            (~df['Host'].str.contains('unidentified', case=False, na=False))
        )
        
        # Get unique host values (preserve raw values for better resolution)
        unique_hosts = df.loc[valid_mask, 'Host'].unique()
        
        # Convert to list and strip whitespace
        host_list = [str(host).strip() for host in unique_hosts]
        
        # Remove any that became empty after stripping
        host_list = [h for h in host_list if h]
        
        host_list = sorted(host_list)
        logging.info(f"✅ Found {len(host_list)} unique host identifiers")
        
        return host_list
    
    def resolve_host_assemblies(self, species_list: List[str]) -> Dict[str, AssemblyMetadata]:
        """
        Resolve host species to best assembly for each
        
        This is the intermediary step that gathers assembly accessions and metadata
        before any downloads occur.
        
        Args:
            species_list: List of species names to resolve
            
        Returns:
            Dictionary mapping species name to best AssemblyMetadata
        """
        logging.info(f"🔍 Resolving {len(species_list)} species to assemblies...")
        
        resolved = {}
        failed = []
        
        for i, species in enumerate(species_list, 1):
            logging.info(f"[{i}/{len(species_list)}] Resolving {species}...")
            
            # Check if already in cache
            if species in self.assembly_cache:
                resolved[species] = self.assembly_cache[species]
                continue
            
            # Resolve to best assembly
            assembly = self.resolver.get_best_assembly(
                species,
                prefer_refseq=True,
                require_complete=False  # Don't require complete, but will rank higher
            )
            
            if assembly:
                resolved[species] = assembly
                self.assembly_cache[species] = assembly
                logging.info(f"   ✅ {assembly.assembly_accession} ({assembly.assembly_level})")
            else:
                failed.append(species)
                logging.warning(f"   ❌ No assembly found")
        
        logging.info(f"✅ Resolved {len(resolved)}/{len(species_list)} species to assemblies")
        if failed:
            logging.warning(f"⚠️  Failed to resolve {len(failed)} species:")
            for species in failed[:10]:  # Show first 10
                logging.warning(f"   - {species}")
            if len(failed) > 10:
                logging.warning(f"   ... and {len(failed) - 10} more")
        
        return resolved
    
    def download_assembly_ftp(self, 
                              assembly: AssemblyMetadata,
                              output_subdir: Path) -> Tuple[bool, Dict[str, Path]]:
        """
        Download assembly files from NCBI FTP
        
        Uses FTP for sequence retrieval (not efetch), as recommended.
        
        Args:
            assembly: AssemblyMetadata with FTP path
            output_subdir: Output directory for this assembly
            
        Returns:
            Tuple of (success: bool, downloaded_files: Dict[file_type, path])
        """
        if not assembly.ftp_path:
            logging.error(f"❌ No FTP path for {assembly.assembly_accession}")
            return False, {}
        
        # Create assembly-specific directory
        output_subdir.mkdir(parents=True, exist_ok=True)
        
        # Determine base filename from FTP path
        # FTP path format: https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2
        base_name = assembly.ftp_path.split('/')[-1]
        
        # Determine which files to download
        files_to_download = GenomeFileType.get_essential_files()
        if self.download_optional_files:
            files_to_download.extend(GenomeFileType.get_optional_files())
        
        downloaded = {}
        success = True
        
        for file_suffix in files_to_download:
            file_name = base_name + file_suffix
            file_url = f"{assembly.ftp_path}/{file_name}"
            output_file = output_subdir / file_name
            
            # Check if file already exists
            if self.skip_existing and output_file.exists():
                # Validate file if checksums enabled
                if self.validate_checksums:
                    if self._validate_file(output_file):
                        logging.debug(f"   ✓ Skipping existing file: {file_name}")
                        downloaded[file_suffix] = output_file
                        continue
                    else:
                        logging.warning(f"   ⚠️  Existing file failed validation: {file_name}")
                        output_file.unlink()  # Delete corrupted file
                else:
                    logging.debug(f"   ✓ Skipping existing file: {file_name}")
                    downloaded[file_suffix] = output_file
                    continue
            
            # Download file
            try:
                logging.info(f"   Downloading {file_name}...")
                urllib.request.urlretrieve(file_url, output_file)
                
                # Validate download
                if self.validate_checksums and not self._validate_file(output_file):
                    logging.error(f"   ❌ Downloaded file failed validation: {file_name}")
                    output_file.unlink()
                    success = False
                    continue
                
                downloaded[file_suffix] = output_file
                logging.info(f"   ✅ Downloaded {file_name} ({output_file.stat().st_size / 1024 / 1024:.2f} MB)")
                
            except urllib.error.HTTPError as e:
                if file_suffix in GenomeFileType.get_essential_files():
                    logging.error(f"   ❌ Failed to download essential file {file_name}: {e}")
                    success = False
                else:
                    logging.warning(f"   ⚠️  Optional file not available: {file_name}")
                    
            except Exception as e:
                if file_suffix in GenomeFileType.get_essential_files():
                    logging.error(f"   ❌ Error downloading {file_name}: {e}")
                    success = False
                else:
                    logging.warning(f"   ⚠️  Could not download optional file {file_name}: {e}")
        
        return success, downloaded
    
    def _validate_file(self, file_path: Path) -> bool:
        """
        Validate file integrity (fast path for resume loops).

        Checks:
        1. File exists and has non-zero size
        2. For ``*.fna.gz`` files, peek at the first 64KB for a FASTA
           header + sequence content instead of scanning the whole file.
           Full scans made every ``skip_existing`` resume re-read ~40GB.

        Note: Could be enhanced with MD5 checksum validation using NCBI's
        checksum files for more rigorous validation.
        """
        if not file_path.exists():
            return False

        try:
            if file_path.stat().st_size == 0:
                return False
        except OSError:
            return False

        # Lightweight header peek for gzipped FASTA (skip full-file scan).
        if file_path.suffix == '.gz' and '.fna' in file_path.name:
            try:
                with gzip.open(file_path, 'rt') as f:
                    head = f.read(65536)
                if not head:
                    return False
                return ('>' in head) and any(c in head for c in 'ACGTN')
            except Exception as e:
                logging.debug(f"FASTA validation failed for {file_path}: {e}")
                return False

        # Plain .fna: size check + 4K header probe (avoids hanging on
        # bad-block extents beyond the first pages during resume skips).
        if '.fna' in file_path.name:
            try:
                with open(file_path, 'r') as f:
                    head = f.read(4096)
                if not head:
                    return False
                # Accept headerless sequence files as long as non-empty;
                # stats step will decide.
                return True
            except Exception as e:
                logging.debug(f"FASTA validation failed for {file_path}: {e}")
                return False

        return True
    
    @staticmethod
    def _stream_genome_stats(fasta_path: Path) -> Tuple[Optional[int], Optional[float]]:
        """Byte-streaming length/GC count without Biopython object overhead.

        Skips ``>`` header lines, counts all other non-whitespace bases
        towards length (matching legacy ``len(seq)`` semantics) and
        ``G``/``C`` (case-insensitive) towards GC. Reads 1MB binary chunks
        so single huge contig lines never materialise as giant strings.
        """
        opener = gzip.open if str(fasta_path).endswith('.gz') else open
        total_length = 0
        gc_count = 0
        buf = b''
        with opener(fasta_path, 'rb') as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                data = buf + chunk
                lines = data.split(b'\n')
                buf = lines.pop()
                for line in lines:
                    s = line.strip()
                    if not s or s.startswith(b'>'):
                        continue
                    total_length += len(s)
                    up = s.upper()
                    gc_count += up.count(b'G') + up.count(b'C')
            if buf:
                s = buf.strip()
                if s and not s.startswith(b'>'):
                    total_length += len(s)
                    up = s.upper()
                    gc_count += up.count(b'G') + up.count(b'C')
        if total_length > 0:
            return total_length, round((gc_count / total_length) * 100, 2)
        return None, None

    def calculate_genome_stats(self, fasta_path: Path) -> Tuple[Optional[int], Optional[float]]:
        """
        Calculate genome length and GC content from FASTA file.

        Hardened vs legacy ``SeqIO.parse`` loop:
        * size guard (``max_fasta_bytes``) bounds memory/time,
        * worker-thread timeout (``stats_timeout``) returns
          ``(None, None)`` instead of hanging the 5516-genome loop on a
          stuck read (e.g. bad-block ``D``-state like GCF_014191245.1).

        Note: an uninterruptible kernel read cannot be killed from
        userspace; on timeout the worker thread lingers but the parent
        loop continues and the accession is recorded as stats-failed.

        Args:
            fasta_path: Path to FASTA file (can be gzipped)

        Returns:
            Tuple of (genome_length, gc_content_percentage)
        """
        try:
            try:
                if Path(fasta_path).stat().st_size > self.max_fasta_bytes:
                    logging.warning(
                        f"   ⚠️  Skipping stats for oversized file "
                        f"{Path(fasta_path).name} "
                        f"({Path(fasta_path).stat().st_size:,} bytes)"
                    )
                    return None, None
            except OSError as e:
                logging.warning(f"   ⚠️  Could not stat genome file: {e}")
                return None, None

            # Use daemon thread so timeout does not block process exit (previous non-daemon worker kept PID 128 alive)
            import threading
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="genome_stats")
            # Force worker threads to be daemon — allows Snakemake to exit even if read is stuck in kernel
            try:
                # Private but stable: ThreadPoolExecutor stores threads in _threads
                for t in getattr(executor, "_threads", set()):
                    t.daemon = True
            except Exception:
                pass
            try:
                future = executor.submit(self._stream_genome_stats, Path(fasta_path))
                # Also mark newly created thread as daemon (race-safe)
                try:
                    for t in getattr(executor, "_threads", set()):
                        t.daemon = True
                except Exception:
                    pass
                try:
                    return future.result(timeout=self.stats_timeout)
                except FuturesTimeoutError:
                    logging.warning(
                        f"   ⚠️  Genome stats timed out after "
                        f"{self.stats_timeout}s: {Path(fasta_path).name} "
                        f"({Path(fasta_path).stat().st_size if Path(fasta_path).exists() else 'missing'} bytes) "
                        f"— recording as failed, continuing"
                    )
                    try:
                        future.cancel()
                    except Exception:
                        pass
                    return None, None
            finally:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
        except Exception as e:
            logging.warning(f"   ⚠️  Could not calculate genome stats: {e}")
            return None, None
    
    def create_host_fasta(self, assembly: AssemblyMetadata, downloaded_files: Dict[str, Path]) -> Optional[Path]:
        """
        Create individual host FASTA file from downloaded genomic FASTA
        
        Extracts and decompresses the genomic FASTA for use in downstream analysis.
        
        Args:
            assembly: AssemblyMetadata
            downloaded_files: Dict of downloaded files
            
        Returns:
            Path to created FASTA file or None
        """
        if GenomeFileType.GENOMIC_FNA not in downloaded_files:
            return None
        
        source_file = downloaded_files[GenomeFileType.GENOMIC_FNA]
        
        # Create output filename: {Assembly_Accession}.fna
        output_file = self.output_dir / f"{assembly.assembly_accession.replace('.', '_')}.fna"
        
        # Skip if exists and validated
        if self.skip_existing and output_file.exists():
            if self._validate_file(output_file):
                return output_file
            else:
                # Remove corrupted file
                output_file.unlink()
        
        # Decompress via chunked binary copy to .tmp + atomic replace
        # (legacy f_in.read() materialised the whole genome as one str).
        tmp_file = output_file.with_suffix(output_file.suffix + ".tmp")
        try:
            with gzip.open(source_file, 'rb') as f_in:
                with open(tmp_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out, length=1024 * 1024)
                    f_out.flush()
                    try:
                        os.fsync(f_out.fileno())
                    except OSError:
                        pass
            # 4K readability probe before publishing
            try:
                with open(tmp_file, 'rb') as probe:
                    if not probe.read(4096):
                        raise IOError("decompressed file is empty")
            except Exception as probe_exc:
                tmp_file.unlink(missing_ok=True)
                raise IOError(f"readability probe failed: {probe_exc}")
            tmp_file.replace(output_file)

            logging.info(f"   ✅ Created host FASTA: {output_file.name}")
            return output_file

        except Exception as e:
            logging.error(f"   ❌ Failed to create host FASTA: {e}")
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
            if output_file.exists():
                try:
                    # Leave pre-existing valid file alone; only remove if
                    # we just created a partial file (size 0).
                    if output_file.stat().st_size == 0:
                        output_file.unlink()
                except OSError:
                    pass
            return None
    
    def _generate_candidates(self, phage_df: pd.DataFrame) -> pd.DataFrame:
        """Parse every phage row's Host field and return a candidates dataframe.

        One row per (Phage_ID, HostToken) pair.  Rows without valid tokens are
        excluded (e.g. phages with ``Host == '-'``).

        Args:
            phage_df: Phage metadata dataframe with at least a ``Host`` column.

        Returns:
            DataFrame with columns ``Phage_ID``, ``Host_Raw``, ``Host_Token``,
            ``Token_Type``, ``Token_Order``, sorted by *Phage_ID* then
            *Token_Order*.
        """
        _COLS = ['Phage_ID', 'Host_Raw', 'Host_Token', 'Token_Type', 'Token_Order']
        records: List[Dict] = []

        for _, row in phage_df.iterrows():
            phage_id = str(row.get('Phage_ID', row.get('phage_id', ''))).strip()
            host_raw = str(row.get('Host', '')).strip()

            if not phage_id:
                continue

            for token in parse_host_field(host_raw):
                records.append({
                    'Phage_ID': phage_id,
                    'Host_Raw': host_raw,
                    'Host_Token': token.token,
                    'Token_Type': token.token_type,
                    'Token_Order': token.token_order,
                })

        df = pd.DataFrame(records, columns=_COLS)
        if not df.empty:
            df = df.sort_values(['Phage_ID', 'Token_Order']).reset_index(drop=True)
        return df

    def _build_assembly_links(
        self,
        candidates_df: pd.DataFrame,
        token_to_assemblies: Dict[str, List[AssemblyMetadata]],
    ) -> pd.DataFrame:
        """Build phage_host_assemblies rows from candidates and resolved assemblies.

        Args:
            candidates_df:      Output of :meth:`_generate_candidates`.
            token_to_assemblies: Mapping from *token string* to list of
                                  :class:`AssemblyMetadata` (best first).

        Returns:
            DataFrame with one row per (Phage_ID, Assembly_Accession) link,
            sorted by *Phage_ID*, *Token_Order*, *Resolution_Rank*.
        """
        _COLS = [
            'Phage_ID', 'Host_Raw', 'Host_Token', 'Token_Type', 'Token_Order',
            'Assembly_Accession', 'Resolution_Source', 'Resolution_Rank',
            'Confidence', 'Assembly_Level', 'RefSeq_Category', 'Quality_Score',
            'Ambiguous', 'Ambiguity_Reason',
        ]

        if candidates_df.empty:
            return pd.DataFrame(columns=_COLS)

        records: List[Dict] = []
        for _, row in candidates_df.iterrows():
            token_str = row['Host_Token']
            assemblies = token_to_assemblies.get(token_str, [])

            resolution_source, base_confidence = _resolution_params(row['Token_Type'])
            ambiguous = len(assemblies) > 1
            reason = _ambiguity_reason(len(assemblies))

            for rank, asm in enumerate(assemblies, start=1):
                records.append({
                    'Phage_ID': row['Phage_ID'],
                    'Host_Raw': row['Host_Raw'],
                    'Host_Token': token_str,
                    'Token_Type': row['Token_Type'],
                    'Token_Order': row['Token_Order'],
                    'Assembly_Accession': asm.assembly_accession,
                    'Resolution_Source': resolution_source,
                    'Resolution_Rank': rank,
                    'Confidence': _calculate_confidence(base_confidence, rank),
                    'Assembly_Level': asm.assembly_level,
                    'RefSeq_Category': asm.refseq_category,
                    'Quality_Score': asm.get_quality_score(),
                    'Ambiguous': ambiguous,
                    'Ambiguity_Reason': reason,
                })

        df = pd.DataFrame(records, columns=_COLS)
        if not df.empty:
            df = df.sort_values(
                ['Phage_ID', 'Token_Order', 'Resolution_Rank']
            ).reset_index(drop=True)
        return df

    def _filter_non_bacterial_assemblies(
        self,
        token_to_assemblies: Dict[str, List[AssemblyMetadata]],
    ) -> Tuple[Dict[str, List[AssemblyMetadata]], List[str]]:
        """Filter out assemblies that do not belong to the Bacteria domain.

        For each resolved token, every assembly whose ``species_taxid`` can be
        confirmed as non-bacterial (via :meth:`AssemblyResolver.is_bacterial_taxid`)
        is removed and logged.  Assemblies without a TaxID, or whose bacterial
        status cannot be determined (lookup returns ``None``), are kept with an
        appropriate warning so that uncertain cases are not silently discarded.

        Args:
            token_to_assemblies: Mapping from host token string to the list of
                resolved :class:`AssemblyMetadata` objects for that token.

        Returns:
            A 2-tuple of:

            * the (mutated) *token_to_assemblies* dict with non-bacterial
              assemblies removed, and
            * a list of token strings that had *all* their assemblies removed
              because they resolved exclusively to non-bacterial organisms.
        """
        non_bacterial_tokens: List[str] = []
        for tok, assemblies in list(token_to_assemblies.items()):
            if not assemblies:
                continue
            bacterial_assemblies: List[AssemblyMetadata] = []
            token_has_non_bacterial = False
            for asm in assemblies:
                if asm.species_taxid is None:
                    # Cannot verify – keep and note at debug level
                    logging.debug(
                        f"No TaxID for assembly {asm.assembly_accession} "
                        f"('{asm.organism_name}'); including without bacterial check"
                    )
                    bacterial_assemblies.append(asm)
                    continue
                tax_key = str(asm.species_taxid)
                if tax_key in self._bacterial_cache:
                    is_bacterial = self._bacterial_cache[tax_key]
                else:
                    try:
                        is_bacterial = self.resolver.is_bacterial_taxid(asm.species_taxid)
                    except Exception as exc:
                        logging.warning(
                            f"⚠️  Bacterial check failed for TaxID {asm.species_taxid}: {exc}"
                        )
                        is_bacterial = None
                    self._bacterial_cache[tax_key] = is_bacterial
                if is_bacterial is False:
                    logging.warning(
                        f"⚠️  Non-bacterial host skipped: token '{tok}' resolved to "
                        f"'{asm.organism_name}' (TaxID {asm.species_taxid}), "
                        f"which is not in the Bacteria domain — excluding from pipeline"
                    )
                    token_has_non_bacterial = True
                elif is_bacterial is None:
                    logging.warning(
                        f"⚠️  Could not verify taxonomy for token '{tok}' resolved to "
                        f"'{asm.organism_name}' (TaxID {asm.species_taxid}); "
                        f"including in pipeline as bacterial status is unknown"
                    )
                    bacterial_assemblies.append(asm)
                else:
                    bacterial_assemblies.append(asm)
            token_to_assemblies[tok] = bacterial_assemblies
            if token_has_non_bacterial and not bacterial_assemblies:
                non_bacterial_tokens.append(tok)
        self._save_bacterial_cache()
        return token_to_assemblies, non_bacterial_tokens

    def process_all_hosts(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Main processing pipeline: parse hosts, resolve to assemblies, download.

        Multi-host aware: each phage may yield several host candidates, each
        resolved to one or more assembly accessions.

        New outputs written during this method:

        * **phage_host_candidates.csv** – one row per (Phage_ID, HostToken).
        * **phage_host_assemblies.csv** – one row per (Phage_ID,
          Assembly_Accession) link with rank + confidence + provenance.

        Existing (backward-compatible) outputs:

        * host_metadata.csv (per assembly)
        * assembly_metadata.csv (detailed per assembly)
        * phage_host_links.csv (phage→assembly links)

        Returns:
            Tuple of ``(host_metadata_df, assembly_metadata_df,
            phage_host_links_df)``.
        """
        logging.info("📋 Starting multi-host processing pipeline...")

        # ------------------------------------------------------------------
        # Stage 1: Parse host fields into candidates (seed-reuse on resume)
        # ------------------------------------------------------------------
        candidates_df = None
        if self.skip_existing and self._is_fresh(
            self.phage_host_candidates_output, self.phage_csv_path
        ):
            try:
                candidates_df = pd.read_csv(self.phage_host_candidates_output)
                if not candidates_df.empty and 'Host_Token' in candidates_df.columns:
                    logging.info(
                        f"   ↩️  Reusing {len(candidates_df)} candidate rows from "
                        f"{self.phage_host_candidates_output.name} (skipped re-parse)"
                    )
            except Exception as exc:
                logging.warning(f"⚠️  Could not reuse candidates CSV: {exc}")
                candidates_df = None
        if candidates_df is None:
            phage_df = pd.read_csv(self.phage_csv_path)
            candidates_df = self._generate_candidates(phage_df)

            self._atomic_write_csv(candidates_df, self.phage_host_candidates_output)
            logging.info(
                f"✅ Written {len(candidates_df)} candidate rows to "
                f"{self.phage_host_candidates_output}"
            )

        # ------------------------------------------------------------------
        # Stage 2: Resolve each unique token to assemblies
        # ------------------------------------------------------------------
        # Deduplicate tokens: same token string → resolve once
        unique_tokens: Dict[str, str] = {}  # token → token_type (first seen)
        for _, row in candidates_df.iterrows():
            tok = row['Host_Token']
            if tok not in unique_tokens:
                unique_tokens[tok] = row['Token_Type']

        logging.info(f"🔍 Resolving {len(unique_tokens)} unique host tokens…")
        token_to_assemblies: Dict[str, List[AssemblyMetadata]] = {}

        for i, (tok, tok_type) in enumerate(unique_tokens.items(), 1):
            logging.info(f"[{i}/{len(unique_tokens)}] Resolving '{tok}' ({tok_type})…")

            if tok in self.token_resolution_cache:
                token_to_assemblies[tok] = self.token_resolution_cache[tok]
                cached_assemblies = token_to_assemblies[tok]
                if cached_assemblies:
                    logging.info(f"   ✓ Cached token resolution: {cached_assemblies[0].assembly_accession}")
                else:
                    logging.info("   ✓ Cached token resolution: no assembly")
                continue

            # Check assembly_cache (populated by resolve_host_assemblies() too)
            if tok in self.assembly_cache:
                cached = self.assembly_cache[tok]
                token_to_assemblies[tok] = [cached] if cached else []
                logging.info(f"   ✓ Cached: {cached.assembly_accession if cached else 'none'}")
                continue

            assemblies = self.resolver.resolve(tok, prefer_refseq=True, max_results=1)
            token_to_assemblies[tok] = assemblies

            if assemblies:
                self.assembly_cache[tok] = assemblies[0]
                logging.info(f"   ✅ {assemblies[0].assembly_accession}")
            else:
                logging.warning(f"   ❌ No assembly found for '{tok}'")

        self._save_token_resolution_cache(token_to_assemblies)
        logging.info(
            f"✅ Updated token resolution cache: {self.host_resolution_cache_output}"
        )

        # ------------------------------------------------------------------
        # Stage 2b: Verify resolved assemblies are bacterial; log and remove
        # any that belong to non-bacterial organisms (e.g. human, mouse).
        # ------------------------------------------------------------------
        token_to_assemblies, non_bacterial_tokens = self._filter_non_bacterial_assemblies(
            token_to_assemblies
        )
        if non_bacterial_tokens:
            logging.warning(
                f"⚠️  {len(non_bacterial_tokens)} host token(s) were excluded because "
                f"they resolved to non-bacterial organisms: "
                + ", ".join(f"'{t}'" for t in non_bacterial_tokens)
            )
        else:
            logging.info("✅ All resolved hosts verified as bacterial")

        # ------------------------------------------------------------------
        # Stage 3: Build phage_host_assemblies
        # ------------------------------------------------------------------
        assembly_links_df = self._build_assembly_links(candidates_df, token_to_assemblies)
        assembly_links_df.to_csv(self.phage_host_assemblies_output, index=False)
        logging.info(
            f"✅ Written {len(assembly_links_df)} assembly link rows to "
            f"{self.phage_host_assemblies_output}"
        )

        # ------------------------------------------------------------------
        # Stage 4: Collect unique assemblies and download
        # ------------------------------------------------------------------
        # One AssemblyMetadata per unique accession (deduplicated)
        all_assembly_meta: Dict[str, AssemblyMetadata] = {}
        for asms in token_to_assemblies.values():
            for asm in asms:
                if asm.assembly_accession not in all_assembly_meta:
                    all_assembly_meta[asm.assembly_accession] = asm

        host_records: List[Dict] = []
        assembly_records: List[Dict] = []

        # Host seed for resume: skipped accessions still need a host row
        # (legacy code `continue`d before creating one, dropping them from
        # host_metadata.csv on resume). Prefer checkpoint, then final output.
        host_seed: Dict[str, Dict] = {}
        for host_candidate in (self.host_checkpoint_output, self.metadata_output):
            if not host_candidate.exists():
                continue
            try:
                _hdf = pd.read_csv(host_candidate)
                if not _hdf.empty and 'Assembly_Accession' in _hdf.columns:
                    for _, _hrow in _hdf.iterrows():
                        host_seed[str(_hrow['Assembly_Accession'])] = _hrow.to_dict()
                    if host_seed:
                        logging.info(
                            f"   ↩️  Loaded {len(host_seed)} host seed rows from "
                            f"{host_candidate.name}"
                        )
                        break
            except Exception as exc:
                logging.debug(f"Could not load host seed from {host_candidate}: {exc}")

        for i, (accession, assembly) in enumerate(all_assembly_meta.items(), 1):
            try:
                logging.info(
                    f"[{i}/{len(all_assembly_meta)}] Processing "
                    f"{assembly.organism_name} ({accession})…"
                )

                # Skip if already downloaded and cached
                if accession in self.existing_metadata and self.skip_existing:
                    logging.info("   ✓ Already processed, skipping")
                    assembly_records.append(self.existing_metadata[accession])
                    if accession in host_seed:
                        host_records.append(host_seed[accession])
                    else:
                        # Reconstruct minimal host row; stats recomputed
                        # bounded (timeout) from the existing .fna if present.
                        _gl, _gc = None, None
                        _existing_fna = self.output_dir / f"{accession.replace('.', '_')}.fna"
                        if _existing_fna.exists():
                            try:
                                _size = _existing_fna.stat().st_size
                            except OSError:
                                _size = -1
                            logging.info(f"   ↻ Re-stat {accession} {_existing_fna.name} {_size:,} bytes…")
                            _gl, _gc = self.calculate_genome_stats(_existing_fna)
                            if _gl is None:
                                logging.warning(f"   ⚠️  Re-stat failed for {accession} — keeping '-' and continuing")
                        host_records.append({
                            'Host_ID': accession.replace('.', '_'),
                            'Species_Name': assembly.organism_name,
                            'Strain_Name': assembly.strain or '-',
                            'Assembly_Accession': accession,
                            'Assembly_Name': assembly.assembly_name,
                            'Assembly_Level': assembly.assembly_level,
                            'Genome_Length': str(_gl) if _gl is not None else '-',
                            'GC_Content': str(_gc) if _gc is not None else '-',
                            'RefSeq_Category': assembly.refseq_category,
                            'Download_Date': datetime.now().strftime('%Y-%m-%d'),
                            'Source': 'assembly_resolver',
                        })
                    if self.checkpoint_every and (len(assembly_records) % self.checkpoint_every == 0):
                        self._flush_checkpoints(host_records, assembly_records)
                    continue

                # Download files (unless metadata-only mode)
                downloaded_files: Dict[str, Path] = {}
                download_success = True
                host_fasta = None
                genome_length = None
                gc_content = None

                if not self.metadata_only:
                    assembly_subdir = self.output_dir / "assemblies" / accession
                    download_success, downloaded_files = self.download_assembly_ftp(
                        assembly, assembly_subdir
                    )

                    if download_success:
                        host_fasta = self.create_host_fasta(assembly, downloaded_files)
                        if host_fasta and host_fasta.exists():
                            logging.info("   📊 Calculating genome statistics…")
                            genome_length, gc_content = self.calculate_genome_stats(host_fasta)
                            if genome_length is not None:
                                logging.info(f"   ✅ Length: {genome_length:,} bp, GC: {gc_content}%")
                            else:
                                logging.warning(
                                    f"   ⚠️  Stats unavailable for {accession} "
                                    f"(recorded as failed, continuing)"
                                )
                    else:
                        logging.warning(f"   ⚠️  Download failed for {accession}")
                        assembly_subdir_path = self.output_dir / "assemblies" / accession
                        if assembly_subdir_path.exists():
                            try:
                                shutil.rmtree(assembly_subdir_path)
                                logging.info("   🧹 Cleaned up partial download directory")
                            except Exception as exc:
                                logging.warning(f"   ⚠️  Could not clean up directory: {exc}")

                assembly_record = {
                    'Assembly_Accession': assembly.assembly_accession,
                    'Assembly_Name': assembly.assembly_name,
                    'Organism_Name': assembly.organism_name,
                    'Species_TaxID': assembly.species_taxid,
                    'Strain': assembly.strain or '-',
                    'Assembly_Level': assembly.assembly_level,
                    'RefSeq_Category': assembly.refseq_category,
                    'BioSample': assembly.biosample or '-',
                    'BioProject': assembly.bioproject or '-',
                    'FTP_Path': assembly.ftp_path or '-',
                    'Submission_Date': assembly.submission_date or '-',
                    'Is_Latest': assembly.is_latest,
                    'Quality_Score': assembly.get_quality_score(),
                    'Is_RefSeq': assembly.is_refseq(),
                    'Download_Status': (
                        'success' if download_success or self.metadata_only
                        else 'failed' if genome_length is None and not download_success
                        else 'stats_failed' if genome_length is None
                        else 'success'
                    ),
                    'Download_Date': datetime.now().strftime('%Y-%m-%d'),
                    'Metadata_Only': self.metadata_only,
                }
                # Refine status: download ok but stats failed (e.g. bad-block
                # GCF_014191245.1 retry) must not look like success.
                if (download_success or self.metadata_only) and genome_length is None and not self.metadata_only:
                    assembly_record['Download_Status'] = (
                        'success' if accession in self.existing_metadata else 'stats_failed'
                    )
                    # Fresh downloads with failed stats keep their files for
                    # forensics but don't block the loop.
                assembly_records.append(assembly_record)

                host_record = {
                    'Host_ID': assembly.assembly_accession.replace('.', '_'),
                    'Species_Name': assembly.organism_name,
                    'Strain_Name': assembly.strain or '-',
                    'Assembly_Accession': assembly.assembly_accession,
                    'Assembly_Name': assembly.assembly_name,
                    'Assembly_Level': assembly.assembly_level,
                    'Genome_Length': str(genome_length) if genome_length is not None else '-',
                    'GC_Content': str(gc_content) if gc_content is not None else '-',
                    'RefSeq_Category': assembly.refseq_category,
                    'Download_Date': datetime.now().strftime('%Y-%m-%d'),
                    'Source': 'assembly_resolver',
                }
                host_records.append(host_record)

                if self.checkpoint_every and (len(assembly_records) % self.checkpoint_every == 0):
                    self._flush_checkpoints(host_records, assembly_records)
                    logging.info(
                        f"   💾 Checkpoint: {len(assembly_records)} assemblies flushed "
                        f"({self.assembly_checkpoint_output.name})"
                    )
            except Exception as exc:
                # Per-accession isolation: one bad genome (bad blocks,
                # NCBI hiccup) must never kill the 5516-loop.
                logging.error(f"   ❌ Failed processing {accession}: {exc} — continuing")
                try:
                    assembly_records.append({
                        'Assembly_Accession': accession,
                        'Assembly_Name': getattr(assembly, 'assembly_name', '-'),
                        'Organism_Name': getattr(assembly, 'organism_name', '-'),
                        'Species_TaxID': getattr(assembly, 'species_taxid', '-'),
                        'Strain': getattr(assembly, 'strain', '-') or '-',
                        'Assembly_Level': getattr(assembly, 'assembly_level', '-'),
                        'RefSeq_Category': getattr(assembly, 'refseq_category', '-'),
                        'BioSample': getattr(assembly, 'biosample', '-') or '-',
                        'BioProject': getattr(assembly, 'bioproject', '-') or '-',
                        'FTP_Path': getattr(assembly, 'ftp_path', '-') or '-',
                        'Submission_Date': getattr(assembly, 'submission_date', '-') or '-',
                        'Is_Latest': getattr(assembly, 'is_latest', True),
                        'Quality_Score': 0,
                        'Is_RefSeq': False,
                        'Download_Status': 'failed',
                        'Download_Date': datetime.now().strftime('%Y-%m-%d'),
                        'Metadata_Only': self.metadata_only,
                    })
                    host_records.append({
                        'Host_ID': accession.replace('.', '_'),
                        'Species_Name': getattr(assembly, 'organism_name', '-'),
                        'Strain_Name': getattr(assembly, 'strain', '-') or '-',
                        'Assembly_Accession': accession,
                        'Assembly_Name': getattr(assembly, 'assembly_name', '-'),
                        'Assembly_Level': getattr(assembly, 'assembly_level', '-'),
                        'Genome_Length': '-',
                        'GC_Content': '-',
                        'RefSeq_Category': getattr(assembly, 'refseq_category', '-'),
                        'Download_Date': datetime.now().strftime('%Y-%m-%d'),
                        'Source': 'assembly_resolver',
                    })
                except Exception:
                    pass

        # Final checkpoint flush so a kill during Stage 5 still resumes Stage 4.
        self._flush_checkpoints(host_records, assembly_records)

        # ------------------------------------------------------------------
        # Stage 5: Build backward-compat phage_host_links from assembly_links
        # ------------------------------------------------------------------
        phage_host_links: List[Dict] = []
        seen_links: Set[Tuple[str, str]] = set()

        for _, row in assembly_links_df.iterrows():
            asm = all_assembly_meta.get(row['Assembly_Accession'])
            if not asm:
                continue
            link_key = (row['Phage_ID'], row['Assembly_Accession'])
            if link_key in seen_links:
                continue
            seen_links.add(link_key)
            phage_host_links.append({
                'Phage_ID': row['Phage_ID'],
                'Host_Species': asm.organism_name,
                'Host_Full_Name': row['Host_Raw'],
                'Assembly_Accession': row['Assembly_Accession'],
                'Assembly_Level': asm.assembly_level,
                'RefSeq_Category': asm.refseq_category,
                'Link_Quality': 'direct' if asm.is_refseq() else 'genbank',
            })

        host_df = pd.DataFrame(host_records)
        assembly_df = pd.DataFrame(assembly_records)
        links_df = pd.DataFrame(phage_host_links)

        return host_df, assembly_df, links_df

    
    def create_phage_host_links(self, assemblies: Dict[str, AssemblyMetadata]) -> List[Dict]:
        """
        Create phage-to-host assembly links
        
        Links each phage to its host's assembly accession.
        
        Args:
            assemblies: Dict mapping species name to AssemblyMetadata
            
        Returns:
            List of link records
        """
        logging.info("🔗 Creating phage-host assembly links...")
        
        # Read phage CSV
        phage_df = pd.read_csv(self.phage_csv_path)
        
        links = []
        for _, row in phage_df.iterrows():
            phage_id = row.get('Phage_ID', row.get('phage_id', ''))
            host = row.get('Host', '')
            
            if not host or host == '-' or not phage_id:
                continue
            
            # Extract species name from host
            parts = str(host).strip().split()
            if len(parts) >= 2 and parts[0][0].isupper():
                species = f"{parts[0]} {parts[1]}"
            elif len(parts) == 1 and parts[0][0].isupper():
                species = parts[0]
            else:
                continue
            
            # Find assembly for this species
            if species in assemblies:
                assembly = assemblies[species]
                links.append({
                    'Phage_ID': phage_id,
                    'Host_Species': species,
                    'Host_Full_Name': host,
                    'Assembly_Accession': assembly.assembly_accession,
                    'Assembly_Level': assembly.assembly_level,
                    'RefSeq_Category': assembly.refseq_category,
                    'Link_Quality': 'direct' if assembly.is_refseq() else 'genbank'
                })
        
        logging.info(f"✅ Created {len(links)} phage-host links")
        return links
    
    def run(self):
        """Execute complete pipeline"""
        logging.info("=" * 80)
        logging.info("ROBUST HOST GENOME DOWNLOADER")
        logging.info("=" * 80)

        start_time = time.time()

        # Process all hosts (writes candidates + assemblies CSVs internally)
        host_df, assembly_df, links_df = self.process_all_hosts()

        # Save backward-compatible outputs
        logging.info("💾 Saving outputs…")

        host_df.to_csv(self.metadata_output, index=False)
        logging.info(f"   ✅ Host metadata: {self.metadata_output}")

        assembly_df.to_csv(self.assembly_metadata_output, index=False)
        logging.info(f"   ✅ Assembly metadata: {self.assembly_metadata_output}")

        links_df.to_csv(self.phage_host_links_output, index=False)
        logging.info(f"   ✅ Phage-host links: {self.phage_host_links_output}")

        # (phage_host_candidates and phage_host_assemblies already written by
        # process_all_hosts() so Snakemake can track them as rule outputs.)

        # Checkpoints served their purpose — remove so the next run with
        # different inputs cannot accidentally reuse stale progress.
        for _cp in (self.assembly_checkpoint_output, self.host_checkpoint_output):
            try:
                _cp.unlink(missing_ok=True)
            except OSError as exc:
                logging.debug(f"Could not remove checkpoint {_cp}: {exc}")

        # Summary
        elapsed = time.time() - start_time
        logging.info("=" * 80)
        logging.info("SUMMARY")
        logging.info("=" * 80)
        logging.info(f"Total hosts processed: {len(host_df)}")
        logging.info(f"Total assemblies: {len(assembly_df)}")
        logging.info(f"Total phage-host links: {len(links_df)}")
        if not self.metadata_only:
            success_count = (
                len(assembly_df[assembly_df['Download_Status'] == 'success'])
                if not assembly_df.empty and 'Download_Status' in assembly_df.columns
                else 0
            )
            logging.info(f"Successful downloads: {success_count}/{len(assembly_df)}")
        logging.info(f"Time elapsed: {elapsed:.1f}s")
        logging.info("=" * 80)


def main():
    """Main entry point for Snakemake"""
    import argparse

    # For Snakemake integration
    if 'snakemake' in globals():
        # Route all logging explicitly to the Snakemake log file
        try:
            _common = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'common')
            if _common not in sys.path:
                sys.path.insert(0, _common)
            from logging_utils import setup_logging  # noqa: PLC0415
            setup_logging(snakemake.log[0])          # noqa: F821
        except Exception:
            Path(snakemake.log[0]).parent.mkdir(parents=True, exist_ok=True)  # noqa: F821
            fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            root = logging.getLogger()
            root.handlers.clear()
            root.setLevel(logging.INFO)
            fh = logging.FileHandler(snakemake.log[0])  # noqa: F821
            fh.setFormatter(fmt)
            root.addHandler(fh)
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(fmt)
            root.addHandler(sh)
    else:
        # Setup logging for command-line mode
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    # For Snakemake integration
    if 'snakemake' in globals():
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=snakemake.input.phage_csv,
            output_dir=snakemake.params.output_dir,
            metadata_output=snakemake.output.metadata,
            assembly_metadata_output=snakemake.output.get(
                'assembly_metadata',
                snakemake.output.metadata.replace('.csv', '_assemblies.csv'),
            ),
            phage_host_links_output=snakemake.output.get(
                'phage_host_links',
                snakemake.output.metadata.replace('.csv', '_phage_host_links.csv'),
            ),
            ncbi_email=os.environ.get('NCBI_EMAIL', 'your.email@example.com'),
            ncbi_api_key=os.environ.get('NCBI_API_KEY'),
            metadata_only=snakemake.params.get('metadata_only', False),
            skip_existing=snakemake.params.get('skip_existing', True),
            validate_checksums=snakemake.params.get('validate_checksums', True),
            download_optional_files=snakemake.params.get('download_optional_files', False),
            phage_host_candidates_output=snakemake.output.get('phage_host_candidates'),
            phage_host_assemblies_output=snakemake.output.get('phage_host_assemblies'),
            host_resolution_cache_output=snakemake.output.get('host_resolution_cache'),
            reuse_resolution_cache=snakemake.params.get('reuse_resolution_cache', True),
            host_resolution_cache_ttl_days=snakemake.params.get('host_resolution_cache_ttl_days', 120),
            stats_timeout=snakemake.params.get('stats_timeout', 60.0),
            checkpoint_every=snakemake.params.get('checkpoint_every', 100),
            max_fasta_bytes=snakemake.params.get('max_fasta_bytes', 500 * 1024 * 1024),
        )
        downloader.run()
    else:
        # Command line mode
        parser = argparse.ArgumentParser(description='Robust host genome downloader')
        parser.add_argument('--phage-csv', required=True, help='Phage metadata CSV')
        parser.add_argument('--output-dir', required=True, help='Output directory')
        parser.add_argument('--metadata-output', required=True, help='Host metadata output CSV')
        parser.add_argument('--assembly-metadata', help='Assembly metadata output CSV')
        parser.add_argument('--phage-host-links', help='Phage-host links output CSV')
        parser.add_argument('--phage-host-candidates', help='Phage-host candidates output CSV')
        parser.add_argument('--phage-host-assemblies', help='Phage-host assemblies output CSV')
        parser.add_argument('--host-resolution-cache', help='Host token resolution cache JSON output')
        parser.add_argument('--ncbi-email', default=os.environ.get('NCBI_EMAIL'), help='NCBI email')
        parser.add_argument('--ncbi-api-key', default=os.environ.get('NCBI_API_KEY'), help='NCBI API key')
        parser.add_argument('--metadata-only', action='store_true', help='Metadata only mode')
        parser.add_argument('--skip-existing', action='store_true', help='Skip existing files')
        parser.add_argument('--no-skip-existing', dest='skip_existing', action='store_false',
                            help='Re-download existing files')
        parser.set_defaults(skip_existing=True)
        parser.add_argument('--validate-checksums', action='store_true', help='Validate checksums')
        parser.add_argument('--no-validate-checksums', dest='validate_checksums',
                            action='store_false', help='Skip checksum validation')
        parser.set_defaults(validate_checksums=True)
        parser.add_argument('--download-optional', action='store_true', help='Download optional files')
        parser.add_argument('--no-resolution-cache', dest='reuse_resolution_cache', action='store_false',
                            help='Disable reuse of token resolution cache')
        parser.set_defaults(reuse_resolution_cache=True)
        parser.add_argument('--stats-timeout', type=float, default=60.0,
                            help='Per-file genome stats timeout in seconds')
        parser.add_argument('--checkpoint-every', type=int, default=100,
                            help='Flush Stage-4 checkpoints every N accessions')
        parser.add_argument('--max-fasta-bytes', type=int, default=500 * 1024 * 1024,
                            help='Skip stats for FASTA files larger than this')

        args = parser.parse_args()

        downloader = RobustHostGenomeDownloader(
            phage_csv_path=args.phage_csv,
            output_dir=args.output_dir,
            metadata_output=args.metadata_output,
            assembly_metadata_output=(
                args.assembly_metadata
                or args.metadata_output.replace('.csv', '_assemblies.csv')
            ),
            phage_host_links_output=(
                args.phage_host_links
                or args.metadata_output.replace('.csv', '_phage_host_links.csv')
            ),
            ncbi_email=args.ncbi_email,
            ncbi_api_key=args.ncbi_api_key,
            metadata_only=args.metadata_only,
            skip_existing=args.skip_existing,
            validate_checksums=args.validate_checksums,
            download_optional_files=args.download_optional,
            phage_host_candidates_output=args.phage_host_candidates,
            phage_host_assemblies_output=args.phage_host_assemblies,
            host_resolution_cache_output=args.host_resolution_cache,
            reuse_resolution_cache=args.reuse_resolution_cache,
            stats_timeout=args.stats_timeout,
            checkpoint_every=args.checkpoint_every,
            max_fasta_bytes=args.max_fasta_bytes,
        )
        downloader.run()


if __name__ == '__main__':
    main()

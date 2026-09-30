"""
sequence_retrieval.py
=====================

SequenceRetriever facade — orchestrates metadata queries, sequence retrieval,
and FASTA loading.

This module is the main entry point for the pbi package. It composes:
- MetadataQueriesMixin (metadata_queries.py) — DuckDB metadata queries
- SequenceOpsMixin (sequence_ops.py) — low-level sequence fetch
- fasta_index.py — FASTA loading and caching
- query_utils.py — SQL query parsing
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Union

import duckdb
import pandas as pd
from pyfaidx import Fasta

from .fasta_index import (
    MAX_HOST_FASTA_CACHE_SIZE,
    HostFastaCache,
    PrivatePhageFastaCache,
    _fasta_key_function,
    load_protein_fasta,
    _should_rebuild_fai,
)
from .fasta_utils import assemble_genome, get_genome_stats
from .metadata_queries import MetadataQueriesMixin
from .query_utils import parse_where_clause
from .sequence_ops import SequenceOpsMixin

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def _normalize_source_type(source_type: Optional[str]) -> str:
    """Normalize source type to canonical public/private labels."""
    normalized = str(source_type).strip().lower() if source_type is not None else ""
    return "private" if normalized == "private" else "public"


def _normalize_source_db(source_db: Optional[object]) -> Optional[str]:
    """Normalize source DB labels and discard empty/NaN-like values."""
    if source_db is None:
        return None
    normalized = str(source_db).strip()
    if not normalized or normalized.lower() == "nan":
        return None
    return normalized


class SequenceRetriever(MetadataQueriesMixin, SequenceOpsMixin):
    """
    Retrieve sequences from indexed FASTA files based on DuckDB queries.

    Features:
    - Lazy loading with background thread support
    - Query-based sequence retrieval from DuckDB
    - Direct ID-based retrieval
    - Batch processing support
    - Memory-efficient streaming

    This is a facade that composes MetadataQueriesMixin and SequenceOpsMixin.
    """

    def __init__(self, db_path: str, phage_fasta_path: str, protein_fasta_path: str,
                 host_fasta_path: Optional[str] = None, host_mapping_path: Optional[str] = None,
                 private_phage_mapping_path: Optional[str] = None,
                 preload: bool = True):
        """
        Initialize SequenceRetriever with lazy FASTA loading.

        Args:
            db_path: Path to DuckDB database
            phage_fasta_path: Path to indexed phage FASTA file (public sequences only)
            protein_fasta_path: Path to indexed protein FASTA file
            host_fasta_path: Path to indexed host FASTA file (DEPRECATED - use host_mapping_path)
            host_mapping_path: Path to JSON mapping file for individual host FASTA files
            private_phage_mapping_path: Path to JSON mapping ``source_db → phage.fasta`` for
                private datasets.
            preload: If True, load FASTA files in background thread (default: True)
        """
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        if not Path(phage_fasta_path).exists():
            raise FileNotFoundError(f"Phage FASTA not found: {phage_fasta_path}")
        if not Path(protein_fasta_path).exists():
            raise FileNotFoundError(f"Protein FASTA not found: {protein_fasta_path}")

        phage_index = Path(str(phage_fasta_path) + '.fai')
        protein_index = Path(str(protein_fasta_path) + '.fai')

        logging.info(f"📂 Checking FASTA index files:")
        logging.info(f"   Phage index: {phage_index.exists()} ({phage_index.stat().st_size / 1024:.1f} KB)")
        logging.info(f"   Protein index: {protein_index.exists()} ({protein_index.stat().st_size / 1024:.1f} KB)")

        if not phage_index.exists():
            raise FileNotFoundError(f"Phage FASTA index not found: {phage_index}")
        if not protein_index.exists():
            raise FileNotFoundError(f"Protein FASTA index not found: {protein_index}")

        # Initialize private phage mapping
        self._private_phage_mapping: Optional[Dict[str, str]] = None
        self._private_phage_source_lookup: Dict[str, str] = {}
        self._private_phage_fasta_cache = PrivatePhageFastaCache()

        if private_phage_mapping_path:
            _ppm = Path(private_phage_mapping_path)
            if _ppm.exists():
                with _ppm.open("r") as _f:
                    self._private_phage_mapping = json.load(_f)
                for _source_key in self._private_phage_mapping.keys():
                    _normalized_source = _normalize_source_db(_source_key)
                    if _normalized_source:
                        _norm_key = _normalized_source.lower()
                        _existing = self._private_phage_source_lookup.get(_norm_key)
                        if _existing is not None and _existing != _source_key:
                            logging.warning(
                                "⚠️ Duplicate normalized private source key '%s' for '%s' and '%s'; using '%s'",
                                _norm_key, _existing, _source_key, _existing,
                            )
                        else:
                            self._private_phage_source_lookup[_norm_key] = _source_key
                logging.info(
                    f"📂 Loaded private phage mapping for "
                    f"{len(self._private_phage_mapping)} sources: {list(self._private_phage_mapping.keys())}"
                )
            else:
                logging.debug(f"Private phage mapping not found: {private_phage_mapping_path}")

        # Initialize host data handling
        self._host_fasta_path = host_fasta_path
        self._host_mapping_path = host_mapping_path
        self._host_mapping = None
        self._host_fasta_cache = HostFastaCache()
        self._host_fasta = None
        self._host_lock = threading.Lock()
        self._host_count = None
        self._has_host_data = False
        self._use_host_mapping = False

        if host_mapping_path:
            if Path(host_mapping_path).exists():
                logging.info(f"📂 Using host mapping file: {host_mapping_path}")
                self._has_host_data = True
                self._use_host_mapping = True
                with open(host_mapping_path, 'r') as f:
                    self._host_mapping = json.load(f)
                self._host_count = len(self._host_mapping)
                logging.info(f"   Loaded mapping for {self._host_count} hosts")
            else:
                logging.warning(f"⚠️  Host mapping file not found: {host_mapping_path}")
        elif host_fasta_path:
            if Path(host_fasta_path).exists():
                host_index = Path(str(host_fasta_path) + '.fai')
                if host_index.exists():
                    logging.info(f"   Host index: {host_index.exists()} ({host_index.stat().st_size / 1024:.1f} KB)")
                    self._has_host_data = True
                else:
                    logging.warning(f"⚠️  Host FASTA index not found: {host_index}")
            else:
                logging.warning(f"⚠️  Host FASTA not found: {host_fasta_path}")

        # Initialize database connection
        logging.info(f"📂 Connecting to database: {db_path}")
        self.conn = duckdb.connect(db_path, read_only=True)

        # Store paths for lazy loading
        self._phage_fasta_path = phage_fasta_path
        self._protein_fasta_path = protein_fasta_path

        # Lazy-loaded FASTA objects
        self._phage_fasta = None
        self._protein_fasta = None

        # Thread synchronization
        self._phage_lock = threading.Lock()
        self._protein_lock = threading.Lock()
        self._loading_complete = threading.Event()

        # Stats
        self._phage_count = None
        self._protein_count = None

        if preload:
            logging.info("🔄 Starting background FASTA loading...")
            self._load_thread = threading.Thread(target=self._preload_fasta, daemon=True)
            self._load_thread.start()
            logging.info("✅ Initialization complete (FASTA loading in background)")
        else:
            logging.info("✅ Initialization complete (FASTA files will load on first use)")

    def _preload_fasta(self):
        """Background task to load FASTA files."""
        start_total = time.time()

        try:
            logging.info(f"🔄 [Background] Loading phage FASTA: {self._phage_fasta_path}")
            start = time.time()

            with self._phage_lock:
                self._phage_fasta = Fasta(
                    self._phage_fasta_path,
                    rebuild=False,
                    key_function=_fasta_key_function
                )
                self._phage_count = len(self._phage_fasta.keys())

            elapsed = time.time() - start
            logging.info(f"   ✅ Phage FASTA loaded in {elapsed:.2f}s ({self._phage_count:,} sequences)")

            logging.info(f"🔄 [Background] Loading protein FASTA: {self._protein_fasta_path}")
            start = time.time()

            with self._protein_lock:
                self._protein_fasta = _load_protein_fasta(self._protein_fasta_path)
                self._protein_count = len(self._protein_fasta.keys())

            elapsed = time.time() - start
            logging.info(f"   ✅ Protein FASTA loaded in {elapsed:.2f}s ({self._protein_count:,} sequences)")

            if self._has_host_data and self._host_fasta_path and not self._use_host_mapping:
                logging.info(f"🔄 [Background] Loading host FASTA: {self._host_fasta_path}")
                start = time.time()

                with self._host_lock:
                    self._host_fasta = Fasta(
                        self._host_fasta_path,
                        rebuild=False,
                        key_function=_fasta_key_function
                    )
                    self._host_count = len(self._host_fasta.keys())

                elapsed = time.time() - start
                logging.info(f"   ✅ Host FASTA loaded in {elapsed:.2f}s ({self._host_count:,} sequences)")
            elif self._use_host_mapping:
                logging.info(f"   ℹ️  Using on-demand loading for {self._host_count:,} individual host files")

            self._loading_complete.set()

            total_elapsed = time.time() - start_total
            logging.info(f"🎉 All FASTA files loaded in {total_elapsed:.2f}s")

        except Exception as e:
            logging.error(f"❌ Error loading FASTA files: {e}")
            import traceback
            traceback.print_exc()

    @property
    def phage_fasta(self):
        """Get phage FASTA, loading if necessary."""
        if self._phage_fasta is None:
            with self._phage_lock:
                if self._phage_fasta is None:
                    logging.info(f"📂 Loading phage FASTA on-demand: {self._phage_fasta_path}")
                    start = time.time()
                    self._phage_fasta = Fasta(
                        self._phage_fasta_path,
                        rebuild=False,
                        key_function=_fasta_key_function
                    )
                    elapsed = time.time() - start
                    logging.info(f"   ✅ Loaded in {elapsed:.2f}s")
        return self._phage_fasta

    @property
    def protein_fasta(self):
        """Get protein FASTA, loading if necessary."""
        if self._protein_fasta is None:
            with self._protein_lock:
                if self._protein_fasta is None:
                    logging.info(f"📂 Loading protein FASTA on-demand: {self._protein_fasta_path}")
                    start = time.time()
                    self._protein_fasta = _load_protein_fasta(self._protein_fasta_path)
                    elapsed = time.time() - start
                    logging.info(f"   ✅ Loaded in {elapsed:.2f}s")
        return self._protein_fasta

    @property
    def host_fasta(self):
        """
        Get host FASTA, loading if necessary.

        DEPRECATED: Use get_host_sequence() instead for individual host access.
        """
        if not self._has_host_data:
            raise ValueError("Host FASTA not configured - pass host_fasta_path or host_mapping_path to __init__")

        if self._use_host_mapping:
            raise ValueError(
                "Direct access to host_fasta is not available when using host_mapping_path. "
                "Use get_host_sequence(host_id) method instead to load individual host files on-demand."
            )

        if self._host_fasta is None:
            with self._host_lock:
                if self._host_fasta is None:
                    logging.info(f"📂 Loading host FASTA on-demand: {self._host_fasta_path}")
                    start = time.time()
                    self._host_fasta = Fasta(
                        self._host_fasta_path,
                        rebuild=False,
                        key_function=_fasta_key_function
                    )
                    elapsed = time.time() - start
                    logging.info(f"   ✅ Loaded in {elapsed:.2f}s")
        return self._host_fasta

    def _get_host_fasta_for_id(self, host_id: str) -> Fasta:
        """Get Fasta object for a specific host ID (used in mapping mode)."""
        if not self._use_host_mapping:
            raise RuntimeError("This method is only for host mapping mode")

        if host_id not in self._host_mapping:
            raise KeyError(f"Host ID '{host_id}' not found in mapping")

        fasta_path = self._host_mapping[host_id]
        return self._host_fasta_cache.get(host_id, fasta_path, path_resolver=self._resolve_host_fasta_path)

    def _resolve_host_fasta_path(self, host_id: str, mapped_path: str) -> str:
        """Resolve host FASTA path from mapping, with fallback search for stale paths."""
        path = Path(mapped_path)
        if path.exists():
            return str(path)

        if not path.is_absolute():
            cwd_candidate = Path.cwd() / path
            if cwd_candidate.exists():
                return str(cwd_candidate)

        candidate_roots = []
        env_private_root = os.getenv("PBI_PRIVATE_DATA_DIR")
        if env_private_root:
            candidate_roots.append(Path(env_private_root))
        candidate_roots.extend([
            Path("/private-data"),
            Path(__file__).resolve().parents[2] / "private_data",
            Path.cwd() / "private_data",
        ])

        expected_source = None
        if len(path.parts) >= 3 and path.parent.name == "hosts":
            expected_source = path.parent.parent.name or None

        seen = set()
        for root in candidate_roots:
            root_str = str(root.expanduser().resolve(strict=False))
            if root_str in seen:
                continue
            seen.add(root_str)
            if not root.exists():
                continue
            if root.is_file():
                continue

            matches = []
            if expected_source:
                preferred = root / expected_source / "hosts" / path.name
                if preferred.exists():
                    matches.append(preferred)

            if not matches:
                for source_dir in sorted(
                    (p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")),
                    key=lambda p: p.name,
                ):
                    candidate = source_dir / "hosts" / path.name
                    if candidate.exists():
                        matches.append(candidate)

            if not matches:
                matches = sorted(root.glob(f"*/hosts/{path.name}"))

            if matches:
                resolved = matches[0]
                logging.warning(
                    "⚠️ Resolved missing host mapping path for %s: %s -> %s",
                    host_id, mapped_path, resolved,
                )
                self._host_mapping[host_id] = str(resolved)
                return str(resolved)

        return mapped_path

    def _resolve_private_phage_fasta_path(self, source_db: str, mapped_path: str) -> str:
        """Resolve private phage FASTA path from mapping, with fallback for stale mounts."""
        path = Path(mapped_path)
        if path.exists():
            return str(path)

        if not path.is_absolute():
            cwd_candidate = Path.cwd() / path
            if cwd_candidate.exists():
                return str(cwd_candidate)

        candidate_roots = []
        env_private_root = os.getenv("PBI_PRIVATE_DATA_DIR")
        if env_private_root:
            candidate_roots.append(Path(env_private_root))
        candidate_roots.extend([
            Path("/private-data"),
            Path(__file__).resolve().parents[2] / "private_data",
            Path.cwd() / "private_data",
        ])

        seen = set()
        for root in candidate_roots:
            root_str = str(root.expanduser().absolute())
            if root_str in seen:
                continue
            seen.add(root_str)
            if not root.exists() or not root.is_dir():
                continue

            matches = []
            mapped_norm = path.as_posix()
            private_data_prefix = "/private-data/"
            if private_data_prefix in mapped_norm:
                remapped_suffix = mapped_norm.split(private_data_prefix, 1)[1]
                remapped = root / Path(remapped_suffix)
                if remapped.exists():
                    matches.append(remapped)

            preferred = root / source_db / "phage.fasta"
            if preferred.exists():
                matches.append(preferred)

            intermediate = root / "private_phage_genomes_intermediate" / source_db / "phage.fasta"
            if intermediate.exists():
                matches.append(intermediate)

            if not matches:
                for candidate in sorted(root.glob(f"*/{source_db}/phage.fasta")):
                    try:
                        relative_parts = candidate.relative_to(root).parts
                    except ValueError:
                        continue
                    if any(part.startswith(".") for part in relative_parts):
                        continue
                    matches.append(candidate)
                    break

            if matches:
                resolved = matches[0]
                logging.warning(
                    "⚠️ Resolved missing private phage mapping path for source %s: %s -> %s",
                    source_db, mapped_path, resolved,
                )
                self._private_phage_mapping[source_db] = str(resolved)
                return str(resolved)

        return mapped_path

    def _resolve_private_source_db(self, source_db: Optional[object]) -> Optional[str]:
        """Resolve a DB-provided source label to a canonical private mapping key."""
        normalized_source = _normalize_source_db(source_db)
        if normalized_source is None or not self._private_phage_mapping:
            return None
        if normalized_source in self._private_phage_mapping:
            return normalized_source
        return self._private_phage_source_lookup.get(normalized_source.lower())

    def _get_private_phage_fasta(self, source_db: str) -> Fasta:
        """
        Load (and LRU-cache) the phage FASTA for a private source.

        Private phage FASTAs live in per-source directories under
        ``private_phage_genomes_intermediate/<source_db>/phage.fasta``.
        """
        resolved_source_db = self._resolve_private_source_db(source_db)
        if (
            self._private_phage_mapping is None
            or resolved_source_db is None
            or resolved_source_db not in self._private_phage_mapping
        ):
            raise KeyError(f"Private phage source '{source_db}' not found in private_phage_mapping")

        fasta_path = self._private_phage_mapping[resolved_source_db]
        return self._private_phage_fasta_cache.get(
            resolved_source_db, fasta_path,
            path_resolver=self._resolve_private_phage_fasta_path,
        )

    def get_host_sequence(self, host_id: str, contig_mode: str = "first") -> str:
        """Get sequence for a specific host ID."""
        if not self._has_host_data:
            raise ValueError("Host FASTA not configured")

        if contig_mode not in ("first", "concat"):
            raise ValueError(f"contig_mode must be 'first' or 'concat', got '{contig_mode}'.")

        if self._use_host_mapping:
            fasta_obj = self._get_host_fasta_for_id(host_id)
            if not fasta_obj.keys():
                raise KeyError(f"No sequences found in host file for {host_id}")
            return assemble_genome(fasta_obj, mode=contig_mode)
        else:
            return str(self.host_fasta[host_id][:].seq)

    def get_host_genome(
        self,
        host_id: str,
        mode: str = "concat",
        gap: int = 0,
        order: str = "length_desc",
    ) -> Union[str, List[str], Dict[str, str]]:
        """Retrieve the full genome for a host, handling multi-contig FASTA files."""
        if not self._has_host_data:
            raise ValueError("Host FASTA not configured")

        if self._use_host_mapping:
            fasta_obj = self._get_host_fasta_for_id(host_id)
            if not fasta_obj.keys():
                raise KeyError(f"No sequences found in host file for {host_id}")
            return assemble_genome(fasta_obj, mode=mode, gap=gap, order=order)
        else:
            seq = str(self.host_fasta[host_id][:].seq)
            if mode == "list":
                return [seq]
            if mode == "dict":
                return {host_id: seq}
            return seq

    def get_host_genome_stats(
        self,
        host_id: str,
        order: str = "length_desc",
    ) -> Dict[str, object]:
        """Return contig statistics for a host genome FASTA."""
        if not self._has_host_data:
            raise ValueError("Host FASTA not configured")

        if self._use_host_mapping:
            fasta_obj = self._get_host_fasta_for_id(host_id)
            return get_genome_stats(fasta_obj, order=order)
        else:
            seq = str(self.host_fasta[host_id][:].seq)
            length = len(seq)
            return {"contig_count": 1, "lengths": [length], "total_length": length}

    def get_phage_genome(
        self,
        phage_id: str,
        mode: str = "concat",
        gap: int = 0,
        order: str = "length_desc",
    ) -> Union[str, List[str], Dict[str, str]]:
        """Retrieve the full genome for a phage, handling multi-contig cases."""
        source_db: Optional[str] = None
        source_type_val: Optional[str] = None
        if self._private_phage_mapping:
            try:
                row = self.conn.execute(
                    "SELECT Source_DB, source_type FROM fact_phages WHERE Phage_ID = ? LIMIT 1",
                    [phage_id],
                ).fetchone()
                if row:
                    source_db, source_type_val = row
            except Exception:
                pass

        seq = self._get_phage_sequence(phage_id, source_db=source_db, source_type=source_type_val)
        if seq is None:
            raise KeyError(f"Phage ID '{phage_id}' not found in phage FASTA.")

        if mode == "list":
            return [seq]
        if mode == "dict":
            return {phage_id: seq}
        return seq

    def wait_until_ready(self, timeout: Optional[float] = None):
        """Wait for background loading to complete."""
        if not hasattr(self, '_load_thread'):
            return True

        logging.info("⏳ Waiting for FASTA loading to complete...")
        result = self._loading_complete.wait(timeout=timeout)

        if result:
            logging.info("✅ FASTA loading complete")
        else:
            logging.warning(f"⚠️ Timeout after {timeout}s - FASTA may still be loading")

        return result

    def is_ready(self) -> bool:
        """Check if FASTA files are loaded."""
        return self._loading_complete.is_set()

    def get_phage_sequences(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Get phage sequences based on SQL query."""
        _ = self.phage_fasta

        logging.info(f"🔍 Executing query: {query[:100]}...")

        if limit:
            query = f"{query} LIMIT {limit}"

        result = self.conn.execute(query).fetchdf()

        if 'Phage_ID' not in result.columns:
            raise ValueError("Query must return 'Phage_ID' column")

        phage_ids = result['Phage_ID'].tolist()
        logging.info(f"📊 Retrieved {len(phage_ids):,} Phage IDs from query")

        return self._fetch_phage_sequences(phage_ids)

    def get_protein_sequences(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Get protein sequences based on SQL query."""
        _ = self.protein_fasta

        logging.info(f"🔍 Executing query: {query[:100]}...")

        if limit:
            query = f"{query} LIMIT {limit}"

        result = self.conn.execute(query).fetchdf()

        if 'Protein_ID' not in result.columns:
            raise ValueError("Query must return 'Protein_ID' column")

        protein_ids = result['Protein_ID'].tolist()
        logging.info(f"📊 Retrieved {len(protein_ids):,} Protein IDs from query")

        return self._fetch_protein_sequences(protein_ids)

    def get_host_sequences(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """Get host sequences based on SQL query."""
        if not self._has_host_data:
            raise ValueError(
                "Host data not available. Please run the host genome download workflow first:\n"
                "  snakemake --use-conda --cores 1 all_hosts\n"
                "Or check that host_fasta_path or host_mapping_path was provided when creating SequenceRetriever."
            )

        if not self._use_host_mapping:
            _ = self.host_fasta

        logging.info(f"🔍 Executing query: {query[:100]}...")

        if limit:
            query = f"{query} LIMIT {limit}"

        result = self.conn.execute(query).fetchdf()

        if 'Host_ID' not in result.columns:
            raise ValueError("Query must return 'Host_ID' column")

        host_ids = result['Host_ID'].tolist()
        logging.info(f"📊 Retrieved {len(host_ids):,} Host IDs from query")

        return self._fetch_host_sequences(host_ids)

    def get_host_by_phage(self, phage_id: str) -> pd.DataFrame:
        """Get host genome(s) for a given phage."""
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")

        query = f"""
        SELECT h.Host_ID
        FROM phage_host_associations pha
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        WHERE pha.Phage_ID = '{phage_id}'
        """

        return self.get_host_sequences(query)

    def get_phage_host_pairs(
        self,
        where_clause: str = None,
        limit: Optional[int] = None,
        host_contig_mode: str = "concat",
        phage_contig_mode: str = "first",
    ) -> pd.DataFrame:
        """Get phage-host interaction pairs with sequences and metadata."""
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")

        for mode_name, mode_val in (
            ("host_contig_mode", host_contig_mode),
            ("phage_contig_mode", phage_contig_mode),
        ):
            if mode_val not in ("first", "concat"):
                raise ValueError(f"{mode_name} must be 'first' or 'concat', got '{mode_val}'.")

        _ = self.phage_fasta
        if not self._use_host_mapping:
            _ = self.host_fasta

        query = """
        SELECT DISTINCT
            pha.Phage_ID,
            pha.Host_ID,
            p.Source_DB as Phage_Source,
            CASE
                WHEN LOWER(TRIM(COALESCE(p.source_type, ''))) = 'private' THEN 'private'
                ELSE 'public'
            END as Phage_Source_Type,
            p.Length as Phage_Length,
            p.GC_content as Phage_GC,
            p.Taxonomy as Phage_Taxonomy,
            p.Completeness as Phage_Completeness,
            p.Lifestyle as Phage_Lifestyle,
            p.Cluster as Phage_Cluster,
            p.Subcluster as Phage_Subcluster,
            h.Species_Name,
            h.Assembly_Level as Host_Assembly_Level,
            h.Genome_Length as Host_Length,
            h.GC_Content as Host_GC,
            h.RefSeq_Category as Host_RefSeq_Category
        FROM phage_host_associations pha
        JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        """

        where_conditions, limit_offset = parse_where_clause(where_clause)

        if where_conditions:
            query += f" WHERE {where_conditions}"

        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"

        logging.info(f"🔍 Querying phage-host pairs...")
        result = self.conn.execute(query).fetchdf()

        logging.info(f"📊 Found {len(result):,} phage-host pairs")

        phage_ids = result['Phage_ID'].tolist()
        host_ids = result['Host_ID'].tolist()

        logging.info(
            f"📥 Fetching sequences for {len(phage_ids):,} phages and "
            f"{len(set(host_ids)):,} unique hosts"
        )

        phage_seqs = {}
        host_seqs = {}

        phage_source_db = dict(zip(result['Phage_ID'], result['Phage_Source']))
        phage_source_type = dict(zip(result['Phage_ID'], result['Phage_Source_Type']))

        for phage_id in phage_ids:
            seq = self._get_phage_sequence(
                phage_id,
                source_db=phage_source_db.get(phage_id),
                source_type=phage_source_type.get(phage_id),
            )
            phage_seqs[phage_id] = seq

        for host_id in set(host_ids):
            try:
                seq = self.get_host_sequence(host_id, contig_mode=host_contig_mode)
                host_seqs[host_id] = seq
            except KeyError:
                host_seqs[host_id] = None

        result['Phage_Sequence'] = result['Phage_ID'].map(phage_seqs)
        result['Host_Sequence'] = result['Host_ID'].map(host_seqs)

        missing_phage_ids = sorted(
            result.loc[result['Phage_Sequence'].isna(), 'Phage_ID'].drop_duplicates().tolist()
        )
        missing_host_ids = sorted(
            result.loc[result['Host_Sequence'].isna(), 'Host_ID'].drop_duplicates().tolist()
        )

        before_count = len(result)
        result = result.dropna(subset=['Phage_Sequence', 'Host_Sequence'])
        after_count = len(result)

        if before_count > after_count:
            logging.warning(
                "⚠️  Removed %d pairs with missing sequences "
                "(%d phages missing, %d hosts missing)",
                before_count - after_count,
                len(missing_phage_ids),
                len(missing_host_ids),
            )
            if missing_phage_ids:
                logging.warning("   Missing phage IDs (sample): %s", ", ".join(missing_phage_ids[:5]))
            if missing_host_ids:
                logging.warning("   Missing host IDs (sample): %s", ", ".join(missing_host_ids[:5]))

        logging.info(f"✅ Retrieved {len(result):,} complete phage-host pairs with sequences")

        return result

    def query_phage_host_pairs(
        self,
        phage_filters: Optional[Dict[str, str]] = None,
        host_filters: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        host_contig_mode: str = "concat",
        phage_contig_mode: str = "first",
    ) -> pd.DataFrame:
        """Query phage-host pairs using structured filter dictionaries."""
        _ALLOWED_PHAGE_COLS: frozenset = frozenset({
            "Phage_ID", "Source_DB", "Length", "GC_content", "Taxonomy",
            "Completeness", "Host", "Lifestyle", "Cluster", "Subcluster",
            "source_type",
        })
        _ALLOWED_HOST_COLS: frozenset = frozenset({
            "Host_ID", "Species_Name", "Strain_Name", "Assembly_Accession",
            "Assembly_Name", "Assembly_Level", "Genome_Length", "GC_Content",
            "RefSeq_Category", "Download_Date", "Source",
        })
        HOST_COLUMN_ALIASES: Dict[str, str] = {
            "Organism_Name": "Species_Name",
        }

        conditions: List[str] = []

        for col, val in (phage_filters or {}).items():
            if col not in _ALLOWED_PHAGE_COLS:
                raise ValueError(
                    f"Unknown phage filter column '{col}'. "
                    f"Allowed columns: {sorted(_ALLOWED_PHAGE_COLS)}"
                )
            col_expr = f"p.{col}"
            val_str = str(val).replace("'", "''")
            if "%" in val_str:
                conditions.append(f"{col_expr} LIKE '{val_str}'")
            else:
                conditions.append(f"LOWER({col_expr}) = LOWER('{val_str}')")

        for col, val in (host_filters or {}).items():
            real_col = HOST_COLUMN_ALIASES.get(col, col)
            if real_col not in _ALLOWED_HOST_COLS:
                raise ValueError(
                    f"Unknown host filter column '{col}'. "
                    f"Allowed columns: {sorted(_ALLOWED_HOST_COLS | set(HOST_COLUMN_ALIASES))}"
                )
            col_expr = f"h.{real_col}"
            val_str = str(val).replace("'", "''")
            if "%" in val_str:
                conditions.append(f"{col_expr} LIKE '{val_str}'")
            else:
                conditions.append(f"LOWER({col_expr}) = LOWER('{val_str}')")

        where_clause = " AND ".join(conditions) if conditions else None

        return self.get_phage_host_pairs(
            where_clause=where_clause,
            limit=limit,
            host_contig_mode=host_contig_mode,
            phage_contig_mode=phage_contig_mode,
        )

    def get_phage_sequence(self, phage_id: str) -> Optional[str]:
        """Get the DNA sequence for a single phage."""
        return self._get_phage_sequence(phage_id)

    def help(self):
        """Print help information."""
        help_text = """
        SequenceRetriever Help:

        Core sequence retrieval methods:
            - get_phage_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_protein_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_host_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_host_sequence(host_id: str, contig_mode: str = "first") -> str
                  contig_mode="first"   : return only the first/largest contig (default)
                  contig_mode="concat"  : concatenate all contigs into one string

        Full-genome retrieval (multi-contig support):
            - get_host_genome(host_id, mode="concat", gap=0, order="length_desc")
                  Retrieve complete host genome even when split across scaffolds.
                  mode="concat"  : all contigs joined into one string (default)
                  mode="first"   : only the first/largest contig
                  mode="list"    : list of per-contig strings
                  mode="dict"    : {header: sequence} mapping
                  gap=N          : insert N "N" characters between contigs
                  order="length_desc" : sort by length desc (default, deterministic)
                  order="file"        : preserve FASTA file order
            - get_host_genome_stats(host_id, order="length_desc") -> dict
                  Returns {"contig_count", "lengths", "total_length"}
            - get_phage_genome(phage_id, mode="concat", gap=0, order="length_desc")
                  Same interface as get_host_genome; for phages (usually single-contig).

        Pair retrieval methods:
            - get_phage_host_pairs(where_clause=None, limit=None,
                                   host_contig_mode="concat", phage_contig_mode="first")
                   -> pd.DataFrame  with Phage_Sequence, Host_Sequence columns
                   Default host mode returns full fragmented host genomes.
            - get_phage_host_pairs_iterator(where_clause=None, batch_size=1000,
                                            host_contig_mode="first", phage_contig_mode="first")
                  -> iterator of DataFrame batches (memory-efficient)

        Metadata methods:
            - get_phage_metadata(where_clause=None, limit=None) -> pd.DataFrame
            - get_host_metadata(where_clause=None, limit=None) -> pd.DataFrame
            - get_phage_host_metadata(where_clause=None, limit=None) -> pd.DataFrame
            - get_protein_metadata(where_clause=None, limit=None) -> pd.DataFrame
            - get_phages(source_type=None, source_db=None, limit=None) -> pd.DataFrame
            - get_interactions(source_type=None, source_db=None, limit=None) -> pd.DataFrame
            - get_pair_ids_only(shuffle=False, seed=None, limit=None) -> pd.DataFrame
            - get_stats() -> Dict
            - close()

        Usage Examples:
            # Connect
            retriever = SequenceRetriever(db_path, phage_fasta_path, protein_fasta_path,
                                          host_mapping_path=host_mapping_path)

            # Standard sequence retrieval (unchanged)
            phage_df = retriever.get_phage_sequences(
                "SELECT Phage_ID FROM fact_phages WHERE Length > 50000", limit=100)

            # Get full host genome (multi-contig safe)
            full_genome = retriever.get_host_genome("GCF_000005845")
            print(len(full_genome), "bp total")

            # Inspect contig fragmentation
            stats = retriever.get_host_genome_stats("GCF_000005845")
            print(stats["contig_count"], "contigs,", stats["total_length"], "bp total")

            # Phage-host pairs with concatenated host genomes
            pairs = retriever.get_phage_host_pairs(
                "p.Lifestyle = 'Lytic'", limit=100, host_contig_mode="concat")

            # Batch iterator with full host genomes
            for batch_df in retriever.get_phage_host_pairs_iterator(
                    host_contig_mode="concat", batch_size=500):
                print(f"Batch: {len(batch_df)} pairs, "
                      f"host genome sizes: {batch_df['Host_Sequence'].str.len().describe()}")

            # Stats, close
            retriever.get_stats()
            retriever.close()
        """
        print(help_text)

    def create_streaming_dataset(
        self,
        where_clause: Optional[str] = None,
        batch_size: int = 1000,
        transform: Optional[object] = None,
        missing_hosts_csv: Optional[str] = None
    ):
        """Create a PhageHostStreamingDataset for memory-efficient iteration."""
        from .streaming_dataset import PhageHostStreamingDataset

        db_path = str(self.conn.execute("PRAGMA database_list").fetchone()[2])

        return PhageHostStreamingDataset(
            db_path=db_path,
            phage_fasta_path=self._phage_fasta_path,
            host_fasta_path=self._host_fasta_path,
            host_mapping_path=self._host_mapping_path,
            where_clause=where_clause,
            batch_size=batch_size,
            transform=transform,
            missing_hosts_csv=missing_hosts_csv
        )

    def create_indexed_dataset(
        self,
        where_clause: Optional[str] = None,
        transform: Optional[object] = None,
        missing_hosts_csv: Optional[str] = None
    ):
        """Create a PhageHostIndexedDataset for random access with caching."""
        from .streaming_dataset import PhageHostIndexedDataset

        db_path = str(self.conn.execute("PRAGMA database_list").fetchone()[2])

        return PhageHostIndexedDataset(
            db_path=db_path,
            phage_fasta_path=self._phage_fasta_path,
            host_fasta_path=self._host_fasta_path,
            host_mapping_path=self._host_mapping_path,
            where_clause=where_clause,
            transform=transform,
            missing_hosts_csv=missing_hosts_csv
        )

    def get_phage_host_pairs_iterator(
        self,
        where_clause: Optional[str] = None,
        batch_size: int = 1000,
        host_contig_mode: str = "first",
        phage_contig_mode: str = "first",
    ):
        """Get an iterator that yields batches of phage-host pairs as DataFrames."""
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")

        for mode_name, mode_val in (
            ("host_contig_mode", host_contig_mode),
            ("phage_contig_mode", phage_contig_mode),
        ):
            if mode_val not in ("first", "concat"):
                raise ValueError(f"{mode_name} must be 'first' or 'concat', got '{mode_val}'.")

        _ = self.phage_fasta
        if not self._use_host_mapping:
            _ = self.host_fasta

        query = """
        SELECT DISTINCT
            pha.Phage_ID,
            pha.Host_ID,
            p.Source_DB as Phage_Source,
            COALESCE(NULLIF(NULLIF(LOWER(TRIM(p.source_type)), 'nan'), ''), 'public') as Phage_Source_Type,
            p.Length as Phage_Length,
            p.GC_content as Phage_GC,
            p.Taxonomy as Phage_Taxonomy,
            p.Completeness as Phage_Completeness,
            p.Lifestyle as Phage_Lifestyle,
            p.Cluster as Phage_Cluster,
            p.Subcluster as Phage_Subcluster,
            h.Species_Name,
            h.Assembly_Level as Host_Assembly_Level,
            h.Genome_Length as Host_Length,
            h.GC_Content as Host_GC,
            h.RefSeq_Category as Host_RefSeq_Category
        FROM phage_host_associations pha
        JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        """

        where_conditions, limit_offset = parse_where_clause(where_clause)

        if where_conditions:
            query += f" WHERE {where_conditions}"

        if limit_offset:
            query += f" {limit_offset}"

        logging.info(f"🔍 Starting batch iteration with batch_size={batch_size}")

        cursor = self.conn.execute(query)
        batch_num = 0

        while True:
            batch_df = cursor.fetch_df_chunk(batch_size)
            if batch_df is None or len(batch_df) == 0:
                break

            batch_num += 1
            logging.info(f"📦 Processing batch {batch_num} ({len(batch_df)} pairs)")

            phage_seqs = {}
            host_seqs = {}

            phage_source_db = dict(zip(batch_df['Phage_ID'], batch_df['Phage_Source']))
            phage_source_type = dict(zip(batch_df['Phage_ID'], batch_df['Phage_Source_Type']))

            for phage_id in batch_df['Phage_ID'].unique():
                phage_seqs[phage_id] = self._get_phage_sequence(
                    phage_id,
                    source_db=phage_source_db.get(phage_id),
                    source_type=phage_source_type.get(phage_id),
                )

            for host_id in batch_df['Host_ID'].unique():
                host_seqs[host_id] = self._get_sequence_safe(
                    host_id, 'host', host_contig_mode=host_contig_mode
                )

            batch_df['Phage_Sequence'] = batch_df['Phage_ID'].map(phage_seqs)
            batch_df['Host_Sequence'] = batch_df['Host_ID'].map(host_seqs)

            missing_phage_ids = sorted(
                batch_df.loc[batch_df['Phage_Sequence'].isna(), 'Phage_ID'].drop_duplicates().tolist()
            )
            missing_host_ids = sorted(
                batch_df.loc[batch_df['Host_Sequence'].isna(), 'Host_ID'].drop_duplicates().tolist()
            )

            before_count = len(batch_df)
            batch_df = batch_df.dropna(subset=['Phage_Sequence', 'Host_Sequence'])
            after_count = len(batch_df)

            if before_count > after_count:
                logging.warning(
                    "⚠️  Removed %d pairs with missing sequences from batch "
                    "(%d phages missing, %d hosts missing)",
                    before_count - after_count,
                    len(missing_phage_ids),
                    len(missing_host_ids),
                )
                if missing_phage_ids:
                    logging.warning("   Missing phage IDs (sample): %s", ", ".join(missing_phage_ids[:5]))
                if missing_host_ids:
                    logging.warning("   Missing host IDs (sample): %s", ", ".join(missing_host_ids[:5]))

            if len(batch_df) > 0:
                yield batch_df

        logging.info(f"✅ Completed iteration over {batch_num} batches")

    def close(self):
        """Close database connection."""
        self.conn.close()
        logging.info("🔒 Database connection closed")

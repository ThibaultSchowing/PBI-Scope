"""
fasta_index.py
==============

FASTA loading, caching, and key extraction utilities for PBI-Scope.

This module is the single source of truth for:
- FASTA key extraction (phage vs protein)
- FASTA index rebuild detection
- Protein FASTA loading with Variant B key function
- Host/private phage FASTA LRU cache management
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Union

from pyfaidx import Fasta

from .fasta_ids import phage_key, protein_key

# Maximum number of host FASTA files to keep open simultaneously.
MAX_HOST_FASTA_CACHE_SIZE = 100


def _fasta_key_function(header: str) -> str:
    """Extract Phage_ID (first token) — canonical for phage/host FASTAs."""
    return phage_key(header)


def _protein_key_function(header: str) -> str:
    """Extract Protein_ID (second token) — canonical Variant B."""
    return protein_key(header)


def _should_rebuild_fai(fasta_path: Union[str, Path]) -> bool:
    """Return True when FASTA index is missing or older than the FASTA file."""
    fasta_path = Path(fasta_path)
    index_path = Path(str(fasta_path) + '.fai')
    if not index_path.exists():
        return True
    try:
        return index_path.stat().st_mtime < fasta_path.stat().st_mtime
    except OSError:
        return True


def load_protein_fasta(path: str) -> Fasta:
    """
    Load a protein FASTA file using canonical second-token key (Variant B).

    Protein headers are ``>Phage_ID Protein_ID Source_DB [rest]``, so the
    Protein_ID is the second whitespace-delimited token. This gives each
    protein a unique key while preserving phage provenance for find-back.
    Requires ``split_char='\\x00'`` + ``read_long_names=True`` so pyfaidx
    passes the full header to ``key_function`` (default splits on space and
    would only pass the first token).
    """
    try:
        return Fasta(
            path,
            read_long_names=True,
            split_char="\x00",
            key_function=_protein_key_function,
        )
    except ValueError as e:
        if 'Duplicate key' in str(e):
            logging.warning(
                f"⚠️  Duplicate protein keys, rebuilding index: {path}"
            )
            return Fasta(
                path,
                read_long_names=True,
                split_char="\x00",
                key_function=_protein_key_function,
                rebuild=True,
            )
        raise


def load_phage_fasta(path: str, rebuild: bool = False) -> Fasta:
    """Load a phage/host FASTA file using canonical first-token key."""
    return Fasta(
        path,
        read_long_names=True,
        split_char="\x00",
        key_function=_fasta_key_function,
        rebuild=rebuild,
    )


class HostFastaCache:
    """LRU cache for individual host FASTA files (mapping mode)."""

    def __init__(self, max_size: int = MAX_HOST_FASTA_CACHE_SIZE):
        self._cache: OrderedDict[str, Fasta] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, host_id: str, fasta_path: str, path_resolver=None) -> Fasta:
        """Get or load a host FASTA file with LRU eviction."""
        with self._lock:
            if host_id in self._cache:
                self._cache.move_to_end(host_id)
                return self._cache[host_id]

            if path_resolver is not None:
                fasta_path = path_resolver(host_id, fasta_path)

            rebuild = _should_rebuild_fai(fasta_path)
            if rebuild:
                logging.info(f"Creating index for {fasta_path}")

            fasta_obj = load_phage_fasta(fasta_path, rebuild=rebuild)
            self._cache[host_id] = fasta_obj

            # Evict oldest if over capacity
            while len(self._cache) > self._max_size:
                oldest_id, oldest_fasta = self._cache.popitem(last=False)
                if hasattr(oldest_fasta, 'close'):
                    try:
                        oldest_fasta.close()
                    except Exception as e:
                        logging.debug(f"Error closing evicted host FASTA for {oldest_id}: {e}")

            return fasta_obj

    def close_all(self) -> None:
        """Close all cached FASTA files."""
        with self._lock:
            for fasta_obj in self._cache.values():
                if hasattr(fasta_obj, 'close'):
                    try:
                        fasta_obj.close()
                    except Exception:
                        pass
            self._cache.clear()


class PrivatePhageFastaCache:
    """LRU cache for private phage FASTA files by source_db."""

    def __init__(self, max_size: int = MAX_HOST_FASTA_CACHE_SIZE):
        self._cache: OrderedDict[str, Fasta] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size

    def get(self, source_db: str, fasta_path: str, path_resolver=None) -> Fasta:
        """Get or load a private phage FASTA file with LRU eviction."""
        with self._lock:
            if source_db in self._cache:
                self._cache.move_to_end(source_db)
                return self._cache[source_db]

            if path_resolver is not None:
                fasta_path = path_resolver(source_db, fasta_path)

            rebuild = _should_rebuild_fai(fasta_path)
            if rebuild:
                logging.info(f"Creating index for private phage FASTA: {fasta_path}")

            fasta_obj = load_phage_fasta(fasta_path, rebuild=rebuild)
            self._cache[source_db] = fasta_obj

            while len(self._cache) > self._max_size:
                oldest_id, oldest_fasta = self._cache.popitem(last=False)
                if hasattr(oldest_fasta, 'close'):
                    try:
                        oldest_fasta.close()
                    except Exception:
                        pass

            return fasta_obj

    def close_all(self) -> None:
        """Close all cached FASTA files."""
        with self._lock:
            for fasta_obj in self._cache.values():
                if hasattr(fasta_obj, 'close'):
                    try:
                        fasta_obj.close()
                    except Exception:
                        pass
            self._cache.clear()

#!/usr/bin/env python3
"""
GFF3 retrieval module for PBI.

Provides fast random access to GFF3 annotations by phage_id using a
pre-built JSON index.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


class GFF3Retriever:
    """
    Retrieve GFF3 content for phages by phage_id.

    Uses a pre-built JSON index for O(1) lookup. The index maps
    phage_id -> {source_db, file_path, byte_offset, byte_length}.

    Example usage::

        retriever = GFF3Retriever("/data/processed/gff3", "/data/processed/gff3/gff3_index.json")

        # Get full GFF3 content as string
        gff3_content = retriever.get_gff3("Mycobacterium_phage_NuevoMundo")

        # Get GFF3 content as iterator (memory-efficient)
        for line in retriever.get_gff3_lines("Mycobacterium_phage_NuevoMundo"):
            print(line, end="")

        # List all phages from a specific source
        phages = retriever.list_phages(source_db="PhagesDB")
    """

    def __init__(self, gff3_dir: str, index_path: str):
        """
        Initialize GFF3Retriever.

        Args:
            gff3_dir: Directory containing per-database GFF3 files
            index_path: Path to gff3_index.json
        """
        self.gff3_dir = Path(gff3_dir)
        self.index_path = Path(index_path)
        self._index: Optional[Dict] = None

    @property
    def index(self) -> Dict:
        """Lazy-load the index on first access."""
        if self._index is None:
            if not self.index_path.exists():
                raise FileNotFoundError(f"GFF3 index not found: {self.index_path}")
            with open(self.index_path, "r", encoding="utf-8") as f:
                self._index = json.load(f)
            logger.info("Loaded GFF3 index with %d entries", len(self._index))
        return self._index

    def get_gff3(self, phage_id: str) -> str:
        """
        Retrieve the full GFF3 content for a given phage_id.

        Args:
            phage_id: The phage identifier (e.g., "Mycobacterium_phage_NuevoMundo")

        Returns:
            GFF3 text content as a string, or empty string if not found.
        """
        if phage_id not in self.index:
            logger.warning("Phage ID not found in GFF3 index: %s", phage_id)
            return ""

        entry = self.index[phage_id]
        gff3_path = Path(entry["file_path"])

        if not gff3_path.exists():
            logger.warning("GFF3 file not found: %s", gff3_path)
            return ""

        with open(gff3_path, "r", encoding="utf-8") as f:
            f.seek(entry["byte_offset"])
            return f.read(entry["byte_length"])

    def get_gff3_lines(self, phage_id: str) -> Iterator[str]:
        """
        Generator that yields GFF3 lines for a given phage_id.

        Memory-efficient for large files. Yields lines one at a time.

        Args:
            phage_id: The phage identifier

        Yields:
            Individual GFF3 lines (including trailing newline)
        """
        if phage_id not in self.index:
            logger.warning("Phage ID not found in GFF3 index: %s", phage_id)
            return

        entry = self.index[phage_id]
        gff3_path = Path(entry["file_path"])

        if not gff3_path.exists():
            logger.warning("GFF3 file not found: %s", gff3_path)
            return

        with open(gff3_path, "r", encoding="utf-8") as f:
            f.seek(entry["byte_offset"])
            bytes_read = 0
            target_bytes = entry["byte_length"]

            while bytes_read < target_bytes:
                line = f.readline()
                if not line:
                    break
                bytes_read += len(line.encode("utf-8"))
                yield line

    def list_phages(self, source_db: Optional[str] = None) -> List[str]:
        """
        List all phage IDs in the index.

        Args:
            source_db: Optional filter by source database

        Returns:
            List of phage IDs
        """
        if source_db:
            return [
                pid
                for pid, entry in self.index.items()
                if entry["source_db"] == source_db
            ]
        return list(self.index.keys())

    def get_source_db(self, phage_id: str) -> Optional[str]:
        """
        Get the source database for a phage_id.

        Args:
            phage_id: The phage identifier

        Returns:
            Source database name, or None if not found
        """
        entry = self.index.get(phage_id)
        return entry["source_db"] if entry else None

    def has_phage(self, phage_id: str) -> bool:
        """Check if a phage_id exists in the index."""
        return phage_id in self.index

    def stats(self) -> Dict:
        """
        Get statistics about the GFF3 index.

        Returns:
            Dict with total count and per-source counts
        """
        source_counts: Dict[str, int] = {}
        for entry in self.index.values():
            source = entry["source_db"]
            source_counts[source] = source_counts.get(source, 0) + 1

        return {
            "total_phages": len(self.index),
            "sources": source_counts,
            "index_path": str(self.index_path),
            "gff3_dir": str(self.gff3_dir),
        }

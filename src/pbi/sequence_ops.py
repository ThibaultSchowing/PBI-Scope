"""
sequence_ops.py
===============

Low-level sequence fetch operations for SequenceRetriever.

This module provides a mixin class with sequence retrieval methods.
SequenceRetriever inherits from this mixin to maintain backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd
from Bio.SeqUtils import gc_fraction

from .fasta_utils import assemble_genome, get_genome_stats


class SequenceOpsMixin:
    """Mixin providing sequence fetch methods for SequenceRetriever.

    Requires the following attributes on the host class:
    - phage_fasta, protein_fasta: Fasta properties
    - _private_phage_mapping: Optional[Dict]
    - _has_host_data: bool
    - _use_host_mapping: bool
    - conn: DuckDB connection
    """

    def _get_phage_sequence(
        self, phage_id: str, source_db: Optional[str] = None, source_type: Optional[str] = None
    ) -> Optional[str]:
        """Retrieve a single phage sequence, routing private phages to their source FASTA."""
        from .fasta_index import _fasta_key_function, _protein_key_function

        normalized_source_type = str(source_type).strip().lower() if source_type else ""
        normalized_source_type = "private" if normalized_source_type == "private" else "public"
        resolved_source_db = str(source_db).strip() if source_db else None
        if not resolved_source_db or resolved_source_db.lower() == "nan":
            resolved_source_db = None

        is_private = normalized_source_type == "private" or resolved_source_db is not None

        if is_private and self._private_phage_mapping and resolved_source_db:
            try:
                fasta_obj = self._get_private_phage_fasta(resolved_source_db)
                return str(fasta_obj[phage_id][:].seq)
            except (KeyError, Exception) as exc:
                logging.debug(
                    "Private phage %s not found in source %s: %s",
                    phage_id, resolved_source_db, exc,
                )

        try:
            return str(self.phage_fasta[phage_id][:].seq)
        except KeyError:
            if self._private_phage_mapping:
                for sdb in self._private_phage_mapping:
                    try:
                        fasta_obj = self._get_private_phage_fasta(sdb)
                        if phage_id in fasta_obj:
                            logging.debug("Found private phage %s in fallback source %s", phage_id, sdb)
                            return str(fasta_obj[phage_id][:].seq)
                    except Exception:
                        pass
            return None

    def _fetch_phage_sequences(self, phage_ids: list) -> pd.DataFrame:
        """Fetch phage sequences for given Phage IDs."""
        if not phage_ids:
            logging.warning("No Phage IDs provided")
            return pd.DataFrame(columns=['Phage_ID', 'Sequence'])

        logging.info(f"🔍 Fetching sequences for {len(phage_ids):,} phages")

        phage_source_db: Dict[str, str] = {}
        phage_source_type: Dict[str, str] = {}
        if self._private_phage_mapping and phage_ids:
            try:
                placeholders = ", ".join(["?" for _ in phage_ids])
                source_df = self.conn.execute(
                    f"SELECT Phage_ID, Source_DB, source_type FROM fact_phages "
                    f"WHERE Phage_ID IN ({placeholders})",
                    phage_ids,
                ).fetchdf()
                phage_source_db = dict(zip(source_df["Phage_ID"], source_df["Source_DB"]))
                phage_source_type = dict(zip(source_df["Phage_ID"], source_df["source_type"]))
            except Exception as exc:
                logging.debug("Could not query phage source info: %s", exc)

        sequences = []
        missing_ids = []

        for phage_id in phage_ids:
            seq = self._get_phage_sequence(
                phage_id,
                source_db=phage_source_db.get(phage_id),
                source_type=phage_source_type.get(phage_id),
            )
            if seq is not None:
                sequences.append({'Phage_ID': phage_id, 'Sequence': seq})
            else:
                missing_ids.append(phage_id)
                logging.warning(f"⚠️  Phage ID '{phage_id}' not found in FASTA")

        if missing_ids:
            logging.warning(f"⚠️  {len(missing_ids):,} phage IDs not found in FASTA file")

        df = pd.DataFrame(sequences)
        logging.info(f"✅ Retrieved {len(df):,} sequences")
        return df

    def _fetch_protein_sequences(self, protein_ids: list) -> pd.DataFrame:
        """Fetch protein sequences for given Protein IDs."""
        if not protein_ids:
            logging.warning("No Protein IDs provided")
            return pd.DataFrame(columns=['Protein_ID', 'Sequence'])

        logging.info(f"🔍 Fetching sequences for {len(protein_ids):,} proteins")

        sequences = []
        missing_ids = []

        for protein_id in protein_ids:
            try:
                seq = self.protein_fasta[protein_id][:].seq
                sequences.append({
                    'Protein_ID': protein_id,
                    'Sequence': str(seq)
                })
            except KeyError:
                seq = self._fuzzy_protein_lookup(protein_id)
                if seq is not None:
                    sequences.append({'Protein_ID': protein_id, 'Sequence': seq})
                else:
                    missing_ids.append(protein_id)
                    logging.warning(f"⚠️  Protein ID '{protein_id}' not found in FASTA")

        if missing_ids:
            logging.warning(f"⚠️  {len(missing_ids):,} protein IDs not found in FASTA file")

        df = pd.DataFrame(sequences)
        logging.info(f"✅ Retrieved {len(df):,} sequences")
        return df

    def _fetch_host_sequences(self, host_ids: list) -> pd.DataFrame:
        """Fetch host sequences for given Host IDs."""
        if not host_ids:
            logging.warning("No Host IDs provided")
            return pd.DataFrame(columns=['Host_ID', 'Species_Name', 'Sequence', 'Length', 'GC_Content'])

        logging.info(f"🔍 Fetching sequences for {len(host_ids):,} hosts")

        sequences = []
        missing_ids = []

        for host_id in host_ids:
            try:
                seq = self.get_host_sequence(host_id)
                sequences.append({
                    'Host_ID': host_id,
                    'Species_Name': '',
                    'Sequence': seq,
                    'Length': len(seq),
                    'GC_Content': round(gc_fraction(seq) * 100, 2) if seq else 0.0
                })
            except KeyError:
                missing_ids.append(host_id)
                logging.warning(f"⚠️  Host ID '{host_id}' not found in FASTA")

        if missing_ids:
            logging.warning(f"⚠️  {len(missing_ids):,} host IDs not found in FASTA file")

        df = pd.DataFrame(sequences)
        logging.info(f"✅ Retrieved {len(df):,} sequences")
        return df

    def _build_protein_token_index(self) -> dict:
        """Build (once) a mapping of every whitespace-delimited token in every protein FASTA key to that key."""
        if not hasattr(self, '_protein_token_idx'):
            idx: dict = {}
            for key in self.protein_fasta.keys():
                for token in key.split():
                    idx.setdefault(token, key)
            self._protein_token_idx = idx
        return self._protein_token_idx

    def _fuzzy_protein_lookup(self, protein_id: str) -> Optional[str]:
        """Try to find a protein sequence whose FASTA header matches protein_id approximately."""
        fasta = self.protein_fasta

        for key in fasta.keys():
            if key.startswith(protein_id):
                return str(fasta[key][:].seq)

        pid_parts = protein_id.split()
        search_token = pid_parts[1] if len(pid_parts) > 1 else pid_parts[0]
        idx = self._build_protein_token_index()
        matched_key = idx.get(search_token)
        if matched_key is not None:
            return str(fasta[matched_key][:].seq)

        return None

    def _get_sequence_safe(
        self,
        seq_id: str,
        seq_type: str,
        host_contig_mode: str = "first",
    ) -> str:
        """Helper method for safe sequence retrieval with error handling."""
        try:
            if seq_type == 'phage':
                return str(self.phage_fasta[seq_id][:].seq)
            elif seq_type == 'host':
                return self.get_host_sequence(seq_id, contig_mode=host_contig_mode)
            else:
                raise ValueError(f"Invalid seq_type: {seq_type}")
        except KeyError:
            logging.warning(f"⚠️  {seq_type.capitalize()} sequence not found for ID: {seq_id}")
            return ""
        except Exception as e:
            logging.warning(f"⚠️  Error retrieving {seq_type} sequence for {seq_id}: {e}")
            return ""

"""
metadata_queries.py
===================

DuckDB metadata query methods for SequenceRetriever.

This module provides a mixin class with all metadata query methods.
SequenceRetriever inherits from this mixin to maintain backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import pandas as pd

from .query_utils import parse_where_clause


class MetadataQueriesMixin:
    """Mixin providing metadata query methods for SequenceRetriever.

    Requires the following attributes on the host class:
    - conn: DuckDB connection
    - _has_host_data: bool
    - _use_host_mapping: bool
    - _host_count: Optional[int]
    - phage_fasta, protein_fasta, host_fasta: Fasta properties
    - _phage_count, _protein_count: Optional[int]
    """

    def get_stats(self) -> Dict:
        """
        Get database and FASTA statistics

        Note: Will wait for FASTA loading to complete
        """
        if hasattr(self, '_load_thread') and not self.is_ready():
            self.wait_until_ready(timeout=300)

        _ = self.phage_fasta
        _ = self.protein_fasta

        stats = {
            'database': {
                'phages': self.conn.execute("SELECT COUNT(*) FROM fact_phages").fetchone()[0],
                'proteins': self.conn.execute("SELECT COUNT(*) FROM dim_proteins").fetchone()[0],
            },
            'fasta': {
                'phages': self._phage_count if self._phage_count else len(self.phage_fasta.keys()),
                'proteins': self._protein_count if self._protein_count else len(self.protein_fasta.keys()),
            }
        }

        if self._has_host_data:
            try:
                stats['database']['hosts'] = self.conn.execute("SELECT COUNT(*) FROM dim_hosts").fetchone()[0]
                stats['database']['phage_host_associations'] = self.conn.execute(
                    "SELECT COUNT(*) FROM phage_host_associations"
                ).fetchone()[0]

                if self._use_host_mapping:
                    stats['fasta']['hosts'] = self._host_count
                else:
                    _ = self.host_fasta
                    stats['fasta']['hosts'] = self._host_count if self._host_count else len(self.host_fasta.keys())
            except Exception as e:
                logging.warning(f"Host data configured but tables not found. Run host genome workflow first. Error: {e}")
                self._has_host_data = False

        try:
            source_breakdown = self.conn.execute(
                """
                SELECT source_type, Source_DB, COUNT(*) AS count
                FROM fact_phages
                GROUP BY source_type, Source_DB
                ORDER BY source_type, count DESC
                """
            ).fetchdf()
            stats['database']['source_breakdown'] = source_breakdown.to_dict(orient='records')
        except Exception as e:
            logging.debug(f"Could not compute source breakdown stats: {e}")

        logging.info(f"📊 Database Stats:")
        logging.info(f"   Phages: {stats['database']['phages']:,}")
        logging.info(f"   Proteins: {stats['database']['proteins']:,}")
        if 'hosts' in stats['database']:
            logging.info(f"   Hosts: {stats['database']['hosts']:,}")
            if 'phage_host_associations' in stats['database']:
                logging.info(f"   Phage-Host Associations: {stats['database']['phage_host_associations']:,}")

        logging.info(f"📊 FASTA Stats:")
        logging.info(f"   Phages: {stats['fasta']['phages']:,}")
        logging.info(f"   Proteins: {stats['fasta']['proteins']:,}")
        if 'hosts' in stats['fasta']:
            logging.info(f"   Hosts: {stats['fasta']['hosts']:,}")

        return stats

    def get_phages(
        self,
        source_type: Optional[str] = None,
        source_db: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Return phage metadata with optional provenance filters."""
        filters = []
        params = []
        if source_type:
            filters.append("source_type = ?")
            params.append(source_type)
        if source_db:
            filters.append("Source_DB = ?")
            params.append(source_db)

        query = "SELECT * FROM fact_phages"
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY Phage_ID"
        if limit:
            query += f" LIMIT {int(limit)}"

        return self.conn.execute(query, params).fetchdf()

    def get_interactions(
        self,
        source_type: Optional[str] = None,
        source_db: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Return phage-host interactions with optional provenance filters."""
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")

        filters = []
        params = []
        if source_type:
            filters.append("p.source_type = ?")
            params.append(source_type)
        if source_db:
            filters.append("p.Source_DB = ?")
            params.append(source_db)

        query = """
        SELECT DISTINCT
            pha.Phage_ID,
            pha.Host_ID,
            p.Source_DB,
            CASE
                WHEN LOWER(TRIM(COALESCE(p.source_type, ''))) = 'private' THEN 'private'
                ELSE 'public'
            END as source_type
        FROM phage_host_associations pha
        JOIN fact_phages p ON p.Phage_ID = pha.Phage_ID
        """
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY pha.Phage_ID, pha.Host_ID"
        if limit:
            query += f" LIMIT {int(limit)}"

        return self.conn.execute(query, params).fetchdf()

    def get_pair_ids_only(
        self,
        shuffle: bool = False,
        seed: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Return distinct (Phage_ID, Host_ID) pairs without loading sequences."""
        query = "SELECT DISTINCT Phage_ID, Host_ID FROM phage_host_associations"
        if shuffle:
            query += " ORDER BY MD5(Phage_ID || Host_ID)"
        if limit:
            query += f" LIMIT {int(limit)}"
        return self.conn.execute(query).fetchdf()

    def get_phage_metadata(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """Get phage metadata from the database."""
        query = """
        SELECT
            Phage_ID,
            Source_DB,
            Length,
            GC_content,
            Taxonomy,
            Completeness,
            Host,
            Lifestyle,
            Cluster,
            Subcluster
        FROM fact_phages
        """

        where_conditions, limit_offset = parse_where_clause(where_clause)

        if where_conditions:
            query += f" WHERE {where_conditions}"

        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"

        logging.info(f"🔍 Querying phage metadata...")
        result = self.conn.execute(query).fetchdf()
        logging.info(f"✅ Retrieved metadata for {len(result):,} phages")
        return result

    def get_host_metadata(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """Get host metadata from the database."""
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")

        query = """
        SELECT
            Host_ID,
            Species_Name,
            Strain_Name,
            Assembly_Accession,
            Assembly_Name,
            Assembly_Level,
            Genome_Length,
            GC_Content,
            RefSeq_Category,
            Download_Date,
            Source
        FROM dim_hosts
        """

        where_conditions, limit_offset = parse_where_clause(where_clause)

        if where_conditions:
            query += f" WHERE {where_conditions}"

        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"

        logging.info(f"🔍 Querying host metadata...")
        result = self.conn.execute(query).fetchdf()
        logging.info(f"✅ Retrieved metadata for {len(result):,} hosts")
        return result

    def get_phage_host_metadata(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """Get combined phage-host metadata for interaction pairs."""
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")

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
            h.Species_Name as Host_Species,
            h.Strain_Name as Host_Strain,
            h.Assembly_Accession as Host_Assembly,
            h.Assembly_Level as Host_Assembly_Level,
            h.Genome_Length as Host_Length,
            h.GC_Content as Host_GC,
            h.RefSeq_Category as Host_RefSeq_Category,
            h.Source as Host_Source
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

        logging.info(f"🔍 Querying phage-host metadata...")
        result = self.conn.execute(query).fetchdf()
        logging.info(f"✅ Retrieved metadata for {len(result):,} phage-host pairs")
        return result

    def get_protein_metadata(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """Get protein metadata from dim_proteins."""
        query = """
        SELECT
            Protein_ID,
            Phage_ID,
            Source_DB,
            Protein_source,
            Function_prediction_source,
            Start,
            Stop,
            Strand,
            Product,
            Protein_classification
        FROM dim_proteins
        """

        where_conditions, limit_offset = parse_where_clause(where_clause)

        if where_conditions:
            query += f" WHERE {where_conditions}"

        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"

        logging.info(f"🔍 Querying protein metadata...")
        result = self.conn.execute(query).fetchdf()
        logging.info(f"✅ Retrieved metadata for {len(result):,} proteins")
        return result

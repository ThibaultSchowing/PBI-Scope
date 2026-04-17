from __future__ import annotations

import json
from pathlib import Path

import duckdb
from pyfaidx import Fasta

from pbi.sequence_retrieval import SequenceRetriever


def _write_fasta(path: Path, header: str, sequence: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">{header}\n{sequence}\n", encoding="utf-8")
    Fasta(str(path), rebuild=True)


def test_private_sequence_retrieval_consistency(
    tmp_path,
    monkeypatch,
):
    private_root = tmp_path / "private_data"
    monkeypatch.setenv("PBI_PRIVATE_DATA_DIR", str(private_root))

    # Public sequence inputs (mandatory for SequenceRetriever construction).
    public_phage_fasta = tmp_path / "all_phages.fasta"
    protein_fasta = tmp_path / "all_proteins.fasta"
    _write_fasta(public_phage_fasta, "PUB_PHAGE", "GGGG")
    _write_fasta(protein_fasta, "PROT_1", "MKKL")

    # Private phage source and mapping.
    private_source_dir = private_root / "test_private"
    private_phage_fasta = private_source_dir / "phage.fasta"
    _write_fasta(private_phage_fasta, "PRIV_PHAGE", "ATAT")
    private_phage_mapping = tmp_path / "private_phage_mapping.json"
    private_phage_mapping.write_text(
        json.dumps({"test_private": str(private_phage_fasta)}),
        encoding="utf-8",
    )

    # Host paths: stale mapped path points to /private-data/... and should resolve
    # to test_private/hosts, not to hidden .pbi cache folder.
    private_host_good = private_source_dir / "hosts" / "HOST_PRIVATE.fna"
    hidden_host_wrong = private_root / ".pbi" / "hosts" / "HOST_PRIVATE.fna"
    public_host = tmp_path / "public_hosts" / "HOST_PUBLIC.fna"
    _write_fasta(private_host_good, "HOST_PRIVATE", "AAAA")
    _write_fasta(hidden_host_wrong, "HOST_PRIVATE_OLD", "TTTT")
    _write_fasta(public_host, "HOST_PUBLIC", "CCCC")

    host_mapping = tmp_path / "host_fasta_mapping.json"
    host_mapping.write_text(
        json.dumps(
            {
                "HOST_PRIVATE": "/private-data/test_private/hosts/HOST_PRIVATE.fna",
                "HOST_PUBLIC": str(public_host),
            }
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fact_phages (
            Phage_ID VARCHAR,
            Source_DB VARCHAR,
            Length INTEGER,
            GC_content DOUBLE,
            Taxonomy VARCHAR,
            Completeness VARCHAR,
            Host VARCHAR,
            Lifestyle VARCHAR,
            Cluster VARCHAR,
            Subcluster VARCHAR,
            source_type VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE phage_host_associations (
            Phage_ID VARCHAR,
            Host_ID VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_hosts (
            Host_ID VARCHAR,
            Species_Name VARCHAR,
            Assembly_Level VARCHAR,
            Genome_Length BIGINT,
            GC_Content DOUBLE,
            RefSeq_Category VARCHAR
        )
        """
    )

    conn.execute(
        """
        INSERT INTO fact_phages VALUES
            ('PRIV_PHAGE', 'test_private', 1000, 0.5, NULL, NULL, NULL, NULL, NULL, NULL, 'private'),
            ('PUB_PHAGE', 'PhagesDB', 1200, 0.4, NULL, NULL, NULL, NULL, NULL, NULL, 'phagescope')
        """
    )
    conn.execute(
        """
        INSERT INTO phage_host_associations VALUES
            ('PRIV_PHAGE', 'HOST_PRIVATE'),
            ('PUB_PHAGE', 'HOST_PUBLIC')
        """
    )
    conn.execute(
        """
        INSERT INTO dim_hosts VALUES
            ('HOST_PRIVATE', 'Private host', NULL, NULL, NULL, NULL),
            ('HOST_PUBLIC', 'Public host', NULL, NULL, NULL, NULL)
        """
    )
    conn.close()

    retriever = SequenceRetriever(
        str(db_path),
        str(public_phage_fasta),
        str(protein_fasta),
        host_mapping_path=str(host_mapping),
        private_phage_mapping_path=str(private_phage_mapping),
        preload=False,
    )

    pairs = retriever.get_phage_host_pairs()
    retriever.close()

    assert len(pairs) == 2

    private_row = pairs.loc[pairs["Phage_ID"] == "PRIV_PHAGE"].iloc[0]
    public_row = pairs.loc[pairs["Phage_ID"] == "PUB_PHAGE"].iloc[0]

    # Private host must resolve to test_private/hosts/HOST_PRIVATE.fna (AAAA),
    # not hidden .pbi/hosts/HOST_PRIVATE.fna (TTTT).
    assert private_row["Host_Sequence"] == "AAAA"
    assert private_row["Phage_Sequence"] == "ATAT"
    assert private_row["Phage_Source_Type"] == "private"

    # Non-private values like "phagescope" are normalized to "public".
    assert public_row["Host_Sequence"] == "CCCC"
    assert public_row["Phage_Sequence"] == "GGGG"
    assert public_row["Phage_Source_Type"] == "public"


def test_private_phage_mapping_stale_path_resolution(tmp_path, monkeypatch):
    private_root = tmp_path / "private_data"
    monkeypatch.setenv("PBI_PRIVATE_DATA_DIR", str(private_root))

    # Public mandatory FASTAs for retriever construction.
    public_phage_fasta = tmp_path / "all_phages.fasta"
    protein_fasta = tmp_path / "all_proteins.fasta"
    _write_fasta(public_phage_fasta, "PUB_PHAGE", "GGGG")
    _write_fasta(protein_fasta, "PROT_1", "MKKL")

    # Private source with phage sequence available at current mount path.
    private_source_dir = private_root / "test_private"
    private_phage_fasta = private_source_dir / "phage.fasta"
    _write_fasta(private_phage_fasta, "PRIV_PHAGE", "ATAT")

    # Mapping intentionally uses stale /private-data mount path.
    private_phage_mapping = tmp_path / "private_phage_mapping.json"
    private_phage_mapping.write_text(
        json.dumps({"test_private": "/private-data/test_private/phage.fasta"}),
        encoding="utf-8",
    )

    # Host mapping points to existing file to isolate phage-path behavior.
    private_host = private_source_dir / "hosts" / "HOST_PRIVATE.fna"
    _write_fasta(private_host, "HOST_PRIVATE", "AAAA")
    host_mapping = tmp_path / "host_fasta_mapping.json"
    host_mapping.write_text(
        json.dumps({"HOST_PRIVATE": str(private_host)}),
        encoding="utf-8",
    )

    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE fact_phages (
            Phage_ID VARCHAR,
            Source_DB VARCHAR,
            Length INTEGER,
            GC_content DOUBLE,
            Taxonomy VARCHAR,
            Completeness VARCHAR,
            Host VARCHAR,
            Lifestyle VARCHAR,
            Cluster VARCHAR,
            Subcluster VARCHAR,
            source_type VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE phage_host_associations (
            Phage_ID VARCHAR,
            Host_ID VARCHAR
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_hosts (
            Host_ID VARCHAR,
            Species_Name VARCHAR,
            Assembly_Level VARCHAR,
            Genome_Length BIGINT,
            GC_Content DOUBLE,
            RefSeq_Category VARCHAR
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_phages VALUES
            ('PRIV_PHAGE', 'test_private', 1000, 0.5, NULL, NULL, NULL, NULL, NULL, NULL, 'private')
        """
    )
    conn.execute(
        """
        INSERT INTO phage_host_associations VALUES
            ('PRIV_PHAGE', 'HOST_PRIVATE')
        """
    )
    conn.execute(
        """
        INSERT INTO dim_hosts VALUES
            ('HOST_PRIVATE', 'Private host', NULL, NULL, NULL, NULL)
        """
    )
    conn.close()

    retriever = SequenceRetriever(
        str(db_path),
        str(public_phage_fasta),
        str(protein_fasta),
        host_mapping_path=str(host_mapping),
        private_phage_mapping_path=str(private_phage_mapping),
        preload=False,
    )

    pairs = retriever.get_phage_host_pairs()
    retriever.close()

    assert len(pairs) == 1
    row = pairs.iloc[0]
    assert row["Phage_ID"] == "PRIV_PHAGE"
    assert row["Phage_Sequence"] == "ATAT"
    assert row["Host_Sequence"] == "AAAA"

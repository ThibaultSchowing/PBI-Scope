#!/usr/bin/env python3

from pathlib import Path

import duckdb
import json
import pandas as pd

from pbi.private_data import (
    ingest_private_sources_into_db,
    prepare_private_sequence_artifacts,
    validate_private_source,
)


def _write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_private_source(
    root: Path,
    name: str,
    metadata_rows: list[dict],
    phage_ids: list[str],
    host_ids: list[str],
):
    source_dir = root / name
    source_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(metadata_rows).to_csv(source_dir / "metadata.csv", index=False)
    _write_text(source_dir / "phage.fasta", "".join([f">{pid} desc\nATGC\n" for pid in phage_ids]))
    _write_text(source_dir / "host.fasta", "".join([f">{hid} desc\nATGC\n" for hid in host_ids]))
    return source_dir


def _prepare_minimal_db(conn: duckdb.DuckDBPyConnection):
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


def test_validate_private_source_success(tmp_path):
    source = _create_private_source(
        tmp_path,
        "Project_A",
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Host One",
                "Source_DB": "Project_A",
                "interaction": "Virulent",
                "Lab_Condition": "anaerobic",
            }
        ],
        ["P1"],
        ["H1"],
    )
    result = validate_private_source(source)
    assert result.is_valid
    assert result.stats["rows"] == 1


def test_validate_private_source_missing_required_file(tmp_path):
    source = tmp_path / "Project_A"
    source.mkdir()
    # No phage.fasta — this is still a required file
    _write_text(source / "metadata.csv", "Phage_ID,Host_ID,Host_name,Source_DB,interaction\n")
    result = validate_private_source(source)
    assert not result.is_valid
    assert any("Missing required files" in e for e in result.errors)


def test_validate_private_source_missing_required_column(tmp_path):
    source = _create_private_source(
        tmp_path,
        "Project_A",
        [{"Phage_ID": "P1", "Host_ID": "H1", "Source_DB": "Project_A", "interaction": "virulent"}],
        ["P1"],
        ["H1"],
    )
    result = validate_private_source(source)
    assert not result.is_valid
    assert any("missing required columns" in e for e in result.errors)


def test_validate_private_source_invalid_interaction(tmp_path):
    source = _create_private_source(
        tmp_path,
        "Project_A",
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Host One",
                "Source_DB": "Project_A",
                "interaction": "latent",
            }
        ],
        ["P1"],
        ["H1"],
    )
    result = validate_private_source(source)
    assert not result.is_valid
    assert any("Invalid interaction values" in e for e in result.errors)


def test_validate_private_source_id_mismatch(tmp_path):
    source = _create_private_source(
        tmp_path,
        "Project_A",
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Host One",
                "Source_DB": "Project_A",
                "interaction": "virulent",
            }
        ],
        ["P2"],
        ["H2"],
    )
    result = validate_private_source(source)
    assert not result.is_valid
    assert any("Phage_ID not found" in e for e in result.errors)
    assert any("Host_ID not found" in e for e in result.errors)


def test_validate_private_source_missing_host_fasta_is_invalid(tmp_path):
    """host.fasta is mandatory for private sources."""
    source = tmp_path / "Project_B"
    source.mkdir()
    pd.DataFrame(
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Bacteroides dorei",
                "Source_DB": "Project_B",
                "interaction": "virulent",
            }
        ]
    ).to_csv(source / "metadata.csv", index=False)
    _write_text(source / "phage.fasta", ">P1 desc\nATGC\n")
    # Intentionally no host.fasta

    result = validate_private_source(source)
    assert not result.is_valid
    assert any("Missing required files" in e for e in result.errors)
    assert any("host.fasta" in e for e in result.errors)


def test_validate_private_source_with_host_fasta_still_validates_ids(tmp_path):
    """When host.fasta IS provided it must still contain all declared Host_IDs."""
    source = _create_private_source(
        tmp_path,
        "Project_A",
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Host One",
                "Source_DB": "Project_A",
                "interaction": "virulent",
            }
        ],
        phage_ids=["P1"],
        host_ids=["H_WRONG"],  # host.fasta has wrong ID
    )
    result = validate_private_source(source)
    assert not result.is_valid
    assert any("Host_ID not found in host.fasta" in e for e in result.errors)


def test_prepare_private_sequence_artifacts_requires_host_fasta(tmp_path):
    """Sources without host.fasta should be skipped via manifest validity."""
    source = tmp_path / "Project_NoHost"
    source.mkdir()
    pd.DataFrame(
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Bacteroides dorei",
                "Source_DB": "Project_NoHost",
                "interaction": "virulent",
            }
        ]
    ).to_csv(source / "metadata.csv", index=False)
    _write_text(source / "phage.fasta", ">P1 desc\nATGC\n")
    # No host.fasta

    manifest = {"sources": [{"source_db": "Project_NoHost", "source_dir": str(source), "is_valid": False}]}

    private_phage_fasta = tmp_path / "private" / "private_phages.fasta"
    private_host_dir = tmp_path / "private" / "hosts"
    private_host_mapping = tmp_path / "private" / "private_host_mapping.json"

    stats = prepare_private_sequence_artifacts(
        manifest=manifest,
        private_phage_fasta_path=private_phage_fasta,
        private_host_dir=private_host_dir,
        private_host_mapping_path=private_host_mapping,
    )

    assert stats["sources_processed"] == 0
    assert stats["phages_written"] == 0
    assert stats["hosts_written"] == 0

    # Phage FASTA should be present but empty; host mapping should be empty
    assert private_phage_fasta.read_text(encoding="utf-8") == ""
    with private_host_mapping.open("r", encoding="utf-8") as handle:
        mapping = json.load(handle)
    assert mapping == {}
    valid_source = _create_private_source(
        tmp_path,
        "Valid_Source",
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Host One",
                "Source_DB": "Valid_Source",
                "interaction": "temperate",
                "Batch": "B1",
            }
        ],
        ["P1"],
        ["H1"],
    )
    invalid_source = _create_private_source(
        tmp_path,
        "Invalid_Source",
        [
            {
                "Phage_ID": "PX",
                "Host_ID": "HX",
                "Host_name": "Host X",
                "Source_DB": "Wrong_Source",
                "interaction": "virulent",
            }
        ],
        ["PX"],
        ["HX"],
    )

    conn = duckdb.connect(":memory:")
    _prepare_minimal_db(conn)

    summary = ingest_private_sources_into_db(conn, [str(valid_source), str(invalid_source)])
    assert len(summary["ingested"]) == 1
    assert len(summary["skipped"]) == 1

    phage_count = conn.execute("SELECT COUNT(*) FROM fact_phages WHERE source_type = 'private'").fetchone()[0]
    assert phage_count == 1

    attrs_count = conn.execute("SELECT COUNT(*) FROM private_entity_attributes").fetchone()[0]
    assert attrs_count == 1


def test_prepare_private_sequence_artifacts_generates_private_fasta_and_mapping(tmp_path):
    source = _create_private_source(
        tmp_path,
        "Project_A",
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Host One",
                "Source_DB": "Project_A",
                "interaction": "virulent",
            }
        ],
        ["P1"],
        ["H1"],
    )
    manifest = {
        "sources": [
            {
                "source_db": "Project_A",
                "source_dir": str(source),
                "is_valid": True,
            }
        ]
    }

    private_phage_fasta = tmp_path / "private" / "private_phages.fasta"
    private_host_dir = tmp_path / "private" / "hosts"
    private_host_mapping = tmp_path / "private" / "private_host_mapping.json"

    stats = prepare_private_sequence_artifacts(
        manifest=manifest,
        private_phage_fasta_path=private_phage_fasta,
        private_host_dir=private_host_dir,
        private_host_mapping_path=private_host_mapping,
    )

    assert stats["sources_processed"] == 1
    assert stats["phages_written"] == 1
    assert stats["hosts_written"] == 1

    phage_content = private_phage_fasta.read_text(encoding="utf-8")
    assert ">P1 desc" in phage_content

    with private_host_mapping.open("r", encoding="utf-8") as handle:
        mapping = json.load(handle)
    assert "H1" in mapping
    mapped_path = Path(mapping["H1"])
    assert mapped_path.exists()
    assert ">H1 desc" in mapped_path.read_text(encoding="utf-8")


def test_prepare_private_sequence_artifacts_skips_invalid_sources(tmp_path):
    valid_source = _create_private_source(
        tmp_path,
        "Valid_Source",
        [
            {
                "Phage_ID": "P1",
                "Host_ID": "H1",
                "Host_name": "Host One",
                "Source_DB": "Valid_Source",
                "interaction": "temperate",
            }
        ],
        ["P1"],
        ["H1"],
    )
    invalid_source = _create_private_source(
        tmp_path,
        "Invalid_Source",
        [
            {
                "Phage_ID": "PX",
                "Host_ID": "HX",
                "Host_name": "Host X",
                "Source_DB": "Invalid_Source",
                "interaction": "virulent",
            }
        ],
        ["PX"],
        ["HX"],
    )

    manifest = {
        "sources": [
            {"source_db": "Valid_Source", "source_dir": str(valid_source), "is_valid": True},
            {"source_db": "Invalid_Source", "source_dir": str(invalid_source), "is_valid": False},
        ]
    }

    private_phage_fasta = tmp_path / "private" / "private_phages.fasta"
    private_host_dir = tmp_path / "private" / "hosts"
    private_host_mapping = tmp_path / "private" / "private_host_mapping.json"

    stats = prepare_private_sequence_artifacts(
        manifest=manifest,
        private_phage_fasta_path=private_phage_fasta,
        private_host_dir=private_host_dir,
        private_host_mapping_path=private_host_mapping,
    )

    assert stats["sources_processed"] == 1
    assert ">P1 desc" in private_phage_fasta.read_text(encoding="utf-8")
    assert "PX" not in private_phage_fasta.read_text(encoding="utf-8")


def test_ingest_private_sources_resyncs_deleted_sources_and_prevents_duplicates(tmp_path):
    source_a = _create_private_source(
        tmp_path,
        "Source_A",
        [
            {
                "Phage_ID": "PA",
                "Host_ID": "HA",
                "Host_name": "Host A",
                "Source_DB": "Source_A",
                "interaction": "virulent",
            }
        ],
        ["PA"],
        ["HA"],
    )
    source_b = _create_private_source(
        tmp_path,
        "Source_B",
        [
            {
                "Phage_ID": "PB",
                "Host_ID": "HB",
                "Host_name": "Host B",
                "Source_DB": "Source_B",
                "interaction": "temperate",
            }
        ],
        ["PB"],
        ["HB"],
    )

    conn = duckdb.connect(":memory:")
    _prepare_minimal_db(conn)

    first_run = ingest_private_sources_into_db(conn, [str(source_a), str(source_b)])
    assert len(first_run["ingested"]) == 2
    assert conn.execute("SELECT COUNT(*) FROM fact_phages WHERE source_type = 'private'").fetchone()[0] == 2

    # Rerun with only source_a (simulates source_b deleted from private_data folder)
    second_run = ingest_private_sources_into_db(conn, [str(source_a)])
    assert len(second_run["ingested"]) == 1

    private_rows = conn.execute(
        "SELECT Phage_ID, Source_DB FROM fact_phages WHERE source_type = 'private' ORDER BY Phage_ID"
    ).fetchall()
    assert private_rows == [("PA", "Source_A")]

    interaction_rows = conn.execute(
        "SELECT Phage_ID, Source_DB FROM private_interactions ORDER BY Phage_ID"
    ).fetchall()
    assert interaction_rows == [("PA", "Source_A")]

    host_rows = conn.execute(
        "SELECT Host_ID, source_type FROM dim_hosts WHERE source_type = 'private' ORDER BY Host_ID"
    ).fetchall()
    assert host_rows == [("HA", "private")]

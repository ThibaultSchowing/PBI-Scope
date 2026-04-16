#!/usr/bin/env python3

from pathlib import Path

import duckdb
import pandas as pd

from pbi.private_data import ingest_private_sources_into_db, validate_private_source


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


def test_private_ingestion_non_blocking_one_invalid_source(tmp_path):
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

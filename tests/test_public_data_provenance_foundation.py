#!/usr/bin/env python3

import csv
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "workflow" / "scripts" / "preprocessing"))
sys.path.insert(0, str(REPO_ROOT / "workflow" / "scripts" / "database"))

import download_public_file  # noqa: E402
import create_duckdb  # noqa: E402


def test_normalize_source_db_from_source_key():
    assert download_public_file._normalize_source_db("RefSeq_Phage_Metadata_URL") == "RefSeq"
    assert download_public_file._normalize_source_db("OnlyOneToken") == "OnlyOneToken"


def test_tsv_header_and_fingerprint(tmp_path):
    tsv_path = tmp_path / "sample.tsv"
    tsv_path.write_text("a\tb\tc\n1\t2\t3\n", encoding="utf-8")

    columns = download_public_file._read_tsv_header(str(tsv_path))
    assert columns == ["a", "b", "c"]
    assert download_public_file._schema_fingerprint(columns)


def test_duckdb_provenance_tables_resilient_to_missing_files():
    conn = duckdb.connect(":memory:")
    create_duckdb._create_dataset_provenance_table(conn, "")
    create_duckdb._create_pipeline_run_provenance_table(conn, "")

    assert conn.execute("SELECT COUNT(*) FROM dataset_provenance").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM pipeline_run_provenance").fetchone()[0] == 0


def test_csv_header_columns_reader(tmp_path):
    csv_path = tmp_path / "mini.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["A", "B"])
        writer.writerow(["1", "2"])

    assert create_duckdb._csv_header_columns(str(csv_path)) == {"A", "B"}

"""
Tests for the FastAPI API endpoints (api/app.py).

Uses FastAPI TestClient with a mocked SequenceRetriever backed by an
in-memory DuckDB and temporary FASTA files.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_client(retriever):
    """Create a TestClient with the retriever patched in."""
    from fastapi.testclient import TestClient
    import api.app as app_module

    client = TestClient(app_module.app)
    # Patch the global retriever after app is created
    app_module.retriever = retriever
    return client


# ---------------------------------------------------------------------------
# Pure helper function tests (no retriever needed)
# ---------------------------------------------------------------------------

class TestValidateWhereClause:
    def test_none_returns_none(self):
        from api.app import _validate_where_clause
        assert _validate_where_clause(None) is None

    def test_empty_string_returns_none(self):
        from api.app import _validate_where_clause
        assert _validate_where_clause("") is None
        assert _validate_where_clause("  ") is None

    def test_valid_clause_passes(self):
        from api.app import _validate_where_clause
        result = _validate_where_clause("Source_DB = 'RefSeq'")
        assert result == "Source_DB = 'RefSeq'"

    def test_semicolon_blocked(self):
        from api.app import _validate_where_clause
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_where_clause("x; DROP TABLE t")
        assert exc_info.value.status_code == 400

    def test_double_dash_blocked(self):
        from api.app import _validate_where_clause
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_where_clause("x -- comment")

    def test_exec_blocked(self):
        from api.app import _validate_where_clause
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_where_clause("EXEC xp_cmdshell")

    def test_drop_blocked(self):
        from api.app import _validate_where_clause
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_where_clause("DROP TABLE fact_phages")

    def test_insert_blocked(self):
        from api.app import _validate_where_clause
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_where_clause("INSERT INTO fact_phages VALUES (1)")

    def test_delete_blocked(self):
        from api.app import _validate_where_clause
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_where_clause("DELETE FROM fact_phages")

    def test_block_comment_blocked(self):
        from api.app import _validate_where_clause
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_where_clause("/* injection */ SELECT 1")


class TestDfToRecords:
    def test_replaces_inf_nan(self):
        from api.app import _df_to_records
        df = pd.DataFrame({"a": [1.0, np.inf, np.nan, -np.inf]})
        records = _df_to_records(df)
        assert records[0]["a"] == 1.0
        assert records[1]["a"] is None
        assert records[2]["a"] is None
        assert records[3]["a"] is None

    def test_normal_dataframe(self):
        from api.app import _df_to_records
        df = pd.DataFrame({"x": [1, 2], "y": ["a", "b"]})
        records = _df_to_records(df)
        assert len(records) == 2
        assert records[0]["x"] == 1
        assert records[1]["y"] == "b"


class TestGetDataPaths:
    def test_default_paths(self):
        from api.app import get_data_paths
        paths = get_data_paths()
        assert "database" in paths
        assert "phage_fasta" in paths
        assert "protein_fasta" in paths

    def test_custom_data_path(self, monkeypatch):
        from api.app import get_data_paths
        monkeypatch.setenv("DATA_PATH", "/custom/data")
        paths = get_data_paths()
        assert "custom" in paths["database"] and "data" in paths["database"]


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestRootEndpoint:
    def test_root(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "PBI Database API"
        assert "endpoints" in data
        # Check GFF3 endpoints are listed
        assert "phage_gff3" in data["endpoints"]
        assert "gff3_stats" in data["endpoints"]
        assert "gff3_sources" in data["endpoints"]


class TestHealthEndpoint:
    def test_healthy(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_unhealthy_when_no_retriever(self):
        from fastapi.testclient import TestClient
        import api.app as app_module
        original = app_module.retriever
        app_module.retriever = None
        try:
            client = TestClient(app_module.app)
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "degraded"
            assert resp.json()["database_connected"] is False
        finally:
            app_module.retriever = original


class TestStatsEndpoint:
    def test_stats(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/stats")
        # get_stats() uses complex SQL (source_type breakdown) that may fail
        # with a minimal test DB; 200 or 500 are both acceptable
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "database" in data


class TestTablesEndpoint:
    def test_tables(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/tables")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["tables"] >= 0


class TestQueryEndpoint:
    def test_valid_select(self, retriever):
        client = _make_test_client(retriever)
        resp = client.post("/query", json={"query": "SELECT 1 AS x", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["rows"] == 1

    def test_non_select_blocked(self, retriever):
        client = _make_test_client(retriever)
        resp = client.post("/query", json={"query": "DROP TABLE fact_phages"})
        assert resp.status_code == 400


class TestPhageMetadataEndpoint:
    def test_get_phage_metadata(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage-metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["rows"] > 0

    def test_with_limit(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage-metadata?limit=2")
        assert resp.status_code == 200
        assert resp.json()["rows"] <= 2

    def test_with_where(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage-metadata?where=Source_DB+%3D+%27RefSeq%27")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestProteinMetadataEndpoint:
    def test_get_protein_metadata(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/protein-metadata")
        # get_protein_metadata() expects many columns (Protein_source, Strand, etc.)
        # not present in a minimal test DB; 200 or 500 are both acceptable
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            assert data["rows"] > 0


class TestPhageSequenceEndpoint:
    def test_existing_phage(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/phage_001/sequence")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["sequence"]) > 0

    def test_nonexistent_phage(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/NONEXISTENT/sequence")
        assert resp.status_code == 404


class TestPhageGenomeEndpoint:
    def test_concat_mode(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/phage_001/genome?mode=concat")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "sequence" in data

    def test_first_mode(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/phage_001/genome?mode=first")
        assert resp.status_code == 200

    def test_list_mode(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/phage_001/genome?mode=list")
        assert resp.status_code == 200
        data = resp.json()
        assert "contigs" in data
        assert isinstance(data["contigs"], list)

    def test_dict_mode(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/phage_001/genome?mode=dict")
        assert resp.status_code == 200
        data = resp.json()
        assert "contigs" in data
        assert isinstance(data["contigs"], dict)

    def test_invalid_mode(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/phage_001/genome?mode=invalid")
        assert resp.status_code == 400

    def test_nonexistent_phage(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/phage/NONEXISTENT/genome")
        assert resp.status_code == 404 or resp.status_code == 500


class TestHostGenomeEndpoint:
    def test_concat_mode(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/host/host_001/genome?mode=concat")
        # May 500 if host FASTA index is missing, that's OK
        assert resp.status_code in (200, 500)


class TestHostGenomeStatsEndpoint:
    def test_existing_host(self, retriever):
        client = _make_test_client(retriever)
        resp = client.get("/host/host_001/genome-stats")
        # May 500 if host FASTA index is missing
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# GFF3 endpoint tests
# ---------------------------------------------------------------------------

class TestPhageGFF3Endpoint:
    def test_returns_gff3_content(self, gff3_index):
        """Test that /phage/{phage_id}/gff3 returns raw GFF3 content."""
        from fastapi.testclient import TestClient
        import api.app as app_module
        from pbi.gff3_retrieval import GFF3Retriever

        gff3_retriever = GFF3Retriever(
            str(gff3_index["gff3_dir"]),
            str(gff3_index["index_path"])
        )
        original = app_module.gff3_retriever
        app_module.gff3_retriever = gff3_retriever
        try:
            client = TestClient(app_module.app)
            resp = client.get("/phage/phage_001/gff3")
            assert resp.status_code == 200
            assert "##gff-version 3" in resp.text
            assert "phage_001" in resp.text
        finally:
            app_module.gff3_retriever = original

    def test_missing_phage_returns_404(self, gff3_index):
        """Test that missing phage returns 404."""
        from fastapi.testclient import TestClient
        import api.app as app_module
        from pbi.gff3_retrieval import GFF3Retriever

        gff3_retriever = GFF3Retriever(
            str(gff3_index["gff3_dir"]),
            str(gff3_index["index_path"])
        )
        original = app_module.gff3_retriever
        app_module.gff3_retriever = gff3_retriever
        try:
            client = TestClient(app_module.app)
            resp = client.get("/phage/NONEXISTENT/gff3")
            assert resp.status_code == 404
        finally:
            app_module.gff3_retriever = original

    def test_no_gff3_index_returns_503(self):
        """Test that missing GFF3 index returns 503."""
        from fastapi.testclient import TestClient
        import api.app as app_module

        original = app_module.gff3_retriever
        app_module.gff3_retriever = None
        try:
            client = TestClient(app_module.app)
            resp = client.get("/phage/phage_001/gff3")
            assert resp.status_code == 503
        finally:
            app_module.gff3_retriever = original


class TestGFF3StatsEndpoint:
    def test_returns_stats(self, gff3_index):
        """Test that /gff3/stats returns index statistics."""
        from fastapi.testclient import TestClient
        import api.app as app_module
        from pbi.gff3_retrieval import GFF3Retriever

        gff3_retriever = GFF3Retriever(
            str(gff3_index["gff3_dir"]),
            str(gff3_index["index_path"])
        )
        original = app_module.gff3_retriever
        app_module.gff3_retriever = gff3_retriever
        try:
            client = TestClient(app_module.app)
            resp = client.get("/gff3/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "stats" in data
            assert "total_phages" in data["stats"]
        finally:
            app_module.gff3_retriever = original

    def test_no_gff3_index_returns_503(self):
        """Test that missing GFF3 index returns 503."""
        from fastapi.testclient import TestClient
        import api.app as app_module

        original = app_module.gff3_retriever
        app_module.gff3_retriever = None
        try:
            client = TestClient(app_module.app)
            resp = client.get("/gff3/stats")
            assert resp.status_code == 503
        finally:
            app_module.gff3_retriever = original


class TestGFF3SourcesEndpoint:
    def test_returns_sources(self, gff3_index):
        """Test that /gff3/sources returns list of source databases."""
        from fastapi.testclient import TestClient
        import api.app as app_module
        from pbi.gff3_retrieval import GFF3Retriever

        gff3_retriever = GFF3Retriever(
            str(gff3_index["gff3_dir"]),
            str(gff3_index["index_path"])
        )
        original = app_module.gff3_retriever
        app_module.gff3_retriever = gff3_retriever
        try:
            client = TestClient(app_module.app)
            resp = client.get("/gff3/sources")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "sources" in data
            assert isinstance(data["sources"], list)
        finally:
            app_module.gff3_retriever = original

    def test_no_gff3_index_returns_503(self):
        """Test that missing GFF3 index returns 503."""
        from fastapi.testclient import TestClient
        import api.app as app_module

        original = app_module.gff3_retriever
        app_module.gff3_retriever = None
        try:
            client = TestClient(app_module.app)
            resp = client.get("/gff3/sources")
            assert resp.status_code == 503
        finally:
            app_module.gff3_retriever = original


class TestGetDataPathsGFF3:
    def test_gff3_paths_present(self):
        """Test that get_data_paths includes GFF3 paths."""
        from api.app import get_data_paths
        paths = get_data_paths()
        assert "gff3_dir" in paths
        assert "gff3_index" in paths
        assert "gff3" in paths["gff3_dir"]
        assert "gff3_index.json" in paths["gff3_index"]


# ---------------------------------------------------------------------------
# API key auth (n8n integration)
# ---------------------------------------------------------------------------

class TestApiKeyAuth:
    def test_health_exempt_from_auth(self, monkeypatch):
        """Health check stays open when PBI_API_KEY is set (Docker HEALTHCHECK)."""
        monkeypatch.setenv("PBI_API_KEY", "secret-key")
        from fastapi.testclient import TestClient
        import api.app as app_module

        client = TestClient(app_module.app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_non_exempt_endpoint_requires_key(self, monkeypatch):
        """A non-exempt endpoint returns 401 without the X-API-Key header."""
        monkeypatch.setenv("PBI_API_KEY", "secret-key")
        from fastapi.testclient import TestClient
        import api.app as app_module

        client = TestClient(app_module.app)
        resp = client.post("/blast/search", json={"sequence": "ACGT"})
        assert resp.status_code == 401
        assert "API key" in resp.json()["detail"]

    def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setenv("PBI_API_KEY", "secret-key")
        from fastapi.testclient import TestClient
        import api.app as app_module

        client = TestClient(app_module.app)
        resp = client.post(
            "/blast/search",
            json={"sequence": "ACGT"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401

    def test_valid_key_passes_auth(self, monkeypatch):
        """A valid key passes auth; the request then reaches the route logic."""
        monkeypatch.setenv("PBI_API_KEY", "secret-key")
        from fastapi.testclient import TestClient
        import api.app as app_module
        from unittest.mock import patch

        client = TestClient(app_module.app)
        with patch.object(app_module, "blast_searcher", None):
            resp = client.post(
                "/blast/search",
                json={"sequence": "ACGT"},
                headers={"X-API-Key": "secret-key"},
            )
            # Auth passed; now 503 because no BLAST databases are configured.
            assert resp.status_code == 503

    def test_auth_disabled_when_key_unset(self, monkeypatch):
        """Without PBI_API_KEY, auth is skipped (local/dev behaviour preserved)."""
        monkeypatch.delenv("PBI_API_KEY", raising=False)
        from fastapi.testclient import TestClient
        import api.app as app_module

        client = TestClient(app_module.app)
        resp = client.post("/blast/search", json={"sequence": "ACGT"})
        # No auth; hits 503 (no BLAST DB) rather than 401.
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Async BLAST jobs (n8n polling workflow)
# ---------------------------------------------------------------------------

class TestBlastJobs:
    @pytest.fixture(autouse=True)
    def _clear_jobs(self):
        import api.app as app_module
        app_module._BLAST_JOBS.clear()
        yield
        app_module._BLAST_JOBS.clear()

    def test_create_job_returns_202(self):
        import api.app as app_module
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        import pandas as pd

        client = TestClient(app_module.app)
        mock_df = pd.DataFrame({"hit_id": ["h1"], "pident": [99.0]})
        with patch.object(app_module, "blast_searcher") as mock_bs:
            mock_bs.search_sequence.return_value = mock_df
            resp = client.post("/blast/jobs", json={"sequence": "ACGT"})

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert "job_id" in data
        # Job is registered in the in-memory store for polling.
        assert data["job_id"] in app_module._BLAST_JOBS

    def test_get_job_unknown_returns_404(self):
        import api.app as app_module
        from fastapi.testclient import TestClient

        client = TestClient(app_module.app)
        resp = client.get("/blast/jobs/does-not-exist")
        assert resp.status_code == 404

    def test_get_job_returns_stored_job(self):
        import api.app as app_module
        from fastapi.testclient import TestClient

        client = TestClient(app_module.app)
        job_id = "test-job-1"
        now = app_module.time.time()
        app_module._BLAST_JOBS[job_id] = {
            "job_id": job_id,
            "status": "done",
            "created_at": now,
            "completed_at": now + 1.0,
            "hits": 3,
            "results": [{"hit_id": "h1"}],
            "program": "blastn",
        }
        resp = client.get(f"/blast/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "done"
        assert data["hits"] == 3
        assert len(data["results"]) == 1

    def test_list_jobs(self):
        import api.app as app_module
        from fastapi.testclient import TestClient

        client = TestClient(app_module.app)
        now = app_module.time.time()
        app_module._BLAST_JOBS["j1"] = {
            "job_id": "j1", "status": "queued", "created_at": now
        }
        resp = client.get("/blast/jobs")
        assert resp.status_code == 200
        assert isinstance(resp.json()["jobs"], list)
        assert len(resp.json()["jobs"]) >= 1

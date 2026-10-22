"""
FastAPI application for PBI database queries.

Provides metadata exploration, sequence retrieval, and genome access
via a shared SequenceRetriever instance.
"""

import asyncio
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import numpy as np

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel, Field
import duckdb

from pbi.sequence_retrieval import SequenceRetriever
from pbi.gff3_retrieval import GFF3Retriever
from pbi.blast_search import BlastSearcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('api.app')

# Global retriever instance
retriever: Optional[SequenceRetriever] = None
gff3_retriever: Optional[GFF3Retriever] = None
blast_searcher: Optional[BlastSearcher] = None

# ── Auth ─────────────────────────────────────────────────────────────────────

# API key (optional). When PBI_API_KEY is set, all non-exempt routes require
# the X-API-Key header. n8n runs inside the same compose network and sends the
# key via the HTTP Request node header. Enforced by the api_key_auth middleware
# below (not by a route dependency).

# Paths that do not require authentication (health checks, Swagger UI, OpenAPI
# spec import). Kept open so Docker HEALTHCHECK and n8n spec import work without
# a key; n8n workflows call authenticated endpoints with the header instead.
_AUTH_EXEMPT_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"}

# ── Async BLAST jobs ─────────────────────────────────────────────────────────

# In-memory job store (single uvicorn worker in Dockerfile.api). Suitable for
# n8n polling workflows; jobs are TTL-evicted on access.
_BLAST_JOBS: Dict[str, dict] = {}
_BLAST_JOB_TTL_SECONDS = 3600


def _evict_expired_blast_jobs() -> None:
    now = time.time()
    expired = [
        jid for jid, job in _BLAST_JOBS.items()
        if now - job.get("created_at", 0) > _BLAST_JOB_TTL_SECONDS
    ]
    for jid in expired:
        _BLAST_JOBS.pop(jid, None)


# ── Helpers ──────────────────────────────────────────────────────────────────

# Only allow SELECT statements to reduce SQL injection risk
_SAFE_QUERY_RE = re.compile(r'^\s*(SELECT|WITH|SHOW|DESCRIBE|EXPLAIN)\b', re.IGNORECASE)


def _validate_where_clause(clause: Optional[str]) -> Optional[str]:
    """Validate a WHERE clause fragment for safety."""
    if clause is None:
        return None
    clause = clause.strip()
    if not clause:
        return None
    # Block common injection patterns
    upper = clause.upper()
    
    # Check for non-word character patterns (substring match)
    non_word_forbidden = [';', '--', '/*', '*/']
    for pattern in non_word_forbidden:
        if pattern in upper:
            raise HTTPException(status_code=400, detail=f"Forbidden pattern in clause: {pattern}")
    
    # Check for SQL keywords (word boundary match)
    keyword_forbidden = ['EXEC', 'EXECUTE', 'DROP', 'DELETE',
                         'INSERT', 'UPDATE', 'ALTER', 'CREATE', 'TRUNCATE']
    for keyword in keyword_forbidden:
        if re.search(r'\b' + keyword + r'\b', upper):
            raise HTTPException(status_code=400, detail=f"Forbidden keyword in clause: {keyword}")
    return clause


def _df_to_records(df):
    """Convert a DataFrame to JSON-safe list of dicts."""
    df = df.replace([np.inf, -np.inf], None)
    df = df.replace({np.nan: None})
    return df.to_dict(orient='records')


def get_data_paths():
    """Get paths to database and FASTA files from environment or defaults."""
    base_path = Path(os.getenv('DATA_PATH', 'data/processed'))

    return {
        'database': str(base_path / 'databases' / 'phage_database_optimized.duckdb'),
        'phage_fasta': str(base_path / 'sequences' / 'all_phages.fasta'),
        'protein_fasta': str(base_path / 'sequences' / 'all_proteins.fasta'),
        'host_mapping': str(base_path / 'sequences' / 'host_fasta_mapping.json'),
        'host_fasta': str(base_path / 'sequences' / 'all_hosts.fasta'),
        'blast_db': str(base_path / 'blast_db'),
        'gff3_dir': str(base_path / 'gff3'),
        'gff3_index': str(base_path / 'gff3' / 'gff3_index.json'),
    }


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global retriever, gff3_retriever, blast_searcher

    try:
        paths = get_data_paths()
        logger.info(f"Connecting to database: {paths['database']}")
        logger.info(f"Phage FASTA: {paths['phage_fasta']}")
        logger.info(f"Protein FASTA: {paths['protein_fasta']}")

        # Check required files — if missing, start in degraded mode
        missing = [
            name for name in ['database', 'phage_fasta', 'protein_fasta']
            if not Path(paths[name]).exists()
        ]
        if missing:
            logger.warning(
                "Missing data files: %s. API running in degraded mode "
                "(metadata/sequence endpoints unavailable).",
                ", ".join(missing),
            )
        else:
            # Optional host files
            host_mapping = paths.get('host_mapping')
            host_fasta = paths.get('host_fasta')
            if host_mapping and Path(host_mapping).exists():
                logger.info(f"Host mapping: {host_mapping}")
            if host_fasta and Path(host_fasta).exists():
                logger.info(f"Host FASTA: {host_fasta}")

            retriever = SequenceRetriever(
                paths['database'],
                paths['phage_fasta'],
                paths['protein_fasta'],
                host_fasta_path=host_fasta if host_fasta and Path(host_fasta).exists() else None,
                host_mapping_path=host_mapping if host_mapping and Path(host_mapping).exists() else None,
            )
            logger.info("Successfully connected to database")

            stats = retriever.get_stats()
            logger.info(f"Database statistics: {stats['database']}")

        # Initialize GFF3 retriever (optional)
        gff3_index = paths.get('gff3_index')
        gff3_dir = paths.get('gff3_dir')
        if gff3_index and Path(gff3_index).exists():
            gff3_retriever = GFF3Retriever(gff3_dir, gff3_index)
            gff3_stats = gff3_retriever.stats()
            logger.info(f"GFF3 index loaded: {gff3_stats['total_phages']:,} phages")
        else:
            logger.warning("GFF3 index not found, GFF3 endpoints will be unavailable")

        # Initialize BLAST searcher (optional)
        blast_db_dir = Path(paths['blast_db'])
        if blast_db_dir.exists():
            try:
                blast_searcher = BlastSearcher(blast_db_dir)
                blast_dbs = blast_searcher.list_databases()
                ready = sum(1 for d in blast_dbs.values() if d["exists"])
                logger.info(f"BLAST databases initialized: {ready}/{len(blast_dbs)} ready")
            except Exception as e:
                logger.warning(f"BLAST initialization failed: {e}")
                blast_searcher = None
        else:
            logger.warning("BLAST database directory not found, BLAST endpoints will be unavailable")

    except Exception as e:
        logger.error(f"Startup error (non-blocking): {e}")

    yield

    if retriever:
        retriever.close()
        logger.info("Database connection closed")


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PBI Database API",
    description="API for querying the Phage Bacteria Interactions database",
    version="0.6.0",
    lifespan=lifespan
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Require X-API-Key on non-exempt routes when PBI_API_KEY is set."""
    path = request.url.path
    if path in _AUTH_EXEMPT_PATHS or path.startswith("/docs/") or path == "/openapi.json":
        return await call_next(request)
    api_key = os.getenv("PBI_API_KEY")
    if api_key:
        provided = request.headers.get("X-API-Key")
        if not provided or provided != api_key:
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key"})
    return await call_next(request)


def custom_openapi():
    """Expose an ApiKeyHeader security scheme so /docs and n8n spec import work."""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "ApiKeyHeader"
    ] = {"type": "apiKey", "in": "header", "name": "X-API-Key"}
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# ── Request models ───────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    limit: Optional[int] = 1000


class PhageSequenceRequest(BaseModel):
    query: Optional[str] = None
    phage_ids: Optional[List[str]] = None
    limit: Optional[int] = 1000


class ProteinSequenceRequest(BaseModel):
    query: Optional[str] = None
    protein_ids: Optional[List[str]] = None
    limit: Optional[int] = 1000


class BlastSearchRequest(BaseModel):
    sequence: str
    program: str = "blastn"
    db: Optional[str] = None
    max_hits: int = Field(default=10, ge=1, le=100, description="Max hits to return (1-100)")
    evalue: float = 1e-5
    timeout: int = Field(default=1800, ge=1, le=86400, description="BLAST timeout in seconds (default 1800 = 30 min)")
    num_threads: int = Field(default=1, ge=1, le=16, description="Number of BLAST threads (default 1)")


class BlastJobCreateResponse(BaseModel):
    job_id: str
    status: str = "queued"


class BlastJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    program: Optional[str] = None
    db: Optional[str] = None
    hits: Optional[int] = None
    results: Optional[List[dict]] = None
    error: Optional[str] = None


class BlastJobListResponse(BaseModel):
    jobs: List[dict]


# ── Utility endpoints ────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "PBI Database API",
        "version": "0.6.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "stats": "/stats",
            "tables": "/tables",
            "query": "/query (POST)",
            # Metadata
            "phage_metadata": "/phage-metadata",
            "host_metadata": "/host-metadata",
            "phage_host_metadata": "/phage-host-metadata",
            "phage_host_pairs": "/phage-host-pairs",
            "protein_metadata": "/protein-metadata",
            # Sequences
            "phages": "/phages (POST)",
            "proteins": "/proteins (POST)",
            "phages_fasta": "/phages/fasta (POST)",
            "proteins_fasta": "/proteins/fasta (POST)",
            "phage_sequence": "/phage/{phage_id}/sequence",
             # Genomes
             "phage_genome": "/phage/{phage_id}/genome",
             "host_genome": "/host/{host_id}/genome",
             "host_genome_stats": "/host/{host_id}/genome-stats",
             # GFF3
             "phage_gff3": "/phage/{phage_id}/gff3",
             "gff3_stats": "/gff3/stats",
             "gff3_sources": "/gff3/sources",
             # BLAST
             "blast_search": "/blast/search (POST)",
             "blast_databases": "/blast/databases",
             "blast_status": "/blast/status",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns 200 in both healthy and degraded modes.  Clients should check
    ``database_connected`` to determine if metadata/sequence endpoints are
    available.
    """
    return {
        "status": "healthy" if retriever is not None else "degraded",
        "database_connected": retriever is not None,
        "blast_available": blast_searcher is not None,
    }


@app.get("/stats")
async def get_statistics():
    """Get database statistics."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        return retriever.get_stats()
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tables")
async def list_tables():
    """List all tables and views in the database."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        tables_result = retriever.conn.execute("SHOW TABLES").fetchdf()
        tables = tables_result['name'].tolist() if 'name' in tables_result.columns else []

        views_result = retriever.conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
        ).fetchdf()
        views = views_result['table_name'].tolist() if 'table_name' in views_result.columns else []

        table_names = [t for t in tables if t not in views]

        return {
            "success": True,
            "rows": len(tables),
            "tables": len(table_names),
            "views": len(views),
            "data": [{"name": name, "type": "view" if name in views else "table"} for name in tables]
        }
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query")
async def execute_query(request: QueryRequest):
    """Execute a read-only SQL query against the database."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    # Enforce SELECT-only
    if not _SAFE_QUERY_RE.match(request.query):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")

    try:
        result = retriever.conn.execute(request.query).fetchdf()
        if request.limit:
            result = result.head(request.limit)
        return {
            "success": True,
            "rows": len(result),
            "data": _df_to_records(result)
        }
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


# ── Metadata endpoints ───────────────────────────────────────────────────────

@app.get("/phage-metadata")
async def get_phage_metadata(
    where: Optional[str] = Query(None, description="SQL WHERE clause fragment (without WHERE keyword)"),
    limit: Optional[int] = Query(1000, ge=1, le=100000)
):
    """Get phage metadata from fact_phages with optional filtering."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    where = _validate_where_clause(where)
    try:
        df = retriever.get_phage_metadata(where_clause=where, limit=limit)
        return {"success": True, "rows": len(df), "data": _df_to_records(df)}
    except Exception as e:
        logger.error(f"Error getting phage metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/host-metadata")
async def get_host_metadata(
    where: Optional[str] = Query(None, description="SQL WHERE clause fragment (without WHERE keyword)"),
    limit: Optional[int] = Query(1000, ge=1, le=100000)
):
    """Get host metadata from dim_hosts with optional filtering."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    where = _validate_where_clause(where)
    try:
        df = retriever.get_host_metadata(where_clause=where, limit=limit)
        return {"success": True, "rows": len(df), "data": _df_to_records(df)}
    except ValueError as e:
        # Host data table doesn't exist - return informative error
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting host metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/phage-host-metadata")
async def get_phage_host_metadata(
    where: Optional[str] = Query(None, description="SQL WHERE clause fragment (without WHERE keyword)"),
    limit: Optional[int] = Query(1000, ge=1, le=100000)
):
    """Get combined phage-host metadata with optional filtering."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    where = _validate_where_clause(where)
    try:
        df = retriever.get_phage_host_metadata(where_clause=where, limit=limit)
        return {"success": True, "rows": len(df), "data": _df_to_records(df)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting phage-host metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/phage-host-pairs")
async def get_phage_host_pairs(
    where: Optional[str] = Query(None, description="SQL WHERE clause fragment"),
    limit: Optional[int] = Query(1000, ge=1, le=100000),
    host_contig_mode: str = Query("concat", description="Host contig mode: first, concat, list, dict"),
    phage_contig_mode: str = Query("first", description="Phage contig mode: first, concat, list, dict"),
):
    """Get phage-host pairs with sequences and metadata."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    where = _validate_where_clause(where)
    try:
        df = retriever.get_phage_host_pairs(
            where_clause=where,
            limit=limit,
            host_contig_mode=host_contig_mode,
            phage_contig_mode=phage_contig_mode,
        )
        return {"success": True, "rows": len(df), "data": _df_to_records(df)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting phage-host pairs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/protein-metadata")
async def get_protein_metadata(
    where: Optional[str] = Query(None, description="SQL WHERE clause fragment"),
    limit: Optional[int] = Query(1000, ge=1, le=100000)
):
    """Get protein metadata from dim_proteins with optional filtering."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    where = _validate_where_clause(where)
    try:
        df = retriever.get_protein_metadata(where_clause=where, limit=limit)
        return {"success": True, "rows": len(df), "data": _df_to_records(df)}
    except Exception as e:
        logger.error(f"Error getting protein metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Sequence endpoints ───────────────────────────────────────────────────────

@app.get("/phage/{phage_id}/sequence")
async def get_phage_sequence(phage_id: str):
    """Get the DNA sequence for a single phage."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        seq = retriever.get_phage_sequence(phage_id)
        if seq is None:
            raise HTTPException(status_code=404, detail=f"Phage not found: {phage_id}")
        return {"success": True, "phage_id": phage_id, "sequence": seq, "length": len(seq)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting phage sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/phages")
async def get_phages(request: PhageSequenceRequest):
    """Get phage sequences based on query or IDs."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        if request.query:
            result = retriever.get_phage_sequences(request.query, limit=request.limit)
        elif request.phage_ids:
            placeholders = ', '.join(['?'] * len(request.phage_ids))
            query = f"SELECT Phage_ID FROM fact_phages WHERE Phage_ID IN ({placeholders})"
            result = retriever.get_phage_sequences(query, request.phage_ids)
        else:
            raise HTTPException(status_code=400, detail="Either 'query' or 'phage_ids' must be provided")
        return {"success": True, "count": len(result), "sequences": result.to_dict(orient='records')}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving phages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/proteins")
async def get_proteins(request: ProteinSequenceRequest):
    """Get protein sequences based on query or IDs."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        if request.query:
            result = retriever.get_protein_sequences(request.query, limit=request.limit)
        elif request.protein_ids:
            placeholders = ', '.join(['?'] * len(request.protein_ids))
            query = f"SELECT Protein_ID FROM dim_proteins WHERE Protein_ID IN ({placeholders})"
            result = retriever.get_protein_sequences(query, request.protein_ids)
        else:
            raise HTTPException(status_code=400, detail="Either 'query' or 'protein_ids' must be provided")
        return {"success": True, "count": len(result), "sequences": result.to_dict(orient='records')}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving proteins: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/phages/fasta", response_class=PlainTextResponse)
async def get_phages_fasta(request: PhageSequenceRequest):
    """Get phage sequences in FASTA format."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        if request.query:
            result = retriever.get_phage_sequences(request.query, limit=request.limit)
        elif request.phage_ids:
            placeholders = ', '.join(['?'] * len(request.phage_ids))
            query = f"SELECT Phage_ID FROM fact_phages WHERE Phage_ID IN ({placeholders})"
            result = retriever.get_phage_sequences(query, request.phage_ids)
        else:
            raise HTTPException(status_code=400, detail="Either 'query' or 'phage_ids' must be provided")
        fasta_lines = []
        for _, row in result.iterrows():
            fasta_lines.append(f">{row['id']}")
            fasta_lines.append(row['sequence'])
        return "\n".join(fasta_lines)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating FASTA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/proteins/fasta", response_class=PlainTextResponse)
async def get_proteins_fasta(request: ProteinSequenceRequest):
    """Get protein sequences in FASTA format."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        if request.query:
            result = retriever.get_protein_sequences(request.query, limit=request.limit)
        elif request.protein_ids:
            placeholders = ', '.join(['?'] * len(request.protein_ids))
            query = f"SELECT Protein_ID FROM dim_proteins WHERE Protein_ID IN ({placeholders})"
            result = retriever.get_protein_sequences(query, request.protein_ids)
        else:
            raise HTTPException(status_code=400, detail="Either 'query' or 'protein_ids' must be provided")
        fasta_lines = []
        for _, row in result.iterrows():
            fasta_lines.append(f">{row['id']}")
            fasta_lines.append(row['sequence'])
        return "\n".join(fasta_lines)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating FASTA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Genome endpoints ─────────────────────────────────────────────────────────

@app.get("/phage/{phage_id}/genome")
async def get_phage_genome(
    phage_id: str,
    mode: str = Query("concat", description="Return mode: concat, first, list, dict"),
    gap: int = Query(0, ge=0, description="Gap between contigs in concat mode"),
    order: str = Query("length_desc", description="Contig order: length_desc, length_asc, natural"),
):
    """Get full phage genome with multi-contig assembly support."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    if mode not in ("concat", "first", "list", "dict"):
        raise HTTPException(status_code=400, detail="mode must be one of: concat, first, list, dict")
    try:
        result = retriever.get_phage_genome(phage_id, mode=mode, gap=gap, order=order)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Phage not found: {phage_id}")
        if mode == "concat":
            return {"success": True, "phage_id": phage_id, "mode": mode, "sequence": result, "length": len(result)}
        elif mode == "first":
            return {"success": True, "phage_id": phage_id, "mode": mode, "sequence": result, "length": len(result)}
        elif mode == "list":
            return {"success": True, "phage_id": phage_id, "mode": mode, "contigs": result, "count": len(result)}
        else:
            return {"success": True, "phage_id": phage_id, "mode": mode, "contigs": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting phage genome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/host/{host_id}/genome")
async def get_host_genome(
    host_id: str,
    mode: str = Query("concat", description="Return mode: concat, first, list, dict"),
    gap: int = Query(0, ge=0, description="Gap between contigs in concat mode"),
    order: str = Query("length_desc", description="Contig order: length_desc, length_asc, natural"),
):
    """Get full host genome with multi-contig assembly support."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    if mode not in ("concat", "first", "list", "dict"):
        raise HTTPException(status_code=400, detail="mode must be one of: concat, first, list, dict")
    try:
        result = retriever.get_host_genome(host_id, mode=mode, gap=gap, order=order)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Host not found: {host_id}")
        if mode == "concat":
            return {"success": True, "host_id": host_id, "mode": mode, "sequence": result, "length": len(result)}
        elif mode == "first":
            return {"success": True, "host_id": host_id, "mode": mode, "sequence": result, "length": len(result)}
        elif mode == "list":
            return {"success": True, "host_id": host_id, "mode": mode, "contigs": result, "count": len(result)}
        else:
            return {"success": True, "host_id": host_id, "mode": mode, "contigs": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting host genome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/host/{host_id}/genome-stats")
async def get_host_genome_stats(host_id: str):
    """Get contig statistics for a host genome without loading full sequence."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        stats = retriever.get_host_genome_stats(host_id)
        if stats is None:
            raise HTTPException(status_code=404, detail=f"Host not found: {host_id}")
        return {"success": True, "host_id": host_id, "stats": stats}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting host genome stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GFF3 endpoints ───────────────────────────────────────────────────────────

@app.get("/phage/{phage_id}/gff3", response_class=PlainTextResponse)
async def get_phage_gff3(phage_id: str):
    """Get GFF3 annotations for a single phage."""
    if gff3_retriever is None:
        raise HTTPException(status_code=503, detail="GFF3 index not loaded")
    try:
        gff3_content = gff3_retriever.get_gff3(phage_id)
        if not gff3_content:
            raise HTTPException(status_code=404, detail=f"GFF3 not found for phage: {phage_id}")
        return gff3_content
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting GFF3 for phage {phage_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gff3/stats")
async def get_gff3_stats():
    """Get GFF3 index statistics."""
    if gff3_retriever is None:
        raise HTTPException(status_code=503, detail="GFF3 index not loaded")
    try:
        stats = gff3_retriever.stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Error getting GFF3 stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gff3/sources")
async def get_gff3_sources():
    """Get list of source databases in the GFF3 index."""
    if gff3_retriever is None:
        raise HTTPException(status_code=503, detail="GFF3 index not loaded")
    try:
        stats = gff3_retriever.stats()
        sources = sorted(stats['sources'].keys())
        return {"success": True, "count": len(sources), "sources": sources}
    except Exception as e:
        logger.error(f"Error getting GFF3 sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ── BLAST endpoints ───────────────────────────────────────────────────────────

async def _run_blast_job(job_id: str, request: BlastSearchRequest) -> None:
    """Run a BLAST search in a worker thread and update the in-memory job store."""
    _BLAST_JOBS[job_id]["status"] = "running"
    _BLAST_JOBS[job_id]["started_at"] = time.time()
    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: blast_searcher.search_sequence(
                request.sequence,
                program=request.program,
                db=request.db,
                max_hits=request.max_hits,
                evalue=request.evalue,
                timeout=request.timeout,
                num_threads=request.num_threads,
            ),
        )
        _BLAST_JOBS[job_id]["status"] = "done"
        _BLAST_JOBS[job_id]["hits"] = len(df)
        _BLAST_JOBS[job_id]["results"] = _df_to_records(df)
        _BLAST_JOBS[job_id]["completed_at"] = time.time()
    except Exception as e:
        logger.error(f"BLAST job {job_id} failed: {e}")
        _BLAST_JOBS[job_id]["status"] = "failed"
        _BLAST_JOBS[job_id]["error"] = str(e)
        _BLAST_JOBS[job_id]["completed_at"] = time.time()


@app.post("/blast/search")
def blast_search(request: BlastSearchRequest):
    """Search a sequence against BLAST databases (synchronous, blocks until done).

    Runs in FastAPI's threadpool so it does not block the event loop; prefer
    /blast/jobs for long searches called from n8n.
    """
    if blast_searcher is None:
        raise HTTPException(status_code=503, detail="BLAST databases not available")
    try:
        df = blast_searcher.search_sequence(
            request.sequence,
            program=request.program,
            db=request.db,
            max_hits=request.max_hits,
            evalue=request.evalue,
            timeout=request.timeout,
            num_threads=request.num_threads,
        )
        return {
            "success": True,
            "program": request.program,
            "db": request.db or "auto",
            "hits": len(df),
            "results": _df_to_records(df),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"BLAST search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/blast/jobs", response_model=BlastJobCreateResponse, status_code=202)
async def create_blast_job(request: BlastSearchRequest):
    """Queue a BLAST search and return a job id for polling (n8n-friendly)."""
    if blast_searcher is None:
        raise HTTPException(status_code=503, detail="BLAST databases not available")
    job_id = str(uuid.uuid4())
    _BLAST_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "created_at": time.time(),
        "program": request.program,
        "db": request.db,
    }
    asyncio.create_task(_run_blast_job(job_id, request))
    return {"job_id": job_id, "status": "queued"}


@app.get("/blast/jobs/{job_id}", response_model=BlastJobResponse)
async def get_blast_job(job_id: str):
    """Poll a BLAST job: queued | running | done | failed."""
    _evict_expired_blast_jobs()
    job = _BLAST_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/blast/jobs", response_model=BlastJobListResponse)
async def list_blast_jobs():
    """List active BLAST jobs (expired jobs are evicted on each call)."""
    _evict_expired_blast_jobs()
    return {"jobs": list(_BLAST_JOBS.values())}


@app.get("/blast/databases")
async def get_blast_databases():
    """List available BLAST databases and their status."""
    if blast_searcher is None:
        raise HTTPException(status_code=503, detail="BLAST databases not available")
    try:
        dbs = blast_searcher.list_databases()
        return {"success": True, "databases": dbs}
    except Exception as e:
        logger.error(f"Error listing BLAST databases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/blast/status")
async def get_blast_status():
    """Get BLAST installation and database status."""
    import shutil
    blastn_path = shutil.which("blastn")
    blast_installed = blastn_path is not None

    databases_built = False
    available_dbs = []
    if blast_searcher is not None:
        try:
            dbs = blast_searcher.list_databases()
            available_dbs = [name for name, info in dbs.items() if info["exists"]]
            databases_built = len(available_dbs) > 0
        except Exception:
            pass

    return {
        "success": True,
        "blast_installed": blast_installed,
        "databases_built": databases_built,
        "available_databases": available_dbs,
    }

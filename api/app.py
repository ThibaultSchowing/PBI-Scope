"""
FastAPI application for querying the PBI phage database

This API provides endpoints to:
- Query the DuckDB database
- Retrieve phage and protein sequences
- Get database statistics
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import duckdb
import os
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="PBI API",
    description="API for querying Phage-Bacteria Interaction database",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Database paths from environment variables or defaults
DB_PATH = os.getenv("DB_PATH", "/data/processed/databases/phage_database_optimized.duckdb")
PHAGE_FASTA_PATH = os.getenv("PHAGE_FASTA_PATH", "/data/processed/sequences/all_phages.fasta")
PROTEIN_FASTA_PATH = os.getenv("PROTEIN_FASTA_PATH", "/data/processed/sequences/all_proteins.fasta")

# Global database connection (read-only)
db_conn = None

# Pydantic models for request/response
class QueryRequest(BaseModel):
    """SQL query request"""
    sql: str = Field(..., description="SQL query to execute")
    limit: Optional[int] = Field(None, description="Maximum number of rows to return", ge=1, le=10000)

class PhageQueryRequest(BaseModel):
    """Request to get phage sequences"""
    phage_ids: Optional[List[str]] = Field(None, description="List of Phage IDs")
    sql: Optional[str] = Field(None, description="SQL query that returns Phage_ID column")
    limit: Optional[int] = Field(100, description="Maximum number of sequences to return", ge=1, le=1000)

class ProteinQueryRequest(BaseModel):
    """Request to get protein sequences"""
    protein_ids: Optional[List[str]] = Field(None, description="List of Protein IDs")
    sql: Optional[str] = Field(None, description="SQL query that returns Protein_ID column")
    limit: Optional[int] = Field(100, description="Maximum number of sequences to return", ge=1, le=1000)


@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    global db_conn
    try:
        logger.info(f"Connecting to database: {DB_PATH}")
        if not Path(DB_PATH).exists():
            logger.error(f"Database not found: {DB_PATH}")
            raise FileNotFoundError(f"Database not found: {DB_PATH}")
        
        db_conn = duckdb.connect(DB_PATH, read_only=True)
        logger.info("Database connection established")
        
        # Verify database structure
        tables = db_conn.execute("SHOW TABLES").fetchall()
        logger.info(f"Found {len(tables)} tables in database")
        
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Close database connection on shutdown"""
    global db_conn
    if db_conn:
        db_conn.close()
        logger.info("Database connection closed")


@app.get("/", tags=["General"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "PBI API - Phage-Bacteria Interaction Database",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", tags=["General"])
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        result = db_conn.execute("SELECT 1").fetchone()
        return {
            "status": "healthy",
            "database": "connected",
            "test_query": "passed"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {str(e)}")


@app.get("/stats", tags=["Database"])
async def get_stats():
    """Get database statistics"""
    try:
        stats = {
            "tables": {},
            "views": {}
        }
        
        # Get table counts
        tables_to_count = [
            "fact_phages",
            "dim_proteins",
            "dim_terminators",
            "dim_anti_crispr",
            "dim_virulent_factors",
            "dim_transmembrane_proteins",
            "dim_trna_tmrna",
            "dim_antimicrobial_resistance_genes",
            "dim_crispr_arrays"
        ]
        
        for table in tables_to_count:
            try:
                count = db_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats["tables"][table] = count
            except Exception as e:
                logger.warning(f"Could not count {table}: {e}")
                stats["tables"][table] = "error"
        
        # Get view names
        views = db_conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
        stats["views"] = [v[0] for v in views]
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")


@app.get("/tables", tags=["Database"])
async def list_tables():
    """List all tables in the database"""
    try:
        tables = db_conn.execute("SHOW TABLES").fetchall()
        return {
            "tables": [t[0] for t in tables]
        }
    except Exception as e:
        logger.error(f"Error listing tables: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing tables: {str(e)}")


@app.get("/tables/{table_name}/schema", tags=["Database"])
async def get_table_schema(table_name: str):
    """Get schema for a specific table"""
    try:
        # Get column information
        schema = db_conn.execute(f"DESCRIBE {table_name}").fetchdf()
        return {
            "table": table_name,
            "schema": schema.to_dict(orient="records")
        }
    except Exception as e:
        logger.error(f"Error getting schema for {table_name}: {e}")
        raise HTTPException(status_code=404, detail=f"Table not found or error: {str(e)}")


@app.post("/query", tags=["Database"])
async def execute_query(request: QueryRequest):
    """
    Execute a custom SQL query
    
    Note: Only SELECT queries are allowed for safety
    """
    try:
        sql = request.sql.strip()
        
        # Security: Only allow SELECT queries
        if not sql.upper().startswith("SELECT"):
            raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")
        
        # Apply limit if specified
        if request.limit:
            sql = f"{sql} LIMIT {request.limit}"
        
        logger.info(f"Executing query: {sql[:100]}...")
        result = db_conn.execute(sql).fetchdf()
        
        return {
            "rows": len(result),
            "columns": result.columns.tolist(),
            "data": result.to_dict(orient="records")
        }
        
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


@app.get("/phages", tags=["Phages"])
async def get_phages(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of phages to return"),
    source_db: Optional[str] = Query(None, description="Filter by source database"),
    min_length: Optional[int] = Query(None, description="Minimum phage length"),
    max_length: Optional[int] = Query(None, description="Maximum phage length"),
    host: Optional[str] = Query(None, description="Filter by host organism"),
    lifestyle: Optional[str] = Query(None, description="Filter by lifestyle (e.g., virulent, temperate)")
):
    """Get phage metadata with optional filtering"""
    try:
        query = "SELECT * FROM fact_phages WHERE 1=1"
        
        if source_db:
            query += f" AND Source_DB = '{source_db}'"
        if min_length:
            query += f" AND Length >= {min_length}"
        if max_length:
            query += f" AND Length <= {max_length}"
        if host:
            query += f" AND Host LIKE '%{host}%'"
        if lifestyle:
            query += f" AND Lifestyle = '{lifestyle}'"
        
        query += f" LIMIT {limit}"
        
        result = db_conn.execute(query).fetchdf()
        
        return {
            "count": len(result),
            "phages": result.to_dict(orient="records")
        }
        
    except Exception as e:
        logger.error(f"Error getting phages: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/phages/{phage_id}", tags=["Phages"])
async def get_phage_by_id(phage_id: str):
    """Get detailed information about a specific phage"""
    try:
        # Get basic phage info
        phage = db_conn.execute(
            "SELECT * FROM fact_phages WHERE Phage_ID = ?", 
            [phage_id]
        ).fetchdf()
        
        if len(phage) == 0:
            raise HTTPException(status_code=404, detail=f"Phage {phage_id} not found")
        
        # Get associated proteins
        proteins = db_conn.execute(
            "SELECT COUNT(*) as count FROM dim_proteins WHERE Phage_ID = ?",
            [phage_id]
        ).fetchone()[0]
        
        return {
            "phage": phage.to_dict(orient="records")[0],
            "protein_count": proteins
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting phage {phage_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/proteins", tags=["Proteins"])
async def get_proteins(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of proteins to return"),
    phage_id: Optional[str] = Query(None, description="Filter by Phage ID"),
    min_molecular_weight: Optional[float] = Query(None, description="Minimum molecular weight"),
    classification: Optional[str] = Query(None, description="Filter by protein classification")
):
    """Get protein metadata with optional filtering"""
    try:
        query = "SELECT * FROM dim_proteins WHERE 1=1"
        
        if phage_id:
            query += f" AND Phage_ID = '{phage_id}'"
        if min_molecular_weight:
            query += f" AND Molecular_weight >= {min_molecular_weight}"
        if classification:
            query += f" AND Protein_classification LIKE '%{classification}%'"
        
        query += f" LIMIT {limit}"
        
        result = db_conn.execute(query).fetchdf()
        
        return {
            "count": len(result),
            "proteins": result.to_dict(orient="records")
        }
        
    except Exception as e:
        logger.error(f"Error getting proteins: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/sources", tags=["Database"])
async def get_data_sources():
    """Get list of data sources in the database"""
    try:
        sources = db_conn.execute(
            "SELECT DISTINCT Source_DB, COUNT(*) as phage_count FROM fact_phages GROUP BY Source_DB ORDER BY phage_count DESC"
        ).fetchdf()
        
        return {
            "sources": sources.to_dict(orient="records")
        }
        
    except Exception as e:
        logger.error(f"Error getting sources: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

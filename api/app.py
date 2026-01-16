"""
FastAPI application for PBI database queries.

This API provides endpoints for querying the phage database and retrieving sequences.
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import duckdb

from pbi.sequence_retrieval import SequenceRetriever

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('api.app')

# Global retriever instance
retriever: Optional[SequenceRetriever] = None


def get_data_paths():
    """
    Get paths to database and FASTA files from environment or defaults.
    
    Returns:
        dict: Paths to data files
    """
    base_path = Path(os.getenv('DATA_PATH', '/data/processed'))
    
    return {
        'database': str(base_path / 'databases' / 'phage_database_optimized.duckdb'),
        'phage_fasta': str(base_path / 'sequences' / 'all_phages.fasta'),
        'protein_fasta': str(base_path / 'sequences' / 'all_proteins.fasta'),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global retriever
    
    # Startup
    try:
        paths = get_data_paths()
        logger.info(f"Connecting to database: {paths['database']}")
        logger.info(f"Phage FASTA: {paths['phage_fasta']}")
        logger.info(f"Protein FASTA: {paths['protein_fasta']}")
        
        # Check if files exist
        for name, path in paths.items():
            if not Path(path).exists():
                raise FileNotFoundError(f"{name.capitalize()} not found: {path}")
        
        retriever = SequenceRetriever(
            paths['database'],
            paths['phage_fasta'],
            paths['protein_fasta']
        )
        logger.info("✅ Successfully connected to database")
        
        # Log database statistics
        stats = retriever.get_stats()
        logger.info(f"Database statistics: {stats['database']}")
        
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    
    yield
    
    # Shutdown
    if retriever:
        retriever.close()
        logger.info("Database connection closed")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="PBI Database API",
    description="API for querying phage bioinformatics database and retrieving sequences",
    version="0.1.0",
    lifespan=lifespan
)


class QueryRequest(BaseModel):
    """Request model for SQL queries."""
    query: str
    limit: Optional[int] = 1000


class PhageSequenceRequest(BaseModel):
    """Request model for phage sequence retrieval."""
    query: Optional[str] = None
    phage_ids: Optional[List[str]] = None
    limit: Optional[int] = 1000


class ProteinSequenceRequest(BaseModel):
    """Request model for protein sequence retrieval."""
    query: Optional[str] = None
    protein_ids: Optional[List[str]] = None
    limit: Optional[int] = 1000


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "PBI Database API",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "stats": "/stats",
            "query": "/query (POST)",
            "phages": "/phages (POST)",
            "proteins": "/proteins (POST)",
            "phages_fasta": "/phages/fasta (POST)",
            "proteins_fasta": "/proteins/fasta (POST)"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    return {
        "status": "healthy",
        "database": "connected"
    }


@app.get("/stats")
async def get_statistics():
    """Get database statistics."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        stats = retriever.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query")
async def execute_query(request: QueryRequest):
    """
    Execute a custom SQL query against the database.
    
    WARNING: Use with caution in production. Consider limiting to read-only queries.
    """
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # Execute query and convert to dict
        result = retriever.conn.execute(request.query).fetchdf()
        
        # Apply limit if specified
        if request.limit:
            result = result.head(request.limit)
        
        return {
            "success": True,
            "rows": len(result),
            "data": result.to_dict(orient='records')
        }
    except Exception as e:
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


@app.post("/phages")
async def get_phages(request: PhageSequenceRequest):
    """Get phage sequences based on query or IDs."""
    if retriever is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        if request.query:
            result = retriever.get_phage_sequences(
                request.query,
                limit=request.limit
            )
        elif request.phage_ids:
            # Build SQL query from IDs
            ids_str = "', '".join(request.phage_ids)
            query = f"SELECT Phage_ID FROM fact_phages WHERE Phage_ID IN ('{ids_str}')"
            result = retriever.get_phage_sequences(query)
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'query' or 'phage_ids' must be provided"
            )
        
        return {
            "success": True,
            "count": len(result),
            "sequences": result.to_dict(orient='records')
        }
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
            result = retriever.get_protein_sequences(
                request.query,
                limit=request.limit
            )
        elif request.protein_ids:
            # Build SQL query from IDs
            ids_str = "', '".join(request.protein_ids)
            query = f"SELECT Protein_ID FROM dim_proteins WHERE Protein_ID IN ('{ids_str}')"
            result = retriever.get_protein_sequences(query)
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'query' or 'protein_ids' must be provided"
            )
        
        return {
            "success": True,
            "count": len(result),
            "sequences": result.to_dict(orient='records')
        }
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
            result = retriever.get_phage_sequences(
                request.query,
                limit=request.limit
            )
        elif request.phage_ids:
            # Build SQL query from IDs
            ids_str = "', '".join(request.phage_ids)
            query = f"SELECT Phage_ID FROM fact_phages WHERE Phage_ID IN ('{ids_str}')"
            result = retriever.get_phage_sequences(query)
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'query' or 'phage_ids' must be provided"
            )
        
        # Convert to FASTA format
        fasta_lines = []
        for _, row in result.iterrows():
            fasta_lines.append(f">{row['id']}")
            fasta_lines.append(row['sequence'])
        
        return "\n".join(fasta_lines)
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
            result = retriever.get_protein_sequences(
                request.query,
                limit=request.limit
            )
        elif request.protein_ids:
            # Build SQL query from IDs
            ids_str = "', '".join(request.protein_ids)
            query = f"SELECT Protein_ID FROM dim_proteins WHERE Protein_ID IN ('{ids_str}')"
            result = retriever.get_protein_sequences(query)
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'query' or 'protein_ids' must be provided"
            )
        
        # Convert to FASTA format
        fasta_lines = []
        for _, row in result.iterrows():
            fasta_lines.append(f">{row['id']}")
            fasta_lines.append(row['sequence'])
        
        return "\n".join(fasta_lines)
    except Exception as e:
        logger.error(f"Error generating FASTA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

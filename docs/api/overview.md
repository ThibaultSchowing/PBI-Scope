# API Reference

> ⚠️ **UNTESTED** - The REST API is currently **untested** and is **not the recommended way** to interact with PBI data. For efficient data access and machine learning workflows, use the [analysis container](../guides/analysis-guide.md) with the `pbi` Python package directly (5-50x faster than API for bulk operations).

The PBI API provides a REST interface for querying the phage database and retrieving sequences programmatically. It may be useful for lightweight external integrations where only a few records need to be retrieved.

## Current Status

| Feature | Status | Notes |
|---------|--------|-------|
| Database Connection | Implemented | Connects to DuckDB database |
| Health Endpoints | Implemented | `/health` and `/stats` |
| SQL Query Endpoint | Implemented | `/query` with basic safety checks |
| Phage Retrieval | Implemented | Query and ID-based retrieval |
| Protein Retrieval | Implemented | Query and ID-based retrieval |
| FASTA Export | Implemented | Export sequences to FASTA format |
| **Testing** | ❌ **Not done** | API has not been validated |
| Authentication | Planned | No auth currently |
| Rate Limiting | Planned | Not yet implemented |
| Batch Operations | Planned | Bulk data operations |

## Quick Start

### Start the API (Docker)

```bash
# Build and start API
docker compose build api
docker compose up -d api

# API available at http://localhost:8000
```

### Start the API (Local)

```bash
# From project root
cd api
uvicorn app:app --host 0.0.0.0 --port 8000

# Or with auto-reload for development
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Base URL

```
http://localhost:8000
```

## Interactive Documentation

The API provides **auto-generated interactive documentation**:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

👉 **We recommend using the Swagger UI** for exploring and testing the API interactively.

## Endpoints

### Health & Status

#### `GET /`
API information and available endpoints.

**Response:**
```json
{
  "name": "PBI API",
  "version": "0.1.0",
  "status": "running",
  "endpoints": [...]
}
```

#### `GET /health`
Health check - verifies database connection.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected"
}
```

**Status Codes:**
- `200`: API and database are healthy
- `503`: Database connection failed

#### `GET /stats`
Database statistics.

**Response:**
```json
{
  "phages": 873718,
  "proteins": 43088582,
  "trna_tmrna": 702607,
  "terminators": 6462417,
  "anti_crispr": 307329,
  "virulent_factors": 41609,
  "transmembrane": 4020770
}
```

### Data Querying

#### `POST /query`
Execute custom SQL query against the database.

⚠️ **Warning**: Use with caution. In production, this should be restricted to read-only queries.

**Request Body:**
```json
{
  "query": "SELECT * FROM fact_phages LIMIT 10"
}
```

**Response:**
```json
{
  "data": [...],
  "row_count": 10
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT Source_DB, COUNT(*) as count FROM fact_phages GROUP BY Source_DB"}'
```

#### `POST /phages`
Retrieve phage sequences and metadata.

**Request Body (by query):**
```json
{
  "query": "SELECT Phage_ID FROM fact_phages WHERE Length > 100000",
  "limit": 10
}
```

**Request Body (by IDs):**
```json
{
  "phage_ids": ["NC_000866", "NC_001895", "NC_002014"]
}
```

**Response:**
```json
{
  "phages": [
    {
      "phage_id": "NC_000866",
      "sequence": "ATCG...",
      "length": 48502,
      "metadata": {...}
    }
  ],
  "count": 3
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/phages \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT Phage_ID FROM fact_phages WHERE Host LIKE '\''%Escherichia%'\'' LIMIT 5"}'
```

#### `POST /proteins`
Retrieve protein sequences and metadata.

**Request Body:**
```json
{
  "query": "SELECT Protein_ID FROM dim_proteins WHERE Phage_ID = 'NC_000866'",
  "limit": 100
}
```

**Response:**
```json
{
  "proteins": [
    {
      "protein_id": "protein_1",
      "sequence": "MKKL...",
      "metadata": {...}
    }
  ],
  "count": 100
}
```

### FASTA Export

#### `POST /phages/fasta`
Export phage sequences in FASTA format.

**Request Body:**
```json
{
  "query": "SELECT Phage_ID FROM fact_phages LIMIT 5"
}
```

**Response:** (text/plain)
```
>NC_000866 Phage description...
ATCGATCGATCG...
>NC_001895 Phage description...
GCTAGCTAGCTA...
```

**Example:**
```bash
curl -X POST http://localhost:8000/phages/fasta \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT Phage_ID FROM fact_phages WHERE Length > 100000 LIMIT 10"}' \
  > large_phages.fasta
```

#### `POST /proteins/fasta`
Export protein sequences in FASTA format.

**Request Body:**
```json
{
  "query": "SELECT Protein_ID FROM dim_proteins WHERE Phage_ID = 'NC_000866'"
}
```

**Response:** (text/plain)
```
>protein_1 Product description...
MKKLISTAPROTEIN...
>protein_2 Product description...
MVKLASTAPROT...
```

## Database Schema Reference

For API queries, you can access these tables:

### Fact Table
- `fact_phages` - Main phage metadata

### Dimension Tables
- `dim_proteins` - Protein annotations
- `dim_terminators` - Transcription terminators
- `dim_anti_crispr` - Anti-CRISPR proteins
- `dim_virulent_factors` - Virulence factors
- `dim_transmembrane_proteins` - Transmembrane predictions
- `dim_trna_tmrna` - tRNA/tmRNA features
- `dim_crispr_array` - CRISPR arrays
- `dim_antimicrobial_resistance_genes` - AMR genes

See the [Database Overview](../database/overview.md) for detailed schema information.

## Examples

### Get Phages by Host

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT Phage_ID, Host, Length FROM fact_phages WHERE Host LIKE '\''%Staphylococcus%'\'' LIMIT 10"
  }'
```

### Get Large Phages with Many Proteins

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT f.Phage_ID, f.Length, COUNT(p.Protein_ID) as protein_count FROM fact_phages f JOIN dim_proteins p ON f.Phage_ID = p.Phage_ID WHERE f.Length > 200000 GROUP BY f.Phage_ID, f.Length HAVING COUNT(p.Protein_ID) > 200 LIMIT 20"
  }'
```

### Export Specific Phages to FASTA

```bash
curl -X POST http://localhost:8000/phages/fasta \
  -H "Content-Type: application/json" \
  -d '{
    "phage_ids": ["NC_000866", "NC_001895"]
  }' > my_phages.fasta
```

## Error Handling

The API returns standard HTTP status codes:

- **200**: Success
- **400**: Bad Request (invalid query, missing parameters)
- **404**: Not Found (resource doesn't exist)
- **500**: Internal Server Error (database error, unexpected issue)
- **503**: Service Unavailable (database connection failed)

**Error Response Format:**
```json
{
  "error": "Error message here",
  "detail": "Additional details about the error"
}
```

## Limitations & Known Issues

**Current Limitations:**

1. **No Authentication**: API is open - not suitable for public deployment
2. **No Rate Limiting**: Can be overwhelmed by many requests
3. **Query Safety**: Custom SQL queries not fully sanitized
4. **No Pagination**: Large result sets may cause timeouts
5. **Limited Filtering**: Complex filters require custom SQL

**Planned Improvements:**

See the [Future Steps](../future-steps.md) page for planned enhancements including authentication, rate limiting, pagination, and more advanced features.

## Development

### Running in Development Mode

```bash
# With auto-reload
cd api
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# With custom database path
DATABASE_PATH=/path/to/database.duckdb uvicorn app:app --reload
```

### Environment Variables

```bash
# Database path
export DATABASE_PATH=/data/processed/databases/phage_database_optimized.duckdb

# Phage FASTA path
export PHAGE_FASTA=/data/processed/sequences/all_phages.fasta

# Protein FASTA path
export PROTEIN_FASTA=/data/processed/sequences/all_proteins.fasta

# API port
export PORT=8000
```

## Testing the API

### Using curl

```bash
# Health check
curl http://localhost:8000/health

# Get stats
curl http://localhost:8000/stats

# Query data
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT COUNT(*) FROM fact_phages"}'
```

### Using Python

```python
import requests

# Health check
response = requests.get('http://localhost:8000/health')
print(response.json())

# Get statistics
response = requests.get('http://localhost:8000/stats')
print(response.json())

# Query phages
response = requests.post(
    'http://localhost:8000/query',
    json={"query": "SELECT * FROM fact_phages LIMIT 5"}
)
print(response.json())
```

## Next Steps

- Explore the [interactive API docs](http://localhost:8000/docs)
- Review the [Database Schema](../database/overview.md)
- Read about [Docker deployment](../guides/docker-guide.md)
- Check the [Command Reference](../reference/commands.md)

## Support

For API issues or feature requests:
- Open an issue on [GitHub](https://github.com/ThibaultSchowing/PBI/issues)
- Check the [changelog](../changelog.md) for recent updates
- Review [known issues](https://github.com/ThibaultSchowing/PBI/issues?q=is%3Aissue+is%3Aopen+label%3Aapi)

---

**Remember**: This API is in active development. Features and endpoints may change. Always check the latest documentation at `/docs`.

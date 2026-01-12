# Docker Setup for PBI

This document explains how to use Docker to run the PBI (Phage-Bacteria Interaction) pipeline and API.

## Overview

The PBI project has been dockerized into two main components:

1. **Pipeline Container**: Runs the Snakemake workflow to download PhageScope data and create a DuckDB database
2. **API Container**: Serves a REST API to query the database

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (version 20.10 or later)
- [Docker Compose](https://docs.docker.com/compose/install/) (version 2.0 or later)
- At least 50GB of free disk space for the data
- 8GB+ RAM recommended

## Quick Start

### 1. Build the containers

```bash
docker-compose build
```

This will build both the pipeline and API containers. The build process may take 10-15 minutes.

### 2. Run the pipeline to create the database

```bash
docker-compose run --rm pipeline
```

**⚠️ Important**: This step can take 2-4 hours (depending on your internet connection and CPU) as it:
- Downloads all PhageScope metadata files (~2GB)
- Downloads FASTA files for sequences (~50GB)
- Processes and merges all data
- Creates the DuckDB database (~15GB)
- Generates validation reports
- Creates optimized database (~12GB)

**The database will not be queryable until this process completes.**

The data will be stored in a Docker volume named `pbi-data` and persists between container runs.

### 3. Start the API server

Once the pipeline has completed and the database is created, start the API:

```bash
docker-compose up -d api
```

The API will be available at http://localhost:8000

### 4. Access the API documentation

Open your browser and navigate to:
- **Interactive API docs (Swagger UI)**: http://localhost:8000/docs
- **Alternative docs (ReDoc)**: http://localhost:8000/redoc

## Usage Examples

### Using the API

#### Health Check
```bash
curl http://localhost:8000/health
```

#### Get Database Statistics
```bash
curl http://localhost:8000/stats
```

#### List Available Tables
```bash
curl http://localhost:8000/tables
```

#### Query Phages
```bash
# Get 10 phages
curl "http://localhost:8000/phages?limit=10"

# Filter by source database
curl "http://localhost:8000/phages?source_db=RefSeq&limit=10"

# Filter by length
curl "http://localhost:8000/phages?min_length=50000&max_length=100000&limit=10"

# Filter by host
curl "http://localhost:8000/phages?host=Escherichia&limit=10"
```

#### Get Specific Phage Information
```bash
curl http://localhost:8000/phages/NC_000866
```

#### Query Proteins
```bash
# Get proteins for a specific phage
curl "http://localhost:8000/proteins?phage_id=NC_000866&limit=10"

# Filter by molecular weight
curl "http://localhost:8000/proteins?min_molecular_weight=50000&limit=10"
```

#### Execute Custom SQL Queries
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT Phage_ID, Length, GC_content FROM fact_phages WHERE Length > 100000",
    "limit": 10
  }'
```

#### Get Data Sources
```bash
curl http://localhost:8000/sources
```

### Using Python Requests

```python
import requests
import json

# API base URL
BASE_URL = "http://localhost:8000"

# Get stats
response = requests.get(f"{BASE_URL}/stats")
stats = response.json()
print(json.dumps(stats, indent=2))

# Query phages
params = {
    "source_db": "RefSeq",
    "min_length": 50000,
    "limit": 10
}
response = requests.get(f"{BASE_URL}/phages", params=params)
phages = response.json()
print(f"Found {phages['count']} phages")

# Custom SQL query
query_data = {
    "sql": "SELECT Source_DB, COUNT(*) as count FROM fact_phages GROUP BY Source_DB",
    "limit": 100
}
response = requests.post(f"{BASE_URL}/query", json=query_data)
results = response.json()
print(json.dumps(results, indent=2))
```

## Docker Commands Reference

### Building

```bash
# Build all containers
docker-compose build

# Build only the pipeline container
docker-compose build pipeline

# Build only the API container
docker-compose build api

# Rebuild without cache
docker-compose build --no-cache
```

### Running

```bash
# Run the pipeline once
docker-compose run --rm pipeline

# Start the API in the background
docker-compose up -d api

# Start the API in the foreground (see logs)
docker-compose up api

# Stop the API
docker-compose down
```

### Managing Data

```bash
# View logs
docker-compose logs api
docker-compose logs -f api  # Follow logs

# List volumes
docker volume ls

# Inspect the data volume
docker volume inspect pbi_pbi-data

# Back up the data volume
docker run --rm -v pbi_pbi-data:/data -v $(pwd):/backup alpine tar czf /backup/pbi-data-backup.tar.gz -C /data .

# Restore the data volume
docker run --rm -v pbi_pbi-data:/data -v $(pwd):/backup alpine tar xzf /backup/pbi-data-backup.tar.gz -C /data

# Remove the data volume (WARNING: This deletes all data!)
docker-compose down -v
```

### Debugging

```bash
# Access the pipeline container shell
docker-compose run --rm pipeline bash

# Access the API container shell
docker-compose exec api bash

# View API logs
docker-compose logs -f api

# Restart the API
docker-compose restart api
```

## Architecture

### Pipeline Container

- **Base Image**: `mambaorg/micromamba:1.5.8` (conda/mamba package manager)
- **Purpose**: Execute Snakemake workflow to download and process PhageScope data
- **Key Components**:
  - Snakemake workflow engine
  - Python 3.10 with scientific packages (pandas, numpy, duckdb)
  - Data processing scripts
- **Volumes**: Writes to `/data` volume
- **Execution**: Typically run once or when data needs to be updated

### API Container

- **Base Image**: `python:3.10-slim`
- **Purpose**: Serve REST API for database queries
- **Key Components**:
  - FastAPI web framework
  - Uvicorn ASGI server
  - DuckDB for database queries
- **Volumes**: Read-only access to `/data` volume
- **Ports**: Exposes port 8000
- **Execution**: Runs continuously as a service

### Data Flow

```
PhageScope → Pipeline Container → DuckDB + FASTA files → API Container → REST API
```

## Environment Variables

### Pipeline Container

- `SNAKEMAKE_CORES`: Number of CPU cores to use (default: all)

### API Container

- `DB_PATH`: Path to DuckDB database (default: `/data/processed/databases/phage_database_optimized.duckdb`)
- `PHAGE_FASTA_PATH`: Path to phage FASTA file (default: `/data/processed/sequences/all_phages.fasta`)
- `PROTEIN_FASTA_PATH`: Path to protein FASTA file (default: `/data/processed/sequences/all_proteins.fasta`)

## API Endpoints

### General
- `GET /` - API information
- `GET /health` - Health check
- `GET /stats` - Database statistics

### Database
- `GET /tables` - List all tables
- `GET /tables/{table_name}/schema` - Get table schema
- `POST /query` - Execute custom SQL query
- `GET /sources` - List data sources

### Phages
- `GET /phages` - Query phages with filters (source_db, min_length, max_length, host, lifestyle)
- `GET /phages/{phage_id}` - Get specific phage information

### Proteins
- `GET /proteins` - Query proteins with filters (phage_id, min_molecular_weight, classification)

## Database Schema

The database follows a star schema design:

### Fact Table
- `fact_phages` - Main phage metadata (Phage_ID, Source_DB, Length, GC_content, Taxonomy, etc.)

### Dimension Tables
- `dim_proteins` - Protein annotations
- `dim_terminators` - Transcription terminators
- `dim_anti_crispr` - Anti-CRISPR proteins
- `dim_virulent_factors` - Virulence factors
- `dim_transmembrane_proteins` - Transmembrane proteins
- `dim_trna_tmrna` - tRNA and tmRNA genes
- `dim_antimicrobial_resistance_genes` - AMR genes
- `dim_crispr_arrays` - CRISPR arrays

### Views
- `phage_summary` - Summary statistics by source
- `phage_size_distribution` - Size distribution analysis
- `phage_complete_profile` - Complete phage profiles with all features
- `amr_gene_summary` - AMR gene statistics
- `crispr_array_summary` - CRISPR array statistics
- Additional analytical views

## Troubleshooting

### Pipeline fails to download data

**Problem**: Network timeouts or connection errors during data download

**Solution**:
```bash
# Increase timeout settings or retry the pipeline
docker-compose run --rm pipeline
```

### API returns "Database not found"

**Problem**: Pipeline hasn't been run yet or data volume is empty

**Solution**:
```bash
# Run the pipeline first
docker-compose run --rm pipeline
# Then start the API
docker-compose up -d api
```

### Out of disk space

**Problem**: Not enough space for downloaded data

**Solution**:
- Ensure you have at least 50GB free
- Clean up Docker images: `docker system prune -a`
- Check volume size: `docker system df -v`

### API is slow

**Problem**: Large queries taking too long

**Solution**:
- Use the `limit` parameter to restrict result size
- The database has indexes on key columns for performance
- Consider increasing container memory allocation

### Container won't start

**Problem**: Port 8000 already in use

**Solution**:
```bash
# Check what's using the port
lsof -i :8000
# Kill the process or change the port in docker-compose.yml
ports:
  - "8001:8000"  # Map to different host port
```

## Data Updates

To update the database with fresh data from PhageScope:

```bash
# Stop the API
docker-compose down

# Remove old data (optional, if you want a fresh start)
docker volume rm pbi_pbi-data

# Run pipeline to download fresh data
docker-compose run --rm pipeline

# Restart the API
docker-compose up -d api
```

## Security Considerations

1. **Read-only Database**: The API container has read-only access to the database
2. **Query Restrictions**: Only SELECT queries are allowed through the `/query` endpoint
3. **No Authentication**: Currently, the API has no authentication. For production use:
   - Add API key authentication
   - Use a reverse proxy (nginx) with SSL/TLS
   - Implement rate limiting
   - Restrict network access

## Performance Tips

1. **Use filters**: Always use query parameters to filter results instead of retrieving all data
2. **Set appropriate limits**: Use the `limit` parameter to control response size
3. **Use indexed columns**: Queries on Phage_ID, Source_DB, and Protein_ID are optimized
4. **Cache responses**: Consider caching frequently accessed data on the client side

## Support

For issues, questions, or contributions:
- GitHub Issues: [ThibaultSchowing/PBI](https://github.com/ThibaultSchowing/PBI/issues)
- Documentation: [GitHub Pages](https://thibaultschowing.github.io/PBI/)

## License

This project follows the license specified in the main PBI repository.

# Docker Guide

This guide explains how to run the PBI pipeline and API using Docker.

## 🐳 Overview

The PBI Docker setup consists of two main services:

1. **Pipeline Service**: Runs the Snakemake workflow to build the phage database
2. **API Service**: Provides a REST API for querying the database and retrieving sequences

Both services share a common data volume to ensure the API can access the database built by the pipeline.

## Prerequisites

- Docker (version 20.10 or later)
- Docker Compose (version 2.0 or later)
- At least 60 GB of free disk space
- At least 16 GB of RAM (32 GB recommended)
- Stable internet connection (for initial data download)

## Quick Start

### 1. Build and Run the Pipeline

First, build the Docker image and run the pipeline to create the database:

```bash
# Build the pipeline image
docker compose build pipeline

# Run the pipeline (takes 2-4 hours on first run)
docker compose run --rm pipeline
```

**What happens during this step:**
- Downloads ~50 GB of phage genomic data from PhageScope
- Extracts and processes data from 14+ databases
- Merges data using chunked processing to avoid memory issues
- Creates optimized DuckDB database (~15 GB)
- Generates indexed FASTA files (~100 GB)
- Produces HTML validation reports

**Output files** (stored in the `pbi-data` volume):
- `/data/processed/databases/phage_database_optimized.duckdb`
- `/data/processed/sequences/all_phages.fasta` (+ `.fai` index)
- `/data/processed/sequences/all_proteins.fasta` (+ `.fai` index)
- `/data/processed/reports/*.html` - Validation and statistics reports

### 2. Build and Start the API

Once the pipeline completes, build and start the API service:

```bash
# Build the API image
docker compose build api

# Start the API service (detached mode)
docker compose up -d api
```

The API will be available at `http://localhost:8000`

### 3. Test the API

```bash
# Check API health
curl http://localhost:8000/health

# Get database statistics
curl http://localhost:8000/stats

# Open interactive API documentation in browser
# http://localhost:8000/docs
```

## Common Operations

### View Logs

```bash
# Pipeline logs
docker compose logs pipeline

# API logs (follow in real-time)
docker compose logs -f api
```

### Stop/Restart Services

```bash
# Stop API
docker compose down

# Restart API
docker compose restart api
```

### Update the Database

To rebuild the database with updated data:

```bash
# Stop API if running
docker compose down

# Re-run pipeline
docker compose run --rm pipeline

# Restart API
docker compose up -d api
```

### Access Data and Reports

```bash
# Copy database to host
docker run --rm -v pbi-data:/data -v $(pwd):/backup alpine \
  cp /data/processed/databases/phage_database_optimized.duckdb /backup/

# Copy all reports to host
docker run --rm -v pbi-data:/data -v $(pwd):/backup alpine \
  cp -r /data/processed/reports /backup/

# List available data
docker run --rm -v pbi-data:/data alpine ls -lah /data/processed/
```

## Volume Management

The setup uses two Docker volumes:

### `pbi-data` Volume (~60-80 GB)
Stores all pipeline data:
- **Raw data**: `/data/raw/` - Downloaded archives and extracted files
- **Intermediate**: `/data/intermediate/` - Merged CSV and FASTA files
- **Processed**: `/data/processed/` - Final database, sequences, and reports

### `pbi-cache` Volume (~2-3 GB)
Stores Snakemake working directory:
- Conda environments (persists to avoid re-downloading)
- Workflow metadata
- Execution logs

**Important**: Both volumes persist even after containers are removed. This speeds up development and prevents data loss.

### Clean Up

```bash
# Remove everything (containers + volumes)
docker compose down -v

# Remove only cache (keeps database)
docker compose down
docker volume rm pbi-cache

# Clean up cache using the provided script
./cleanup_cache.sh
```

## Customization

### Adjust Resources

Edit `docker-compose.yml`:

```yaml
services:
  pipeline:
    cpus: '4'
    mem_limit: 16g
```

### Change API Port

Edit `docker-compose.yml`:

```yaml
services:
  api:
    ports:
      - "8080:8000"  # Change 8080 to your desired port
```

### Use Local Data Directory

Instead of Docker volumes, mount a local directory:

```yaml
services:
  pipeline:
    volumes:
      - ./data:/data  # Use local ./data directory
```

## Troubleshooting

### Pipeline Fails with "No space left on device"

- Check available disk space: `df -h`
- Clean up Docker: `docker system prune -a --volumes`
- Ensure at least 60 GB free space

### API Can't Connect to Database

**Error**: `Database not found`

**Solution**:
1. Ensure pipeline completed successfully
2. Check if database exists:
   ```bash
   docker run --rm -v pbi-data:/data alpine ls -lh /data/processed/databases/
   ```
3. If file doesn't exist, re-run the pipeline

### Pipeline Takes Too Long

- First run takes 2-4 hours (downloading ~50 GB)
- Subsequent runs only process changed data
- Use fewer cores if I/O bound: `docker compose run --rm pipeline snakemake --cores 2`

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Or change the port in docker-compose.yml
```

## Architecture

```
┌──────────────┐
│   Pipeline   │
│  (Snakemake) │
└──────┬───────┘
       │
       ├─> Downloads & processes data
       │
       ▼
┌─────────────────────────────┐
│   Shared Volume (pbi-data)  │
│                             │
│  /data/processed/           │
│    ├─ databases/            │
│    ├─ sequences/            │
│    └─ reports/              │
└──────────┬──────────────────┘
           │ (read-only)
           ▼
     ┌─────────┐
     │   API   │
     │ (FastAPI)│
     └─────────┘
```

## Next Steps

- Explore the [API documentation](../api/overview.md)
- Learn about the [database schema](../database/overview.md)
- See [API usage examples](../api/overview.md#examples)

For more detailed Docker information, see the [DOCKER.md](../../DOCKER.md) file in the repository root.

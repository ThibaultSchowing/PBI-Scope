# Docker Guide for PBI

This guide explains how to build and run the PBI (Phage Bioinformatics Interface) pipeline and API using Docker.

## Overview

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

### 1. Build the Pipeline Image

First, build the Docker image for the pipeline:

```bash
docker compose build pipeline
```

This will:
- Install Snakemake and conda dependencies
- Set up the workflow environment
- Prepare the workflow directory

### 2. Run the Pipeline to Build the Database

Run the pipeline to download data and build the database. This process can take 2-4 hours:

```bash
docker compose run --rm pipeline
```

The `--rm` flag automatically removes the container after completion.

**What happens during this step:**
- Downloads ~50 GB of phage genomic data from multiple sources
- Processes and merges data from 14+ databases
- Creates optimized DuckDB database
- Generates indexed FASTA files for sequences
- Produces validation reports

**Output files** (stored in the `pbi-data` volume):
- `/data/processed/databases/phage_database_optimized.duckdb`
- `/data/processed/sequences/all_phages.fasta` (+ `.fai` index)
- `/data/processed/sequences/all_proteins.fasta` (+ `.fai` index)

**Cache files** (stored in the `pbi-cache` volume):
- Snakemake metadata and workflow state
- Conda environments (~2 GB)
- This volume persists across runs, so failed pipeline runs don't require re-downloading dependencies

### 3. Build the API Image

Once the pipeline completes successfully, build the API image:

```bash
docker compose build api
```

### 4. Start the API Service

Start the API service to query the database:

```bash
docker compose up api
```

Or run in detached mode:

```bash
docker compose up -d api
```

The API will be available at `http://localhost:8000`

### 5. Test the API

Once the API is running, test it:

```bash
# Check API health
curl http://localhost:8000/health

# Get database statistics
curl http://localhost:8000/stats

# Get API documentation (OpenAPI/Swagger)
# Open in browser: http://localhost:8000/docs
```

## API Endpoints

The PBI API provides the following endpoints:

### Health & Status

- `GET /` - API information and available endpoints
- `GET /health` - Health check (returns 200 if database is connected)
- `GET /stats` - Database statistics (phage count, protein count, etc.)

### Querying Data

- `POST /query` - Execute custom SQL query
  ```bash
  curl -X POST http://localhost:8000/query \
    -H "Content-Type: application/json" \
    -d '{"query": "SELECT * FROM fact_phages LIMIT 10"}'
  ```

- `POST /phages` - Retrieve phage sequences
  ```bash
  # By SQL query
  curl -X POST http://localhost:8000/phages \
    -H "Content-Type: application/json" \
    -d '{"query": "SELECT Phage_ID FROM fact_phages WHERE Length > 100000", "limit": 10}'
  
  # By IDs
  curl -X POST http://localhost:8000/phages \
    -H "Content-Type: application/json" \
    -d '{"phage_ids": ["NC_000866", "NC_001895"]}'
  ```

- `POST /proteins` - Retrieve protein sequences
  ```bash
  curl -X POST http://localhost:8000/proteins \
    -H "Content-Type: application/json" \
    -d '{"query": "SELECT Protein_ID FROM dim_proteins LIMIT 5"}'
  ```

### FASTA Export

- `POST /phages/fasta` - Get phage sequences in FASTA format
- `POST /proteins/fasta` - Get protein sequences in FASTA format

```bash
curl -X POST http://localhost:8000/phages/fasta \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT Phage_ID FROM fact_phages LIMIT 5"}' \
  > phages.fasta
```

### Interactive API Documentation

Visit `http://localhost:8000/docs` in your browser for interactive API documentation (Swagger UI).

## Common Operations

### View Pipeline Logs

```bash
docker compose logs pipeline
```

### View API Logs

```bash
docker compose logs api
```

### Follow API Logs in Real-time

```bash
docker compose logs -f api
```

### Stop the API

```bash
docker compose down
```

### Restart the API

```bash
docker compose restart api
```

### Re-run the Pipeline (Update Database)

To rebuild the database with updated data:

```bash
# Stop API if running
docker compose down

# Re-run pipeline
docker compose run --rm pipeline

# Restart API
docker compose up -d api
```

### Access the Data Volume

To inspect or backup the data:

```bash
# List database contents
docker run --rm -v pbi-data:/data alpine ls -lah /data/processed/databases

# List cache contents
docker run --rm -v pbi-cache:/cache alpine ls -lah /cache

# Copy database to host
docker run --rm -v pbi-data:/data -v $(pwd):/backup alpine \
  cp /data/processed/databases/phage_database_optimized.duckdb /backup/
```

### Clean Up Everything

To remove containers, volumes, and images:

```bash
# Stop all services
docker compose down

# Remove volumes (WARNING: deletes all data!)
docker compose down -v

# Remove images
docker rmi pbi-pipeline pbi-api
```

### Clean Cache Only

To remove only the cache volume (Snakemake metadata and conda environments) while keeping the database:

```bash
# Stop all services
docker compose down

# Remove only the cache volume
docker volume rm pbi-cache

# Next run will rebuild conda environments but reuse existing data
docker compose run --rm pipeline
```

This is useful when you want to:
- Free up disk space (~2 GB)
- Force a clean rebuild of conda environments
- Troubleshoot environment-related issues

**Note**: The cache volume persists across container runs to speed up development. After a failed pipeline run, the cache remains intact, so the next run doesn't need to re-download conda packages or rebuild environments.

## Customization

### Adjust Pipeline Resources

Edit the `docker-compose.yml` file to limit resources:

```yaml
services:
  pipeline:
    # ... existing config ...
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

### Mount Local Data Directory

To use a local directory instead of a Docker volume:

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
- Clean up cache volume only: `docker volume rm pbi-cache`
- Ensure at least 60 GB free space

### API Can't Connect to Database

**Error**: `Database not found: /data/processed/databases/phage_database_optimized.duckdb`

**Solution**:
1. Ensure pipeline completed successfully
2. Check if database file exists in volume:
   ```bash
   docker run --rm -v pbi-data:/data alpine ls -lh /data/processed/databases/
   ```
3. If file doesn't exist, re-run the pipeline

### Pipeline Takes Too Long

- First run typically takes 2-4 hours due to data download
- Subsequent runs are faster (only processes changed data)
- Use `--cores` flag to adjust parallelism:
  ```bash
  docker compose run --rm pipeline snakemake --cores 2 --use-conda --printshellcmds
  ```

### API Startup is Slow

- FASTA file indexing may take 30-60 seconds on first startup
- This is normal for large files
- Check logs: `docker compose logs api`

### Port Already in Use

If port 8000 is already in use:

```bash
# Find process using port
lsof -i :8000

# Or change the port in docker-compose.yml
```

## Architecture Details

### Data Flow

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
│    │   └─ phage_database... │
│    └─ sequences/            │
│        ├─ all_phages.fasta  │
│        └─ all_proteins...   │
└──────────┬──────────────────┘
           │ (read-only)
           ▼
     ┌─────────┐
     │   API   │
     │ (FastAPI)│
     └─────────┘
```

### Volume Management

The `pbi-data` volume is created automatically and persists data between container restarts. This ensures:
- Database is built once and reused
- No need to rebuild when restarting API
- Data survives container removal

The `pbi-cache` volume is also created automatically and persists Snakemake's working directory. This ensures:
- Conda environments are preserved across runs (~2 GB)
- Failed pipeline runs don't require re-downloading dependencies
- Workflow metadata and logs are retained
- Faster iteration during development and debugging

**Important**: Both volumes persist even when containers are removed with `--rm`. This is intentional to speed up development. Clean them manually when needed (see "Clean Up" sections).

## Development

### Mount Source Code for Development

For live code updates without rebuilding:

```yaml
services:
  api:
    volumes:
      - pbi-data:/data:ro
      - ./api:/app/api  # Mount API source
      - ./src:/app/src  # Mount PBI package
    command: uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Run Pipeline with Custom Snakefile

```bash
docker compose run --rm pipeline snakemake --cores 4 --use-conda --snakefile /app/workflow/Snakefile
```

## Performance Considerations

- **Pipeline**: Use 2-4 cores for first run (I/O bound), more cores for subsequent runs
- **API**: Stateless and lightweight, can handle multiple concurrent requests
- **Database**: DuckDB is optimized for analytical queries, reads are fast
- **FASTA**: Indexed with pyfaidx for O(1) random access

## Security Notes

- API runs in read-only mode for data safety
- Consider adding authentication for production use
- Limit SQL query capabilities in production
- Use environment variables for sensitive configuration

## Next Steps

- Explore the interactive API documentation at `/docs`
- Query the database using the `/query` endpoint
- Export sequences in FASTA format
- Integrate API calls into your bioinformatics workflows

For more information about the PBI project, see the main README.md.

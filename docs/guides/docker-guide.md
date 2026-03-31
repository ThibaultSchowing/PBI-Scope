# Docker Guide for PBI

This guide explains how to build and run the PBI (Phage Bioinformatics Interface) pipeline and API using Docker.

## Overview

The PBI Docker setup provides a containerized environment with three specialized services that work together:

### Services

1. **Pipeline Service** (`pbi-pipeline`)
   - Executes the Snakemake workflow to download and process data
   - Builds the DuckDB database from 14+ phage data sources
   - Generates indexed FASTA files and validation reports
   - Runs once to create the database, then can be rerun for updates

2. **API Service** (`pbi-api`) — ⚠️ *Work In Progress*
   - Provides REST API endpoints for database queries
   - Returns data in JSON and FASTA formats
   - **Not yet updated for host management** — host endpoints are not available
   - Interactive API documentation at `/docs` (once running)
   - See the [API documentation](../api/overview.md) for current status

3. **Analysis Service** (`pbi-analysis`)
   - Jupyter Lab environment for direct data access
   - Pre-installed `pbi` Python package and scientific libraries
   - 5-50x faster than API for bulk operations
   - Ideal for data exploration and machine learning

### Data Persistence

Two Docker volumes ensure data persistence:

- **`pbi-data`**: Stores all pipeline outputs (database, sequences, reports) - ~202 GB
- **`pbi-cache`**: Stores Snakemake metadata and conda environments - ~18 GB

All services share read-only access to the `pbi-data` volume, while only the pipeline can write to it.

## Prerequisites

- Docker (version 20.10 or later)
- Docker Compose (version 2.0 or later)
- At least 60 GB of free disk space
- At least 16 GB of RAM (32 GB recommended)
- Stable internet connection (for initial data download)

## Migration Guide for Existing Users

If you're upgrading from a previous version of PBI that used relative paths and the old cache configuration, follow these steps to migrate:

### Step 1: Stop All Containers

```bash
docker compose down
```

### Step 2: Clear Corrupted Metadata (Optional but Recommended)

The cache structure has changed, so it's best to clear the old metadata while preserving your downloaded data:

```bash
# Clear the cache volume (preserves data files in pbi-data volume)
docker run --rm -v pbi-cache:/cache alpine rm -rf /cache/*
```

**Note**: This only removes Snakemake metadata and conda environments (~2 GB), not your downloaded data files (~50 GB).

### Step 3: Pull Latest Changes

```bash
git pull origin main
```

### Step 4: Rebuild Images

Due to changes in the Dockerfile and workflow configuration, you must rebuild with the `--no-cache` flag:

```bash
docker compose build --no-cache pipeline
```

### Step 5: Verify Volume Mounts

The new configuration uses:
- `/data` for all data files (raw, intermediate, processed)
- `/cache` for Snakemake metadata and conda environments

Check your `docker-compose.yml` to ensure it matches the new structure (see Quick Start section).

### Step 6: Run the Pipeline

```bash
docker compose run --rm pipeline
```

**Expected behavior**:
- First run: Downloads data to `/data/raw/*_compressed/` (will take ~4 hours for phage data, ~12–18 hours for host genomes)
- Extracted files in `/data/raw/*_extracted/` are temporary and removed after merging
- Downloaded archives persist and won't be re-downloaded on subsequent runs
- Subsequent runs: "Nothing to be done (all requested files are present and up to date)"

### Step 7: Verify Data Persistence

After the pipeline completes, verify downloaded files persist in the volume:

```bash
# Check compressed archives (should persist)
docker run --rm -v pbi-data:/data alpine ls -lh /data/raw/protein_fasta_compressed/

# Check cache (should contain conda environments)
docker run --rm -v pbi-cache:/cache alpine ls -lh /cache/conda/
```

### Troubleshooting Migration Issues

**Issue**: "Missing output files" warnings during first run after migration

**Solution**: This is expected if you cleared the cache. Snakemake will detect existing files and skip re-downloading them.

**Issue**: Pipeline re-downloads all data despite existing files

**Solution**: 
1. Verify paths in `workflow/config/config.yaml` use absolute paths (e.g., `/data/raw/...`)
2. Ensure `temp()` is removed from download rules in `workflow/rules/phagescope.smk`
3. Check that volumes are mounted correctly in `docker-compose.yml`

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

Run the pipeline to download data and build the database. This process can take **~4 hours** for the phage metadata, and **~12–18 hours** for the host resolution and download. 

```bash
docker compose run --rm pipeline
```

The `--rm` flag automatically removes the container after completion.

**What happens during this step:**
- Downloads ~50 GB of phage genomic data from multiple sources to `/data/raw/`
- Extracts and processes data to `/data/intermediate/`
- Merges data from 14+ databases using chunked processing to avoid out-of-memory errors
- Creates optimized DuckDB database in `/data/processed/databases/`
- Generates indexed FASTA files for sequences in `/data/processed/sequences/`
- Produces validation reports in `workflow/reports/`

**Output files** (stored in the `pbi-data` volume):
- `/data/processed/databases/phage_database_optimized.duckdb`
- `/data/processed/sequences/all_phages.fasta` (+ `.fai` index)
- `/data/processed/sequences/all_proteins.fasta` (+ `.fai` index)
- `/data/processed/reports/` - HTML reports for data validation and statistics

**Cache files** (stored in the `pbi-cache` volume):
- Snakemake metadata and workflow state in `/cache/metadata/`
- Conda environments (~2 GB) in `/cache/conda/`
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

**IMPORTANT**: The API needs time to load the big amount of files. Check the status with

```bash
docker compose logs api
```

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

### 6. (Optional) Start the Analysis Service

For efficient bulk data analysis without API overhead, use the analysis service:

```bash
# Build the analysis container
docker compose build analysis

# Start Jupyter Lab
docker compose up -d analysis
```

The Jupyter Lab interface will be available at `http://localhost:8888`

**⚠️ Security Warning**: Jupyter Lab runs **without authentication** for local development convenience. This configuration is **not suitable for production** or network-exposed deployments.

**Security Recommendations:**
- **Local Development**: Only access via `http://localhost:8888` on the host machine
- **Remote Access**: Use SSH tunneling instead of exposing the port:
  ```bash
  # On your local machine
  ssh -L 8888:localhost:8888 user@remote-server
  # Then access http://localhost:8888 in your local browser
  ```
- **Production Use**: Either:
  - Set `restart: "no"` in docker-compose.yml and only start manually when needed
  - Configure Jupyter authentication by modifying the Dockerfile
  - Use a reverse proxy with authentication (e.g., nginx with basic auth)

**Key Features:**
- **Direct database access** - 5-50x faster than API for bulk operations
- **Read-only access** - Safe access to production data
- **Pre-installed tools** - DuckDB, pandas, matplotlib, seaborn, BioPython
- **Persistent notebooks** - Stored in `./notebooks` directory

**Quick Test:**

Open your browser to `http://localhost:8888` and navigate to `notebooks/analysis_direct_access_guide.ipynb` for a complete guide with examples.

See the [Analysis Guide](analysis-guide.md) for detailed usage instructions and best practices.

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

For detailed information about the database schema, tables, and relationships, see the [Database Overview](../database/overview.md) and [API Reference](../api/overview.md).

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

# List reports
docker run --rm -v pbi-data:/data alpine ls -lah /data/processed/reports

# List cache contents
docker run --rm -v pbi-cache:/cache alpine ls -lah /cache

# Copy database to host
docker run --rm -v pbi-data:/data -v $(pwd):/backup alpine \
  cp /data/processed/databases/phage_database_optimized.duckdb /backup/

# Copy reports to host
docker run --rm -v pbi-data:/data -v $(pwd):/backup alpine \
  cp -r /data/processed/reports /backup/
  
# View a specific report (copy to current directory)
docker run --rm -v pbi-data:/data -v $(pwd):/backup alpine \
  cp /data/processed/reports/database_validation.html /backup/
```

### Create a temporary container to access the data
 ```bash
 # Similar as above : This creates a container named extractor that maps your volume to /data. 
 # We use docker create instead of run so it doesn't try to execute anything.

 docker create --name extractor -v pbi_pbi-data:/data alpine

 # Copy the file(s) to your current directory
 # Replace filename.db with the actual name of the file you saw in your ls command.
 # You can also copy directories
 
 docker cp extractor:/data/processed/databases/filename.db ./filename.db

# Remove the temporary container
# Clean up the container once the copy is finished.

docker rm extractor
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

**Option 1: Using the cleanup script (recommended)**

```bash
./cleanup_cache.sh
```

The script will:
- Check if the cache volume exists
- Warn you if containers are using it
- Prompt for confirmation before deletion
- Provide next steps after cleanup

**Option 2: Manual cleanup**

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
- Ensure that you have enough free space

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

- First run typically takes ~4 hours for phage data, plus ~12–18 hours for host genome downloads
- Subsequent runs are faster (only processes changed data)
- Use `--cores` flag to adjust parallelism (caution ! More than 4 cores can reach your I/O limit on a laptop):
  ```bash
  docker compose run --rm pipeline snakemake --cores 4 --use-conda --printshellcmds
  ```

### API Startup is Slow

- FASTA file indexing may take up to 5 minutes on first startup
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
           ├────────────┐
           ▼            ▼
     ┌─────────┐  ┌──────────┐
     │   API   │  │ Analysis │
     │(FastAPI)│  │ (Jupyter)│
     └─────────┘  └──────────┘
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

### Data Storage Organization

The pipeline organizes data into three distinct categories, all stored in the `pbi-data` volume:

#### 1. Raw Data (`/data/raw/`)
Downloaded directly from external sources without modification. This includes:
- **Compressed FASTA files**: `/data/raw/protein_fasta_compressed/` and `/data/raw/phage_fasta_compressed/`
  - Downloaded `.tar.gz` archives from PhageScope API
  - ~50 GB of compressed genomic data
- **Extracted FASTA files**: `/data/raw/protein_fasta_extracted/` and `/data/raw/phage_fasta_extracted/`
  - Individual FASTA files extracted from archives
  - Used as input for merging operations

#### 2. Intermediate Data (`/data/intermediate/`)
Temporary processing files that are used to build the final outputs:
- **CSV metadata files**: `/data/intermediate/csv/`
  - Downloaded TSV files for each feature (phage metadata, protein annotations, etc.)
  - Individual files per database source
- **Merged CSV files**: `/data/intermediate/csv/merged/`
  - Consolidated metadata from all sources
  - Used to populate the DuckDB database
- **Merged FASTA files by source**: `/data/intermediate/fasta/phages/` and `/data/intermediate/fasta/proteins/`
  - One FASTA file per database (RefSeq, GenBank, MGV, etc.)
  - Intermediate step before final concatenation

#### 3. Processed Data (`/data/processed/`)
Final, optimized outputs ready for use:
- **Databases**: `/data/processed/databases/`
  - `phage_database_optimized.duckdb` - Main queryable database (~10-20 GB)
- **Sequences**: `/data/processed/sequences/`
  - `all_phages.fasta` + `.fai` index - Complete phage genome sequences
  - `all_proteins.fasta` + `.fai` index - Complete protein sequences
  - Indexed for fast random access
- **Reports**: `/data/processed/reports/`
  - HTML reports for data validation and metadata statistics
  - `database_validation.html` - Database structure and quality validation
  - `*_metadata_report.html` - Reports for each data type (phage, proteins, etc.)

#### Cache Volume (`pbi-cache`)
Separate from the data volume, the cache stores Snakemake's working directory:
- **Location**: `/cache` (inside container)
- **Contents**:
  - Conda environments (~2 GB) - Persist across runs to avoid re-downloading packages
  - Workflow metadata - Tracks which steps completed successfully
  - Log files - Detailed execution logs
  
**Note**: The corrupted metadata warnings shown in the problem statement occur when:
- Pipeline is interrupted mid-execution
- Snakemake metadata becomes inconsistent
- Solution: These warnings are harmless and can be ignored. Snakemake will rebuild affected files.

#### Volume Storage Summary

```
Docker Volumes:
├─ pbi-data (main data volume, ~60-80 GB)
│  ├─ /data/raw/              # Downloaded archives and extracted files
│  ├─ /data/intermediate/     # Processing artifacts and merged files
│  └─ /data/processed/        # Final database and sequences (API uses this)
│
└─ pbi-cache (Snakemake cache, ~2-3 GB)
   └─ /cache/  # Conda envs, metadata, logs
```

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
- Analysis service has read-only access to data via `:ro` mount
- Consider adding authentication for production use
- Limit SQL query capabilities in production
- Use environment variables for sensitive configuration

## Analysis Service Deep Dive

The Analysis service provides a powerful alternative to the REST API for bulk data operations, offering direct database and file system access through Jupyter Lab.

### Why Use the Analysis Service?

**Performance Benefits:**
- **5-50x faster** than API for bulk operations
- **No network overhead** - direct file system access
- **Batch processing** - handle millions of records efficiently
- **Memory-efficient** - stream large datasets without loading into RAM

**Use Cases:**
- Analyzing large datasets (>10,000 records)
- Complex SQL queries with multi-table joins
- Exporting bulk data (Parquet, CSV)
- Machine learning dataset preparation
- Exploratory data analysis
- Interactive visualization

### Getting Started with Analysis Service

1. **Start the service:**
   ```bash
   docker compose up -d analysis
   ```

2. **Access Jupyter Lab:**
   - Open http://localhost:8888 in your browser
   - No password required (local development setup)

3. **Open the example notebook:**
   - Navigate to `notebooks/analysis_direct_access_guide.ipynb`
   - Follow the complete guide with examples

### Key Features

**Pre-installed Scientific Stack:**
- DuckDB for database access
- pyfaidx for sequence retrieval
- pandas, numpy for data manipulation
- matplotlib, seaborn for visualization
- BioPython for bioinformatics operations
- pyarrow for efficient data exports

**Persistent Storage:**
- Notebooks saved in `./notebooks` directory
- Exports saved in `/workspace/exports`
- Work persists across container restarts

**Safe Read-Only Access:**
- Volume mounted with `:ro` flag
- Cannot modify production data
- Prevents accidental corruption

### Quick Examples

**Direct DuckDB Query:**
```python
import duckdb

conn = duckdb.connect(
    "/data/processed/databases/phage_database_optimized.duckdb",
    read_only=True
)

# Fast metadata retrieval
df = conn.execute("""
    SELECT Phage_ID, Length, GC_Content
    FROM fact_phages
    WHERE Length > 100000
    LIMIT 10
""").fetchdf()

conn.close()
```

**Batch Sequence Retrieval:**
```python
from pbi import SequenceRetriever

retriever = SequenceRetriever(
    db_path="/data/processed/databases/phage_database_optimized.duckdb",
    phage_fasta_path="/data/processed/sequences/all_phages.fasta",
    protein_fasta_path="/data/processed/sequences/all_proteins.fasta"
)

# Get sequences for multiple phages
sequences = retriever.get_sequences_by_ids(
    ['NC_000866', 'NC_001895'],
    sequence_type='phage'
)
```

**Export to Parquet:**
```python
import duckdb

conn = duckdb.connect(
    "/data/processed/databases/phage_database_optimized.duckdb",
    read_only=True
)

# Efficient export without loading into memory
conn.execute("""
    COPY (
        SELECT * FROM fact_phages
        WHERE Length > 50000
    ) TO '/workspace/exports/large_phages.parquet'
    (FORMAT PARQUET)
""")

conn.close()
```

### Best Practices for Analysis Service

1. **Always use read-only connections:**
   ```python
   conn = duckdb.connect(db_path, read_only=True)
   ```

2. **Process data in batches:**
   ```python
   BATCH_SIZE = 1000
   for offset in range(0, total, BATCH_SIZE):
       batch = conn.execute(f"... LIMIT {BATCH_SIZE} OFFSET {offset}").fetchdf()
   ```

3. **Use native export functions:**
   ```python
   conn.execute("COPY (...) TO 'file.parquet'")
   ```

4. **Close connections:**
   ```python
   try:
       conn = duckdb.connect(db_path, read_only=True)
       # work...
   finally:
       conn.close()
   ```

### Troubleshooting Analysis Service

**Jupyter Lab not accessible:**
```bash
# Check if container is running
docker ps | grep pbi-analysis

# Check logs
docker logs pbi-analysis

# Restart
docker compose restart analysis
```

**Database locked error:**
- Ensure `read_only=True` in connection
- Check that volume is mounted as `:ro`

**Out of memory:**
- Reduce batch size
- Use DuckDB aggregations instead of loading all data
- Stream results to disk with `COPY`

### Performance Comparison: API vs Analysis

The following table shows **representative performance metrics** based on typical operations. Actual performance may vary depending on hardware, data size, and query complexity:

| Operation | API | Analysis | Speedup |
|-----------|-----|----------|---------|
| Query 10K records | ~2s | ~0.1s | 20x |
| Export 100K records | ~30s | ~1s | 30x |
| Complex join | Not feasible | ~0.5s | N/A |
| Sequence retrieval (1000) | ~10s | ~1s | 10x |

**Note**: These are estimates to illustrate the order-of-magnitude improvements. For your specific use case, run the performance comparison section in `analysis_direct_access_guide.ipynb` to measure actual performance.

For detailed usage, examples, and best practices, see the [Analysis Guide](analysis-guide.md).

## Next Steps

- Explore the interactive API documentation at `/docs`
- Query the database using the `/query` endpoint
- Export sequences in FASTA format
- Integrate API calls into your bioinformatics workflows

For more information about the PBI project, see the main README.md.

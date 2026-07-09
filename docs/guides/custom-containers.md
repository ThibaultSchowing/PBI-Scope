# Building Custom Containers

This guide explains how to create your own Docker container connected to the PBI-Scope database. You can use any language (R, Python, Julia, Rust, etc.) and any workflow (Jupyter, scripts, both).

!!! info "Source Files"
    All example files are in the [`mount_scripts/`](https://github.com/ThibaultSchowing/PBI/tree/main/mount_scripts) directory at the repository root. The Dockerfile and scripts contain extensive comments explaining each section.

---

## How Docker Volumes Work

PBI-Scope stores all processed data (database, sequences, indexes) in a **named Docker volume** called `pbi-data`. This volume is created when you first run the pipeline.

```
pbi-data (Docker volume)
├── databases/
│   └── phage_database_optimized.duckdb
├── sequences/
│   ├── all_phages.fasta (+.fai index)
│   ├── all_proteins.fasta (+.fai index)
│   └── host_fasta_mapping.json
└── intermediate/
    └── ...
```

**Key concepts:**

| Concept | Description |
|---------|-------------|
| **Named volume** | Persists data across container restarts. Created by `docker compose up pipeline`. |
| **Bind mount** | Maps a host directory into the container (e.g., `./notebooks:/workspace`). |
| **`DATA_PATH`** | Environment variable set to `/data/processed`. The `pbi` package uses this to find the database. |
| **Read-only** | Containers mount the data volume as read-only (`:ro`) to prevent accidental modifications. |

**Your custom container connects to this volume:**

```yaml
# In your docker-compose.custom.yml
volumes:
  - pbi-data:/data:ro  # Mount the PBI-Scope data volume
```

---

## Quick Start: R + Python Container

The [`mount_scripts/`](https://github.com/ThibaultSchowing/PBI/tree/main/mount_scripts) directory contains a complete working example.

### Step 1: Build the Container

```bash
cd mount_scripts/
docker compose -f docker-compose.custom.yml build
```

### Step 2: Choose a Mode

**Option A: Jupyter Lab** (interactive exploration)

```bash
docker compose -f docker-compose.custom.yml up custom-jupyter
# Open http://localhost:8888 in your browser
```

**Option B: Run Script** (batch processing, long-running tasks)

```bash
docker compose -f docker-compose.custom.yml up custom-scripts
# Plots are saved to ./output/
```

### Step 3: Access Your Work

- **Notebooks**: Edit files in `mount_scripts/` on your host — they appear in `/workspace` inside the container
- **Outputs**: Plots are saved to `mount_scripts/output/` on your host

---

## Understanding the Dockerfile

The example Dockerfile (`mount_scripts/Dockerfile`) builds an R + Python container. Here are the key concepts:

### Base Image

```dockerfile
FROM rocker/r-ver:4.3.2
```

| Base Image | Language | Use Case |
|------------|----------|----------|
| `rocker/r-ver` | R first | R-focused analysis, add Python as needed |
| `python:3.10-slim` | Python first | Python-focused analysis, add R as needed |
| `jupyter/r-notebook` | Both | Pre-configured Jupyter with R kernel |
| `rocker/rstudio` | R first | RStudio Server (port 8787) instead of Jupyter |
| `ubuntu:22.04` | Minimal | Install everything yourself (most control) |

### Installing Packages

**R packages:**

```dockerfile
RUN R -e 'install.packages(c(
    "DBI", "duckdb",      # Database connection
    "dplyr", "tidyr",     # Data manipulation
    "ggplot2", "scales",  # Visualization
    "IRkernel"            # Jupyter R kernel
), repos = "https://cloud.r-project.org")'
```

**Python packages:**

```dockerfile
RUN pip3 install --no-cache-dir \
    pbi \                 # PBI-Scope Python package
    duckdb \
    pandas \
    matplotlib \
    seaborn \
    jupyterlab
```

**System dependencies:**

```dockerfile
RUN apt-get update && apt-get install -y \
    libcurl4-openssl-dev \  # Required by some R packages
    libssl-dev \
    libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
```

### The Entrypoint

```dockerfile
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["jupyter"]
```

The entrypoint script controls what the container does. See [Understanding the Entrypoint](#understanding-the-entrypoint) below.

---

## Understanding the Entrypoint

The entrypoint script (`mount_scripts/entrypoint.sh`) handles two things:

### 1. /etc/passwd Patching

When running as a non-root user (via `docker-compose user:`), the container may not have an entry in `/etc/passwd`. This causes Python's `getpass.getuser()` to crash. The entrypoint adds a temporary entry:

```bash
CURRENT_UID=$(id -u)
if ! getent passwd "${CURRENT_UID}" > /dev/null 2>&1; then
    echo "jupyter:x:${CURRENT_UID}:${CURRENT_GID}:Jupyter user:${HOME}:/bin/sh" \
        >> /etc/passwd 2>/dev/null || true
fi
```

### 2. Mode Switching

The entrypoint reads the first argument (`MODE`) and decides what to run:

```bash
MODE="${1:-jupyter}"

case "${MODE}" in
    jupyter)
        exec jupyter lab --ip=0.0.0.0 --port=8888 ...
        ;;
    script)
        Rscript explore_phages.R
        ;;
    bash)
        exec /bin/bash
        ;;
esac
```

**Usage:**

```bash
# Jupyter mode (default)
docker compose -f docker-compose.custom.yml up custom-jupyter

# Script mode
docker compose -f docker-compose.custom.yml up custom-scripts

# Bash mode (for debugging)
docker compose -f docker-compose.custom.yml run custom-jupyter bash
```

---

## Running Scripts vs Jupyter

### When to Use Scripts

- **Long-running analyses** (hours or days)
- **Automated pipelines** (no human interaction needed)
- **Batch processing** (run the same analysis on multiple datasets)
- **Reproducibility** (scripts are version-controlled, notebooks can have hidden state)

**Example: Run an R script**

```bash
# Run the exploration script
docker compose -f docker-compose.custom.yml up custom-scripts

# Check the output
ls output/
# 01_source_distribution.png
# 02_length_distribution.png
# ...
```

### When to Use Jupyter

- **Interactive exploration** (try different queries, see results immediately)
- **Visualization** (render plots inline)
- **Teaching** (mix code, explanations, and outputs)
- **Prototyping** (develop analysis before converting to script)

**Example: Start Jupyter Lab**

```bash
docker compose -f docker-compose.custom.yml up custom-jupyter
# Open http://localhost:8888
# Select Python 3 or R kernel from the launcher
```

### Converting Between Modes

**From notebook to script:**

```bash
# Export notebook to R script
jupyter nbconvert --to script explore_phages.ipynb

# Or export to Python script
jupyter nbconvert --to python explore_phages.ipynb
```

**From script to notebook:**

```bash
# Convert R script to notebook (using knitr)
Rscript -e 'knitr::knit2html("explore_phages.R")'

# Or manually create a notebook and copy the code cells
```

---

## Querying the API from Custom Containers

You can query the PBI-Scope API from within your custom container without loading the database directly. The API runs as a separate service on the same Docker network and can be reached via `http://pbi-api:8000`.

### When to Use the API

| Feature | API | Direct Database Access |
|---------|-----|------------------------|
| Setup | No local DB needed | Requires `pbi-data` volume |
| Speed | Network latency | Direct file read |
| Bulk downloads | Not supported | Recommended |
| ML streaming | Not supported | Required |
| Shared access | Multiple containers | Single instance |
| SQL queries | Supported | Supported |

!!! note "Read-only access"
    The API provides **read-only** access to the database. All queries are validated and restricted to SELECT statements. This makes it safe for shared environments where multiple users or containers need concurrent access.

### Starting the API

```bash
# Option 1: Start from the main docker-compose.yml
docker compose up api

# Option 2: Start from the custom docker-compose.yml
docker compose -f docker-compose.custom.yml up api

# Option 3: Start everything together
docker compose -f docker-compose.custom.yml up custom-jupyter api
```

### Python Example (using `pbi.APIClient`)

```python
from pbi import APIClient

# Connect to the API (uses Docker network, not localhost)
client = APIClient("http://pbi-api:8000")

# Quick metadata lookup
phages = client.get_phage_metadata(where_clause="Source_DB = 'RefSeq'", limit=10)
print(phages.head())

# SQL exploration
result = client.query("SELECT Source_DB, COUNT(*) FROM fact_phages GROUP BY Source_DB")
print(result)

client.close()
```

### R Example (using `httr`)

```r
library(httr)
library(jsonlite)

# Get database stats
response <- GET("http://pbi-api:8000/stats")
stats <- fromJSON(content(response, "text"))
cat("Phages:", format(stats$database$phages, big.mark = ","), "\n")

# Query phage metadata
response <- GET("http://pbi-api:8000/phage-metadata", query = list(limit = 10))
phages <- fromJSON(content(response, "text"))
print(phages)
```

### curl Example (command line)

```bash
# Health check
curl http://pbi-api:8000/health

# Get statistics
curl http://pbi-api:8000/stats

# Query metadata
curl "http://pbi-api:8000/phage-metadata?limit=10"
```

See [API Reference](../api/overview.md) for full endpoint documentation.

---

## Template: Build Your Own Container

### Fill-in-the-Blank Dockerfile

```dockerfile
# =============================================================================
# My Custom PBI-Scope Container
# =============================================================================
FROM __BASE_IMAGE__

# System dependencies
RUN apt-get update && apt-get install -y \
    __SYSTEM_PACKAGES__ \
    && rm -rf /var/lib/apt/lists/*

# Language-specific packages
RUN __INSTALL_COMMAND__ __PACKAGES__

# Working directory
WORKDIR /workspace

# Copy scripts (optional - you can also mount them)
# COPY scripts/ /workspace/scripts/

# Entrypoint
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE __PORT__
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["jupyter"]
```

### Fill-in-the-Blank docker-compose.yml

```yaml
services:
  my-custom-service:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: pbi-custom
    user: "${UID:-1000}:${GID:-1000}"
    ports:
      - "__PORT__:__PORT__"
    volumes:
      - pbi-data:/data:ro
      - .:/workspace
      - ./output:/workspace/output
    environment:
      - DATA_PATH=/data/processed
      - HOME=/workspace
    networks:
      - pbi-network
    command: ["jupyter"]  # or "script" or "bash"

volumes:
  pbi-data:
    external: true

networks:
  pbi-network:
    external: true
```

---

## Available Base Images

| Image | Language | Jupyter | RStudio | Size | Best For |
|-------|----------|---------|---------|------|----------|
| `rocker/r-ver:4.3.2` | R | Via IRkernel | No | ~800 MB | R-focused work |
| `rocker/rstudio:4.3.2` | R | Via IRkernel | Yes (port 8787) | ~1.2 GB | RStudio users |
| `python:3.10-slim` | Python | Built-in | No | ~150 MB | Python-focused work |
| `jupyter/scipy-notebook` | Python | Built-in | No | ~1.5 GB | Scientific Python |
| `jupyter/r-notebook` | Both | Built-in | No | ~1.8 GB | Quick start |
| `ubuntu:22.04` | Any | Manual | Manual | ~75 MB | Maximum control |

!!! tip "Choosing a Base Image"
    - **Start with `rocker/r-ver`** if you need R — it has the best R package ecosystem
    - **Start with `python:3.10-slim`** if you need Python — it's lightweight and fast to build
    - **Start with `jupyter/r-notebook`** if you want both languages pre-configured

---

## Connecting to the Database from Different Languages

### Python (using `pbi` package)

```python
from pbi import quick_connect

retriever = quick_connect()
phages = retriever.get_phage_metadata(limit=10)
print(phages.head())
retriever.close()
```

### R (using `DBI` + `duckdb`)

```r
library(DBI)
library(duckdb)

db_path <- file.path(Sys.getenv("DATA_PATH", "/data/processed"),
                     "databases", "phage_database_optimized.duckdb")
con <- dbConnect(duckdb(), dbdir = db_path, read_only = TRUE)

phages <- dbGetQuery(con, "SELECT * FROM fact_phages LIMIT 10")
print(phages)

dbDisconnect(con, shutdown = TRUE)
```

### Julia (using `DuckDB.jl`)

```julia
using DuckDB

db_path = joinpath(ENV["DATA_PATH"], "databases", "phage_database_optimized.duckdb")
con = DuckDB.connect(db_path, read_only=true)

phages = DuckDB.execute(con, "SELECT * FROM fact_phages LIMIT 10")
println(phages)

DuckDB.close(con)
```

---

## File Mounting Strategies

### Bind Mount (Recommended for Development)

```yaml
volumes:
  - .:/workspace  # Mount current directory
```

**Pros:**

- Edit files on host, see changes immediately in container
- No rebuild needed when changing scripts
- Files persist across container restarts

**Cons:**

- File permissions may differ between host and container
- Performance may be slower on macOS/Windows

### COPY in Dockerfile (Recommended for Production)

```dockerfile
COPY scripts/ /workspace/scripts/
```

**Pros:**

- Scripts are baked into the image (version-controlled)
- No permission issues
- Consistent across all environments

**Cons:**

- Must rebuild image to change scripts
- Image size increases

### Hybrid Approach

```dockerfile
# Copy default scripts
COPY scripts/ /workspace/scripts/

# But also allow mounting custom scripts at runtime
# (via docker-compose volumes)
```

---

## Troubleshooting

### "Permission denied" when writing to output/

**Cause:** The container runs as a non-root user, but the output directory is owned by root.

**Solution:**

```bash
# Fix permissions on the host
chmod -R 777 mount_scripts/output/

# Or run as root (not recommended for production)
docker compose -f docker-compose.custom.yml run --user root custom-jupyter
```

### "Database not found" error

**Cause:** The `pbi-data` volume doesn't exist or isn't mounted.

**Solution:**

```bash
# Check if the volume exists
docker volume ls | grep pbi-data

# If not, run the pipeline first to create it
docker compose up pipeline

# Or mount an external volume
# In docker-compose.custom.yml, remove `external: true` and let Docker create it
```

### Jupyter won't start: "FileNotFoundError"

**Cause:** The container can't create required directories.

**Solution:** The entrypoint script handles this automatically. If it still fails:

```bash
# Run with bash to debug
docker compose -f docker-compose.custom.yml run custom-jupyter bash

# Inside the container, check permissions
ls -la /workspace
ls -la /.local
```

### R kernel not showing in Jupyter

**Cause:** IRkernel not installed or not registered.

**Solution:**

```bash
# Inside the container, reinstall IRkernel
R -e 'IRkernel::installspec(user = FALSE)'

# Restart Jupyter Lab
```

### Slow file access on macOS/Windows

**Cause:** Docker Desktop has known performance issues with bind mounts.

**Solution:**

- Use named volumes for large datasets
- Keep source code in the container (COPY) and only mount output directories
- Consider using Docker Desktop's "VirtioFS" feature (if available)

---

## Example: Complete R + Python Workflow

The [`mount_scripts/`](https://github.com/ThibaultSchowing/PBI/tree/main/mount_scripts) directory contains a complete working example:

| File | Description |
|------|-------------|
| `Dockerfile` | Builds the R + Python container |
| `docker-compose.custom.yml` | Defines Jupyter and script modes |
| `entrypoint.sh` | Handles mode switching and UID patching |
| `explore_phages.R` | R script for database exploration |
| `explore_phages.py` | Python script for database exploration |
| `explore_phages.ipynb` | Jupyter notebook with both languages |
| `output/` | Directory for saved plots |

**Quick test:**

```bash
cd mount_scripts/

# Build
docker compose -f docker-compose.custom.yml build

# Run script mode
docker compose -f docker-compose.custom.yml up custom-scripts

# Check output
ls output/
# 01_source_distribution.png
# 02_length_distribution.png
# 03_lifestyle_distribution.png
# 04_top_hosts.png
# 05_gc_content_comparison.png
# 06_assembly_quality.png
```

---

## See Also

- [Analysis Container Guide](analysis-guide.md) — The default PBI-Scope container
- [PBI Package Reference](pbi-package.md) — Python API for data access
- [Docker Guide](docker-guide.md) — Docker Compose setup and configuration
- [API Reference](../api/overview.md) — REST API for metadata queries

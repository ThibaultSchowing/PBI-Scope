# mount_scripts/

This directory contains an example custom Docker container for PBI-Scope. It demonstrates how to build your own container with R and Python, connected to the PBI-Scope database.

## Files

| File | Description |
|------|-------------|
| `Dockerfile` | Builds an R + Python container with commented options |
| `docker-compose.custom.yml` | Defines Jupyter and script modes |
| `entrypoint.sh` | Handles mode switching and UID patching |
| `explore_phages.R` | R script for database exploration (6 plots) |
| `explore_phages.py` | Python script for database exploration (6 plots) |
| `explore_phages.ipynb` | Jupyter notebook with both R and Python cells |
| `output/` | Directory for saved plots |

## Use Cases

This example supports three ways of working with the PBI-Scope data:

### 1. Jupyter Notebook (interactive exploration)

Launch Jupyter Lab with both R and Python kernels. Edit the notebook in your browser, run cells one by one, see plots inline.

```bash
docker compose -f docker-compose.custom.yml up custom-jupyter
# Open http://localhost:8888
```

Best for: exploring data, prototyping analyses, teaching, visualization.

### 2. Script execution (batch processing)

Run a script from start to finish without interaction. The container starts, executes the script, saves outputs, and exits.

```bash
docker compose -f docker-compose.custom.yml up custom-scripts
# Plots saved to ./output/
```

Best for: automated pipelines, long-running analyses, reproducible workflows, scheduled tasks.

### 3. Interactive shell (debugging)

Open a bash shell inside the container to test commands, inspect files, or debug issues.

```bash
docker compose -f docker-compose.custom.yml run custom-jupyter bash
# You are now inside the container at /workspace
```

Best for: troubleshooting, testing package imports, checking file paths.

### 4. API Queries (lightweight exploration)

Query the PBI-Scope API without loading the database directly. The API runs as a separate service on the same Docker network and can be reached from any container via `http://pbi-api:8000`.

!!! note "Read-only access"
    The API provides **read-only** access to the database. All queries are validated and restricted to SELECT statements. This makes it safe for shared environments where multiple users or containers need concurrent access.

```bash
# Start the API (if not already running)
docker compose up api

# Start the custom container
docker compose -f docker-compose.custom.yml up custom-jupyter
```

**Python (using `pbi.APIClient`):**

```python
from pbi import APIClient

client = APIClient("http://pbi-api:8000")

# Quick metadata lookup
phages = client.get_phage_metadata(where_clause="Source_DB = 'RefSeq'", limit=10)
print(phages.head())

# SQL exploration
result = client.query("SELECT Source_DB, COUNT(*) FROM fact_phages GROUP BY Source_DB")
print(result)

client.close()
```

**R (using `httr`):**

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

**curl (command line):**

```bash
# Health check
curl http://pbi-api:8000/health

# Get statistics
curl http://pbi-api:8000/stats

# Query metadata
curl "http://pbi-api:8000/phage-metadata?limit=10"
```

Best for: quick metadata lookups, lightweight queries, shared access across multiple containers, when you don't need local FASTA files.

**API vs Direct Database Access:**

| Feature | API | Direct Access |
|---------|-----|---------------|
| Setup | No local DB needed | Requires `pbi-data` volume |
| Speed | Network latency | Direct file read |
| Bulk downloads | Not supported | Recommended |
| ML streaming | Not supported | Required |
| Shared access | Multiple containers | Single instance |
| SQL queries | Supported | Supported |

See [API Reference](../api/overview.md) for full endpoint documentation.

## Quick Start

```bash
# Build the container
docker compose -f docker-compose.custom.yml build

# Run with Jupyter (interactive)
docker compose -f docker-compose.custom.yml up custom-jupyter
# Open http://localhost:8888

# Run script (batch processing)
docker compose -f docker-compose.custom.yml up custom-scripts
# Plots saved to ./output/
```

## Prerequisites

- The `pbi-data` Docker volume must exist (created by running the pipeline)
- Docker and Docker Compose installed

## Customization

See [Building Custom Containers](docs/guides/custom-containers.md) for a full guide on:

- Modifying the Dockerfile for your needs
- Adding R or Python packages
- Creating your own scripts
- Connecting to the database from different languages

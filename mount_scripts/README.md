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

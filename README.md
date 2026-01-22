# PBI Scraper

Phages Bacteria Interaction data scraping from [PhageScope](https://phagescope.deepomics.org).

WORK IN PROGRESS 

Documentation on the [github pages](https://thibaultschowing.github.io/PBI/).

## Summary

This library reads and merge the data from PhageScope into a queryable SQL database, accessible from Python. The first objective is to be able to simplify the access to this data and in further steps, add others data such as bacterial genomes and more detailed interactions and tools via an API. 

Overall the Snakemake pipeline downloads and merges the metadata into a SQL database and merges the protein fasta and phage genome fasta into two big files and create the corresonding fasta.fai index files using pyfaidx. 

Tables and project overview available on [this page](https://thibaultschowing.github.io/PBI/getting-started/overview/). This page includes data summary on all tables as well as [a database validation report](https://thibaultschowing.github.io/PBI/reports/database_validation.html) helping visualize the database structure and elements and compare it to the data available on [PhageScope](https://phagescope.deepomics.org/database).

## Installation & Usage

### Option 1: Docker (Recommended for Production)

The easiest way to run the PBI pipeline and API:

```bash
# Build and run the pipeline
docker compose build pipeline
docker compose run --rm pipeline

# Build and start the API
docker compose build api
docker compose up -d api

# Access the API
curl http://localhost:8000/health
# Visit http://localhost:8000/docs for interactive API documentation
```

See [DOCKER.md](DOCKER.md) for detailed Docker instructions.

### Option 2: Local Development

For development, testing, and debugging:

```bash
# 1. Create conda environment
conda env create -f workflow/envs/base_environment.yaml
conda activate snakemake_base

# 2. Install PBI package
pip install -e .

# 3. Run pipeline
./run_local.sh

# 4. (Optional) Start API locally
export DATA_PATH="data/processed"
uvicorn api.app:app --reload
```

See [LOCAL_SETUP.md](LOCAL_SETUP.md) for detailed local setup instructions.

### Quick Start

**Docker (Production):**

```bash
docker compose build pipeline && docker compose run --rm pipeline
```

**Local (Development):**

```bash
./run_local.sh
```


# PBI Scraper

Phages Bacteria Interaction data scraping from [PhageScope](https://phagescope.deepomics.org).

WORK IN PROGRESS 

Documentation on the [github pages](https://thibaultschowing.github.io/PBI/).

## Summary

This library reads and merge the data from PhageScope into a queryable SQL database, accessible from Python. The first objective is to be able to simplify the access to this data and in further steps, add others data such as bacterial genomes and more detailed interactions and tools via an API. 

Overall the Snakemake pipeline downloads and merges the metadata into a SQL database and merges the protein fasta and phage genome fasta into two big files and create the corresonding fasta.fai index files using pyfaidx. 

Tables and project overview available on [this page](https://thibaultschowing.github.io/PBI/getting-started/overview/). This page includes data summary on all tables as well as [a database validation report](https://thibaultschowing.github.io/PBI/reports/database_validation.html) helping visualize the database structure and elements and compare it to the data available on [PhageScope](https://phagescope.deepomics.org/database).

## Quick Start Options

### Option 1: Docker (Recommended for API users)

The easiest way to run the PBI pipeline and API is using Docker:

```bash
# Build and run the pipeline to create the database
docker compose build pipeline
docker compose run --rm pipeline

# Start the API service
docker compose build api
docker compose up -d api

# Access the API at http://localhost:8000
curl http://localhost:8000/health

# Access interactive API docs at http://localhost:8000/docs
```

For detailed API documentation and available endpoints, see [DOCKER.md](DOCKER.md#api-endpoints).

See [DOCKER.md](DOCKER.md) for detailed Docker instructions and API documentation.

### Option 2: Local Installation

For local development and analysis, see the [installation guide](https://thibaultschowing.github.io/PBI/getting-started/installation/) in the documentation.


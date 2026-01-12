# PBI Scraper

Phages Bacteria Interaction data scraping from [PhageScope](https://phagescope.deepomics.org).

WORK IN PROGRESS 

Documentation on the [github pages](https://thibaultschowing.github.io/PBI/).

## Summary

This library reads and merge the data from PhageScope into a queryable SQL database, accessible from Python. The first objective is to be able to simplify the access to this data and in further steps, add others data such as bacterial genomes and more detailed interactions and tools via an API. 

Overall the Snakemake pipeline downloads and merges the metadata into a SQL database and merges the protein fasta and phage genome fasta into two big files and create the corresonding fasta.fai index files using pyfaidx. 

Tables and project overview available on [this page](https://thibaultschowing.github.io/PBI/getting-started/overview/). This page includes data summary on all tables as well as [a database validation report](https://thibaultschowing.github.io/PBI/reports/database_validation.html) helping visualize the database structure and elements and compare it to the data available on [PhageScope](https://phagescope.deepomics.org/database).

## 🐳 Docker Setup (Recommended)

The easiest way to use PBI is through Docker, which provides:
- **Pipeline Container**: Automated data download and database creation from PhageScope
- **API Container**: REST API for querying the database

### Quick Start with Docker

```bash
# 1. Build the containers
docker compose build

# 2. Run the pipeline to create the database (takes several hours)
docker compose run --rm pipeline

# 3. Start the API server
docker compose up -d api

# 4. Access the API at http://localhost:8000/docs
```

**📖 For detailed Docker instructions, see [DOCKER.md](DOCKER.md)**

### API Features

The REST API provides endpoints to:
- Query phage and protein metadata
- Execute custom SQL queries
- Get database statistics
- Filter by various attributes (source, host, length, etc.)

Example API usage:
```bash
# Get database statistics
curl http://localhost:8000/stats

# Query phages
curl "http://localhost:8000/phages?source_db=RefSeq&limit=10"

# Interactive documentation
open http://localhost:8000/docs
```

See [examples/api_usage.py](examples/api_usage.py) for Python usage examples.


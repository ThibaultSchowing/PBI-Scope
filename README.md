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

# 2. Run the pipeline to create the database (⚠️ takes 2-4 hours on first run)
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

## 💻 Manual Setup (Alternative)

For users who prefer to run the pipeline directly without Docker:

### Prerequisites
- Python 3.8+
- [Pixi package manager](https://pixi.sh/latest/)
- Conda/Mamba
- 50GB+ disk space
- 32GB+ RAM recommended

### Quick Start

**⚠️ Important: First-time database creation takes 2-4 hours**

```bash
# 1. Clone and navigate to repository
git clone <repository-url>
cd PBI

# 2. Install Pixi (if not already installed)
curl -fsSL https://pixi.sh/install.sh | bash

# 3. Install PBI package
pixi run pip install -e .

# 4. Set up caching (recommended)
mkdir -p /mnt/snakemake-cache
export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/

# 5. Run pipeline to create database (2-4 hours on first run)
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --notemp --cores 4

# The database will not be queryable until this completes!
```

**📖 For detailed manual setup instructions, see [Installation Guide](https://thibaultschowing.github.io/PBI/getting-started/installation/)**

### Using the Database

Once the pipeline completes, you can query the database:

```python
import pbi

# Connect to database
retriever = pbi.quick_connect()

# Get statistics
stats = retriever.get_stats()
print(f"Phages: {stats['database']['phages']:,}")
print(f"Proteins: {stats['database']['proteins']:,}")

# Query phages
df = retriever.get_phage_sequences(
    "SELECT * FROM fact_phages WHERE Length > 100000 LIMIT 10"
)
```



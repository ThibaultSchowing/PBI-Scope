# PBI Scraper

Phages Bacteria Interaction data scraping from [PhageScope](https://phagescope.deepomics.org).

WORK IN PROGRESS 

Documentation on the [github pages](https://thibaultschowing.github.io/PBI/).

## Summary

This library reads and merges data from PhageScope into a queryable SQL database, accessible from Python. It integrates phage genomic data, bacterial host genomes from NCBI RefSeq, and provides machine learning tools for phage-host interaction prediction.

The Snakemake pipeline downloads and merges metadata into a DuckDB database, combines FASTA files for phages, proteins, and hosts into indexed files using pyfaidx, and creates phage-host association mappings for ML applications.

**Key Features:**
- 📊 14+ phage databases integrated (RefSeq, Genbank, PhagesDB, etc.)
- 🔬 Host bacterial genomes from NCBI RefSeq
- ⚡ Fast indexed sequence access (phages, proteins, hosts)
- 🤖 Machine learning tools for phage-host prediction
- 🐍 Python `pbi` package with easy-to-use API
- 🌐 REST API for programmatic access
- 📚 Rich metadata: proteins, CRISPR, AMR genes, and more

Tables and project overview available on [this page](https://thibaultschowing.github.io/PBI/getting-started/overview/). See also the [Machine Learning Guide](https://thibaultschowing.github.io/PBI/guides/machine-learning/) for ML applications.

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


## Machine Learning Support

PBI includes comprehensive machine learning support for phage-host interaction prediction:

```python
from pbi import quick_connect, NegativeExampleGenerator

# Connect to database with all sequences
retriever = quick_connect()

# Get phage-host interaction pairs
positive_pairs = retriever.get_phage_host_pairs(limit=1000)

# Generate negative examples
neg_gen = NegativeExampleGenerator(retriever)

# Create balanced dataset (50% positive, 50% negative)
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=positive_pairs,
    strategy='mixed',  # Combines random, GC-based, and taxonomy-based negatives
    positive_ratio=0.5
)

# Dataset is now ready for ML training!
print(f"Total samples: {len(dataset)}")
print(f"Positives: {(dataset['Label'] == 1).sum()}")
print(f"Negatives: {(dataset['Label'] == 0).sum()}")
```

**Resources:**
- 📓 [Machine Learning Tutorial Notebook](notebooks/ml_1_phage_host_dataset.ipynb)
- 📖 [Machine Learning Guide](https://thibaultschowing.github.io/PBI/guides/machine-learning/)
- 🔬 Example use cases: host range prediction, therapeutic candidate identification, lifestyle classification


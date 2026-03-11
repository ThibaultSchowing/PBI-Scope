
![alt](https://github.com/ThibaultSchowing/PBI/blob/main/docs/img/github-header-banner%20(1).png)

# PBI - Phage Bacteria Interaction

> A proof-of-concept dockerized bioinformatics pipeline that makes phage genomic data from [PhageScope](https://phagescope.deepomics.org/database) available in an efficient, structured format for training neural networks and AI models for phage-host interaction prediction. 
>
> **Install - Wait - Work** The pipeline takes care of everything within Docker !

[![Documentation](https://img.shields.io/badge/docs-github%20pages-blue)](https://thibaultschowing.github.io/PBI/)

## 🎯 What is PBI?

PBI integrates data from 14+ phage databases (RefSeq, Genbank, PhagesDB, etc.) via PhageScope and downloads matching bacterial host genomes from NCBI RefSeq, consolidating everything into a queryable DuckDB database with indexed FASTA files. It provides:

- **📊 Unified Database**: ~873K phages, ~43M protein annotations in one DuckDB database
- **🦠 Host Genomes**: NCBI RefSeq bacterial reference genomes, indexed for fast retrieval
- **⚡ Fast Access**: Indexed sequences with pyfaidx + `host_fasta_mapping.json` for instant retrieval
- **🐍 Python Package**: Easy-to-use `pbi` package for data access and ML dataset preparation
- **🔬 Jupyter Lab**: Analysis container with direct database access (recommended usage)
- **🤖 ML Ready**: Built-in tools for phage-host interaction prediction (streaming datasets, negative example generation)

> **Note**: PBI is dependent on PhageScope as its primary data source. 

![](https://github.com/ThibaultSchowing/PBI/blob/main/docs/img/PBI_Schema.png)

## 📚 Documentation

**Full [documentation](https://thibaultschowing.github.io/PBI/)**.

**Check Notebook examples [in the notebooks folder !](https://github.com/ThibaultSchowing/PBI/tree/main/notebooks)**

### Quick Links

- 🚀 **[Installation Guide](https://thibaultschowing.github.io/PBI/guides/installation/)** — Docker setup, SSH port forwarding, running the pipeline
- 🔍 **[How It Works](https://thibaultschowing.github.io/PBI/guides/how-it-works/)** — Pipeline internals, `pbi` package, key data files
- 📊 **[Analysis Container Usage](https://thibaultschowing.github.io/PBI/guides/analysis-guide/)** — Jupyter Lab, demo notebooks
- 🤖 **[Machine Learning Guide](https://thibaultschowing.github.io/PBI/guides/machine-learning/)** — ML dataset preparation
- 📖 **[Database Schema](https://thibaultschowing.github.io/PBI/database/overview/)** — Tables, relationships, host data

## 🚀 Quick Start

### Requirements

- Docker (v20.10+) and Docker Compose (v2.0+)
- At least **230 GB** of free disk space
- **16 GB RAM** minimum (32 GB recommended)
- NCBI API key (optional but strongly recommended for 10x faster host downloads) -> [Get it here](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/api/api-keys/)

### 1. Clone and Configure

```bash
git clone https://github.com/ThibaultSchowing/PBI.git
cd PBI

# Create environment variables with your NCBI credentials
export NCBI_EMAIL="you@domain.org"
export NCBI_API_KEY="..."

```

### 2. Run the Pipeline (in tmux or equivalent for long SSH sessions)

```bash
# Set up SSH port forwarding first (on your local machine):
# ssh -L 8888:localhost:8888 username@your-server

tmux new -s pbi

docker compose build pipeline
docker compose run --rm pipeline
# ~4 hours for PhageScope data, ~12-18 hours for host genomes
```

### 3. Start the Analysis Container

```bash
docker compose build analysis
docker compose up -d analysis
# Access Jupyter Lab at http://localhost:8888
```

### 4. Use the PBI Package in Jupyter

```python
from pbi import quick_connect

retriever = quick_connect()  # auto-detects paths via DATA_PATH env var
stats = retriever.get_stats()
print(f"Total phages: {stats['database']['phages']:,}")

# Get phage-host interaction pairs
pairs = retriever.get_phage_host_pairs(limit=1000)

# Retrieve sequences
sequences = retriever.get_sequences_by_ids(
    pairs['Phage_ID'].tolist(), sequence_type='phage'
)
```

Open [the notebooks folder](https://github.com/ThibaultSchowing/PBI/tree/main/notebooks) to get started with the demo.

## 📓 Demo Notebooks

Three notebooks in `notebooks/` demonstrate the main workflows:

| Notebook | Description |
|----------|-------------|
| `01_database_exploration.ipynb` | Database statistics, quality control, host coverage analysis |
| `02_sequence_retrieval.ipynb` | Metadata queries, sequence retrieval, phage-host pairs |
| `03_ml_streaming.ipynb` | ML dataset preparation, negative examples, PyTorch streaming |

## 🏗️ Architecture

```
┌─────────────┐            ┌──────────────┐      ┌─────────────────┐
│  Pipeline   │──builds──▶│   pbi-data    │◀────│  Analysis       │
│ (Snakemake) │            │   volume     │      │ (Jupyter Lab)   │
└─────────────┘            └──────────────┘      │  port 8888      │
                                 │               └─────────────────┘
                                 ├────▶ DuckDB database (~15 GB)
                                 ├────▶ Phage FASTA + index (~40 GB)
                                 ├────▶ Protein FASTA + index (~60 GB)
                                 └────▶ Host FASTA files + mapping JSON (~87 GB)
```

**Services (docker-compose.yml):**
- **Pipeline**: Snakemake workflow to build the database (~225 GB data total)
- **Analysis**: Jupyter Lab with `pbi` package pre-installed (port 8888)
- **API**: REST API for external integrations (port 8000, currently untested)

## 📊 Data Sources

- **Phage Databases**: 14 databases via [PhageScope](https://phagescope.deepomics.org/workspace/) (RefSeq, Genbank, EMBL, DDBJ, PhagesDB, GOV2, MGV, GVD, IMG/VR, GPD, CHVD, STV, TemPhD, IGVD)
- **Host Genomes**: NCBI RefSeq bacterial reference genomes (~9,000 unique assemblies attempted)
- **Annotations**: Proteins, CRISPR arrays, AMR genes, anti-CRISPR, virulence factors, tRNA/tmRNA

## 🔗 Links
- 🗃️ **[PhageScope](https://phagescope.deepomics.org/workspace/)**
- 📚 **[Full Documentation](https://thibaultschowing.github.io/PBI/)**
- 🐛 **[Issue Tracker](https://github.com/ThibaultSchowing/PBI/issues)**
- 📧 **[Contact](https://github.com/ThibaultSchowing)**

## License

MIT

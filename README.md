# PBI - Phage Bioinformatics Interface

> Comprehensive phage genomics database with integrated host genomes, protein annotations, and machine learning tools for phage-host interaction prediction.

[![Documentation](https://img.shields.io/badge/docs-github%20pages-blue)](https://thibaultschowing.github.io/PBI/)

## 🎯 What is PBI?

PBI integrates data from 14+ phage databases (RefSeq, Genbank, PhagesDB, etc.) and NCBI RefSeq bacterial genomes into a queryable DuckDB database with indexed FASTA files. It provides:

- **📊 Unified Database**: 800K+ phages, proteins, and host genomes in one place
- **⚡ Fast Access**: Indexed sequences with pyfaidx for instant retrieval
- **🐍 Python Package**: Easy-to-use `pbi` package for data access
- **🌐 REST API**: HTTP API for external integrations
- **🔬 Direct Analysis**: Jupyter Lab environment for bulk data analysis (5-50x faster than API)
- **🤖 ML Ready**: Built-in tools for phage-host interaction prediction

## 📚 Documentation

**Full documentation available at: https://thibaultschowing.github.io/PBI/**

### Quick Links

- 🚀 **[Getting Started](https://thibaultschowing.github.io/PBI/guides/docker-guide/)** - Installation and basic usage
- 📖 **[Analysis Guide](https://thibaultschowing.github.io/PBI/guides/analysis-guide/)** - Database access and data retrieval
- 🤖 **[Machine Learning Guide](https://thibaultschowing.github.io/PBI/guides/machine-learning/)** - ML dataset preparation
- 🔧 **[API Reference](https://thibaultschowing.github.io/PBI/api/)** - REST API endpoints
- 📊 **[Database Schema](https://thibaultschowing.github.io/PBI/getting-started/overview/)** - Tables and relationships

## 🚀 Quick Start

### Docker (Recommended)

```bash
# 1. Build and run the pipeline to create the database
docker compose build pipeline
docker compose run --rm pipeline

# 2. Start the analysis service (Jupyter Lab)
docker compose build analysis
docker compose up -d analysis

# 3. Access Jupyter Lab
# Browser: http://localhost:8888
# VSCode: See analysis guide for remote kernel connection
# Open notebooks/ml_1_phage_host_dataset.ipynb to get started
```

### Using the Python Package

```python
from pbi import quick_connect, NegativeExampleGenerator

# Connect to database (automatically uses correct paths in Docker)
retriever = quick_connect()

# Get database statistics
stats = retriever.get_stats()
print(f"Total phages: {stats['database']['phages']:,}")

# Query phage-host interaction pairs
pairs = retriever.get_phage_host_pairs(limit=1000)

# Retrieve sequences
phage_ids = pairs['Phage_ID'].tolist()
sequences = retriever.get_sequences_by_ids(phage_ids, sequence_type='phage')

# Generate ML datasets
neg_gen = NegativeExampleGenerator(retriever)
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=pairs,
    strategy='mixed',
    positive_ratio=0.5
)
```

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Pipeline   │────▶│   pbi-data   │◀────│  Analysis   │
│ (Snakemake) │     │    volume    │     │(Jupyter Lab)│
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ├────▶ DuckDB database
                           ├────▶ Indexed FASTA files
                           └────▶ Metadata & reports
```

**Services:**
- **Pipeline**: Snakemake workflow to build the database (~150GB data)
- **Analysis**: Jupyter Lab with direct database access (port 8888)
- **API**: REST API for external integrations (port 8000)

## 📊 Data Sources

- **Phage Databases**: RefSeq, Genbank, PhagesDB, MillardLab, INPHARED, and 9+ more
- **Host Genomes**: NCBI RefSeq bacterial reference genomes
- **Annotations**: Proteins, CRISPR spacers, AMR genes, lifestyle predictions

## 🔗 Links

- 📚 **[Full Documentation](https://thibaultschowing.github.io/PBI/)**
- 🐛 **[Issue Tracker](https://github.com/ThibaultSchowing/PBI/issues)**
- 📧 **[Contact](https://github.com/ThibaultSchowing)**

## 📄 License

See LICENSE file for details.

---

**Note**: Archived documentation files have been moved to `docs/archive/`. Please refer to the [online documentation](https://thibaultschowing.github.io/PBI/) for the most up-to-date information.
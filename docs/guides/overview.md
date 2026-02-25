# Guides Overview

Welcome to the PBI guides! Choose the guide that matches your needs.

## Getting Started

New to PBI? Start here:

### 🐳 [Installation Guide](installation.md) (Docker — Recommended)

The only fully supported execution method. Docker is required for the full pipeline (including host genome downloads). Covers:
- Installing Docker
- Cloning the repository and configuring NCBI credentials
- Running the pipeline container
- Setting up SSH port forwarding and accessing the Jupyter Lab analysis container

**Time for first pipeline run:**
- **~4 hours** — phage metadata download and processing
- **~12–18 hours** — host genome resolution and download (requires NCBI API key for best speed)

> **Note**: Use `tmux` or a similar terminal multiplexer to keep your SSH session alive during long runs.

### 🔍 [How It Works](how-it-works.md)

Understand the PBI internals before diving in:
- The Snakemake pipeline stages and rules
- The `pbi` Python package and its key classes
- Key data files (including `host_fasta_mapping.json`)
- Host resolution process
- Docker services and data flow

## Usage Guides

Once the pipeline has run, use these guides to interact with the data:

### 📊 [Analysis Container Usage](analysis-guide.md) (Recommended)

The primary way to explore and analyze PBI data using Jupyter Lab with direct database access. Includes links to the three demo notebooks:

- `01_database_exploration.ipynb` — Database statistics and quality control
- `02_sequence_retrieval.ipynb` — Sequence retrieval with the `pbi` package
- `03_ml_streaming.ipynb` — AI/ML dataset preparation and streaming

### 📖 [Pipeline Execution Guide](pipeline-execution.md)

Detailed information about the pipeline steps, especially host genome download tracking and monitoring. Also covers local execution (without Docker) as an alternative.

### 🐍 [PBI Package Reference](pbi-package.md)

API reference for the `pbi` Python package — `SequenceRetriever`, `NegativeExampleGenerator`, and dataset classes.

### 🤖 [Machine Learning Guide](machine-learning.md)

End-to-end guide for building phage-host interaction prediction models using PBI data.

## Database Documentation

### 📊 [Database Overview](../database/overview.md)

Understand the database schema, tables, data sources, and how host genome data is stored separately.

### 🔗 [Host Resolution Details](../database/host-resolution.md)

How host species names from phage metadata are parsed, classified, and resolved to NCBI assembly accessions.

## What You'll Get

After running the full pipeline, you'll have:

- **~873,000 phage genomes** with metadata (from 14+ databases via PhageScope)
- **~43 million protein annotations**
- **Optimized DuckDB database** (~15 GB) for fast analytical queries
- **Indexed FASTA files** (~100 GB) for phages and proteins
- **Host genome FASTA files** from NCBI RefSeq, indexed via `host_fasta_mapping.json`
- **HTML validation reports**

## Prerequisites

| Requirement | Required |
|-------------|---------|
| Docker (v20.10+) | ✅ Yes |
| Docker Compose (v2.0+) | ✅ Yes |
| Disk Space | ✅ 225+ GB |
| RAM | ✅ 16+ GB (32 GB recommended) |
| NCBI API key | Recommended (10x faster host downloads) |
| Python / Conda | Only for local development |

## Need Help?

- Check the [Command Reference](../reference/commands.md) for quick answers
- Review [troubleshooting sections](installation.md#troubleshooting) in each guide
- Open an issue on [GitHub](https://github.com/ThibaultSchowing/PBI/issues)

---

Ready? Start with the [Installation Guide](installation.md)!


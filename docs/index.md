# Welcome to PBI Documentation

**Phage-Bacteria Interaction Database Pipeline**

## What is PBI?

PBI is a bioinformatics pipeline designed to make phage genomic data from [PhageScope](https://phagescope.deepomics.org/database) available in an efficient, structured way for training neural networks and AI models for phage-host interaction prediction. It integrates data from 14+ phage databases via PhageScope and downloads matching bacterial host genomes from NCBI RefSeq.

> **Note**: PBI is a **proof of concept** and is dependent on PhageScope as its primary data source. Future development will aim to provide more precise host strain information when available.

**What you get after running the pipeline:**

- ~873,000 phage genomes with complete metadata
- ~43 million protein annotations with functional predictions
- Bacterial host reference genomes from NCBI RefSeq
- Optimized DuckDB database (~5 GB) for fast analytical queries
- Indexed FASTA files (~100 GB) with pyfaidx for rapid sequence retrieval
- Python package (`pbi`) for easy data access and machine learning dataset preparation

## Getting Started

The recommended (and primary) way to run PBI is via Docker. See the [Installation Guide](guides/installation.md) for step-by-step instructions on setting up Docker, cloning the repository, running the pipeline container, and connecting to the analysis container via SSH port forwarding.

<div class="grid cards" markdown>

-   **[Installation Guide](guides/installation.md)**

    ---

    How to install Docker, clone the repository, configure the pipeline, run the containers, and connect to the Jupyter Lab analysis environment via SSH port forwarding.

-   **[How It Works](guides/how-it-works.md)**

    ---

    Explanation of the pipeline internals, the `pbi` Python package (including key files like `host_fasta_mapping.json`), and the overall architecture.

-   **[Analysis Container Usage](guides/analysis-guide.md)**

    ---

    How to explore the database, retrieve sequences, and prepare machine learning datasets using the Jupyter Lab analysis container. Includes links to the three demo notebooks.

-   **[API Usage](api/overview.md)**

    ---

    REST API reference. Note: the API is currently **untested** and not the recommended way to interact with the data.

</div>

## Pipeline Overview

The PBI pipeline follows a systematic data flow from download to analysis-ready outputs:

```
┌─────────────────────────────────────────────────────────────────┐
│                    PBI Data Flow                                │
│                                                                 │
│  ┌──────────────┐          ┌──────────────────────────────┐     │
│  │  PhageScope  │────────> │  Stage 1: Phage Metadata     │     │
│  │  (14+ DBs)   │          │  Download & merge metadata   │     │
│  └──────────────┘          │  + FASTA sequences           │     │
│                            │     ~4 hours first run       │     │
│                            └──────────────┬───────────────┘     │
│                                           │                     │
│                                           ▼                     │
│  ┌──────────────┐          ┌──────────────────────────────┐     │
│  │  NCBI RefSeq │────────> │  Stage 2: Host Resolution    │     │
│  │ (Bacterial   │          │  Parse host fields, resolve  │     │
│  │  genomes)    │          │  to assemblies, download     │     │
│  └──────────────┘          │     ~18-24 hours first run   │     │
│                            └──────────────┬───────────────┘     │
│                                           │                     │
│                                           ▼                     │
│                    ┌──────────────────────────────────────┐     │
│                    │  Final Outputs (in pbi-data volume)  │     │
│                    │  ├─ DuckDB Database  (~5 GB)         │     │
│                    │  ├─ Phage FASTA + index (~40 GB)     │     │
│                    │  ├─ Protein FASTA + index (~60 GB)   │     │
│                    │  ├─ Host FASTA files + JSON (~90 GB) │     │
│                    │  └─ HTML Validation Reports          │     │
│                    └─────────────────┬────────────────────┘     │
│                                      │                          │
│              ┌───────────────────────┴────────────────────┐     │
│              ▼                                            ▼     │
│     ┌─────────────────┐                    ┌─────────────────┐  │
│     │ Analysis Service│                    │   REST API      │  │
│     │  (Jupyter Lab)  │                    │  (FastAPI)      │  │
│     │  Port 8888      │                    │  Port 8000      │  │
│     └─────────────────┘                    └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

The database uses a **star schema** with phage metadata at the center and host genomes linked via a separate dimension table. See the [Database Overview](database/overview.md) for full details.

```
                     dim_proteins ──┐
                  dim_terminators ──┤
                  dim_anti_crispr ──┤
             dim_virulent_factors ──┤
       dim_transmembrane_proteins ──┤──▶ fact_phages (central)
                   dim_trna_tmrna ──┤
dim_antimicrobial_resistance_genes ─┤
                  dim_crispr_array ─┘
                       dim_hosts  ──▶ (linked via phage_host_links.csv
                                       and host_fasta_mapping.json)
```

All phage dimension tables link to `fact_phages` via **`Phage_ID`**. Host genomes are stored as separate FASTA files and indexed via `host_fasta_mapping.json` for fast retrieval.

## Documentation

<div class="grid cards" markdown>

-   **[Guides](guides/overview.md)**

    ---

    Installation, how it works, analysis container usage, and pipeline execution

-   **[Database](database/overview.md)**

    ---

    Schema documentation, tables, host data, and data sources

-   **[API Reference](api/overview.md)**

    ---

    REST API endpoints — currently untested

-   **[Developer Guide](developer/code-structure.md)**

    ---

    Architecture, code structure, and contributing

</div>

## Current Status

| Component | Status | Description |
|-----------|--------|-------------|
| **Pipeline** | ✅ Complete | Snakemake workflow with 14+ data sources |
| **Phage Database** | ✅ Complete | Optimized DuckDB with star schema |
| **Host Genomes** | ✅ Complete | NCBI RefSeq downloads with multi-host support |
| **Sequences** | ✅ Complete | Indexed FASTA files (phages, proteins, hosts) |
| **Docker** | ✅ Complete | Production-ready containers |
| **Python Package** | 🔧 Active Development | Core functionality available |
| **REST API** | ⚠️ Untested | Basic endpoints implemented, not validated |
| **Documentation** | 🔧 Active Development | Continuously improving |

## Need Help?

- Browse the [guides](guides/overview.md) for detailed instructions
- Report issues on [GitHub](https://github.com/ThibaultSchowing/PBI/issues)
- Check the [troubleshooting sections](guides/installation.md#troubleshooting) in our guides

---

_PBI is a proof of concept built with Snakemake, DuckDB, and FastAPI. It is under active development._


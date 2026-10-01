# Welcome to PBI-Scope Documentation

**PBI-Scope — Phage Bacteria Interactions (v0.6.0)**

## What is PBI-Scope?

PBI-Scope is a reproducible Docker-first pipeline that prepares phage-host data for analysis and machine learning.

It combines:

1. **Public phage data** from [PhageScope](https://phagescope.deepomics.org/) (which itself aggregates multiple phage sources): genomes, proteins, GFF3 annotations, and a large variety of metadata.
2. **Optional private datasets** fully local in `private_data/`
3. **Host genome resolution/download** from NCBI RefSeq
4. **BLAST database build** for sequence similarity search (phages, proteins, hosts, private, combined)

Outputs are stored in a shared data volume and made available through the `pbi` Python package or the REST API.

!!! info "Database overview and data sample available here: "
    For a quick visual overview of all PhageScope tables and data quality, see the [Database Validation Report](https://thibaultschowing.github.io/PBI-Scope/reports/database_validation.html) and [Phage Metadata Report](https://thibaultschowing.github.io/PBI-Scope/reports/phage_metadata_report.html).

> PBI-Scope is **not PhageScope-only** anymore. Private source ingestion is part of the standard workflow when source folders are present and their CSV files are complete!

## Start Here

<div class="grid cards" markdown>

- **[Installation Guide](guides/installation.md)**

  Docker setup, first run, and analysis access.

- **[Story — One Read Overview](guides/storytelling.md)**

  End-to-end narrative of what the tool does and in which order.

- **[Private Data Ingestion](guides/private-data-ingestion.md)**

  Required files, validation rules, and host sequence options.

- **[Analysis Container Usage](guides/analysis-guide.md)**

  VS Code Dev Containers (preferred) and Jupyter Lab workflow.

- **[Build Custom Containers](guides/custom-containers.md)**

  Create your own R+Python container connected to the PBI-Scope database.

- **[Database Reports](reports/database_validation.html)**

  Quick overview of all PhageScope tables and database validation.

</div>

## Quick Start Examples

### Using the `pbi` package (recommended for notebooks)

```python
from pbi import quick_connect

# Connect to the database
retriever = quick_connect()

# Get statistics
stats = retriever.get_stats()
print(f"Phages: {stats['database']['phages']:,}")

# Query phage metadata
phages = retriever.get_phage_metadata(limit=10)
print(phages[['Phage_ID', 'Source_DB', 'Length']].head())
```

### Using the API client (recommended for quick exploration)

```python
from pbi import APIClient

# Connect to the API (start with: docker compose up api)
client = APIClient("http://localhost:8000")

# Get database stats
stats = client.get_stats()
print(f"Phages: {stats['database']['phages']:,}")

# Query with filter
refseq = client.get_phage_metadata(
    where_clause="Source_DB = 'RefSeq' AND Length > 50000",
    limit=10
)
print(refseq.head())
```

### Notebooks

Explore the [example notebooks](https://github.com/ThibaultSchowing/PBI-Scope/tree/main/notebooks) for detailed workflows:

| Notebook | Description |
|----------|-------------|
| `00_pipeline_logs.ipynb` | Pipeline execution logs and reports |
| `01_database_exploration.ipynb` | Database statistics and quality control |
| `02_sequence_retrieval.ipynb` | Retrieving phage and protein sequences |
| `03_ml_streaming.ipynb` | ML dataset preparation with streaming |
| `04_data_release_exploration.ipynb` | Data release exploration |
| `05_end_to_end_walkthrough.ipynb` | Verify execution and explore functionalities |
| `06_reproducibility.ipynb` | Reproducibility and provenance tracking |
| `07_gff3_annotations.ipynb` | GFF3 gene annotation retrieval and analysis |
| `08_api_client.ipynb` | Using the REST API client |
| `09_blast_search.ipynb` | BLAST sequence similarity search |

## Pipeline overview

```text
+----------------------+        +----------------------------+
| public phage data    |------->| Stage 1: download + merge  |
| (PhageScope)         |        | public phage metadata/FASTA|
+----------------------+        +--------------+-------------+
                                               |
+----------------------+        +-------------v--------------+
| private_data/*       |------->| Stage 2: validate private  |
| (optional sources)   |        | metadata/phage/host files  |
+----------------------+        +--------------+-------------+
                                               |
+----------------------+        +-------------v--------------+
| NCBI RefSeq          |------->| Stage 3: resolve/download  |
| (host genomes)       |        | host assemblies            |
+----------------------+        +--------------+-------------+
                                               |
                                   +-----------v-----------+
                                   | Stage 4: build outputs|
                                   | DuckDB + indexed FASTA|
                                   | GFF3 annotations      |
                                   | reports + logs         |
                                   +-----------+-----------+
                                               |
                                   +-----------v-----------+
                                   | Stage 5: BLAST DBs    |
                                   | phages + proteins     |
                                   | host/private/combined |
                                   +-----------+-----------+
                                               |
                     +-------------------------+-------------------------+
                     |                                                   |
           +---------v---------+                               +---------v---------+
           | analysis container|                               | api container      |
           | pbi package (main)|                               | REST API           |
           +-------------------+                               +-------------------+
```

## Current status

| Subject | Status | Notes |
|---|---|---|
| Pipeline orchestration | ✅ Stable | Snakemake workflow in production use |
| Public data integration | ✅ Stable | Public phage content from PhageScope |
| Private data handling | ✅ Stable | Dedicated ingestion/validation path; see [Private Data Ingestion](guides/private-data-ingestion.md) |
| Host genome resolution | ✅ Stable | Multi-token host parsing + NCBI assembly resolution |
| BLAST databases | ✅ Stable | Five pre-built databases (phages, proteins, hosts, private, combined); see notebook `09_blast_search.ipynb` |
| Analysis workflow | ✅ Stable | Analysis container is the main interface |
| REST API | ✅ Supported | Metadata queries, sequence retrieval, GFF3 annotations, BLAST search, SQL exploration; see [API Reference](api/overview.md) |
| Documentation | 🔄 Updated for v0.6.0 | Structure simplified and aligned with current infrastructure |

## Work in Progress

!!! warning "Host prediction bias"
    Most host assignments in PhageScope are **predicted by [DeepHost](https://academic.oup.com/bib/article/23/1/bbab385/6374063)**, not experimentally validated. This introduces a significant bias: if you build a host prediction model using this data, you are training on already-predicted labels rather than curated ground truth.

    We are in communication with the DeepHost authors to address this issue and improve host assignment quality in future releases.

## Reference Pages

New to the project? Start with the [Installation Guide](guides/installation.md) above. When you need details, these reference pages document each part of the system:

| Reference Page | Description |
|----------------|-------------|
| [Commands](reference/commands.md) | Docker, pipeline, database, and API command reference |
| [API Reference](api/overview.md) | REST API endpoints, parameters, and usage examples |
| [Database](database/overview.md) | Schema structure, statistics, and data sources |
| [Host Resolution](database/host-resolution.md) | How host genomes are resolved from NCBI |
| [Code Structure](developer/code-structure.md) | Repository layout and developer guide |
| [CI Tests](developer/ci-tests.md) | Continuous integration and test suite |

## Need help?

- Use the [Installation Guide](guides/installation.md)
- Read [How it works](guides/how-it-works.md)
- Open issues on [GitHub](https://github.com/ThibaultSchowing/PBI-Scope/issues)

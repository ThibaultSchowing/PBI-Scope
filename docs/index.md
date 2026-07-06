# Welcome to PBI Documentation

**PBI — Phage Bacteria Interactions (v0.4.0)**

## What is PBI?

PBI is a reproducible Docker-first pipeline that prepares phage-host data for analysis and machine learning.

It combines:

1. **Public phage data** from PhageScope (which itself aggregates multiple phage sources)
2. **Optional private datasets** from `private_data/`
3. **Host genome resolution/download** from NCBI RefSeq

Outputs are stored in a shared data volume and consumed through the `pbi` Python package (recommended).

> PBI is **not PhageScope-only** anymore. Private source ingestion is part of the standard workflow when source folders are present.

## Start Here

<div class="grid cards" markdown>

- **[Installation Guide](guides/installation.md)**

  Docker setup, first run, and analysis access.

- **[Story — One Read Overview](guides/storytelling.md)**

  End-to-end narrative of what the tool does and in which order.

- **[Private Data Ingestion](guides/private-data-ingestion.md)**

  Required files, validation rules, and mandatory host sequence requirements.

- **[Analysis Container Usage](guides/analysis-guide.md)**

  VS Code Dev Containers (preferred) and Jupyter Lab workflow.

</div>

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
                                  | reports + logs         |
                                  +-----------+-----------+
                                              |
                    +-------------------------+-------------------------+
                    |                                                   |
          +---------v---------+                               +---------v---------+
          | analysis container|                               | api container      |
          | pbi package (main)|                               | exploration API    |
          +-------------------+                               +-------------------+
```

## Current status

| Subject | Status | Notes |
|---|---|---|
| Pipeline orchestration | ✅ Stable | Snakemake workflow in production use |
| Public data integration | ✅ Stable | Public phage content from PhageScope |
| Private data handling | ✅ Stable | Dedicated ingestion/validation path; see [Private Data Ingestion](guides/private-data-ingestion.md) |
| Host genome resolution | ✅ Stable | Multi-token host parsing + NCBI assembly resolution |
| Analysis workflow | ✅ Stable | Analysis container is the main interface |
| REST API | ✅ Available (exploration) | Metadata queries, single sequence retrieval, SQL queries |
| Documentation | 🔄 Updated for v0.4.0 | Structure simplified and aligned with current infrastructure |

## Need help?

- Use the [Guides overview](guides/overview.md)
- Read [How it works](guides/how-it-works.md)
- Open issues on [GitHub](https://github.com/ThibaultSchowing/PBI/issues)

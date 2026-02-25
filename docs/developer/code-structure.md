# Code Structure

Overview of the PBI project architecture and code organization.

## Project Layout

```
PBI/
├── workflow/              # Snakemake pipeline
│   ├── Snakefile          # Main pipeline definition
│   ├── rules/             # Modular pipeline rules
│   │   ├── phagescope.smk   # Download phage data from PhageScope
│   │   ├── database.smk     # Database creation and optimization
│   │   ├── sequences.smk    # FASTA merging and indexing
│   │   └── hosts.smk        # Host genome resolution and download
│   ├── scripts/           # Processing scripts
│   │   ├── database/        # DuckDB creation, optimization, validation
│   │   ├── preprocessing/
│   │   │   └── mergers/     # Per-feature CSV merger scripts
│   │   ├── sequences/       # FASTA handling + host genome download
│   │   │   ├── download_host_genomes_robust.py  # Multi-host parser + NCBI downloader
│   │   │   ├── assembly_resolver.py             # NCBI assembly lookup
│   │   │   ├── index_sequences.py               # pyfaidx indexing
│   │   │   └── index_individual_hosts.py        # Build host_fasta_mapping.json
│   │   └── utils/           # Report generation utilities
│   ├── config/            # Pipeline configuration
│   │   └── config.yaml      # Main config (NCBI credentials, paths, etc.)
│   ├── envs/              # Conda environment specifications
│   └── dag/               # Workflow DAG visualizations
│
├── src/pbi/               # Python package
│   ├── __init__.py          # Package init + quick_connect(), get_default_paths()
│   ├── sequence_retrieval.py  # SequenceRetriever class
│   ├── negative_examples.py   # NegativeExampleGenerator class
│   └── streaming_dataset.py   # PhageHostStreamingDataset, PhageHostIndexedDataset
│
├── api/                   # REST API (untested)
│   └── app.py               # FastAPI application with endpoints
│
├── notebooks/             # Jupyter notebooks
│   ├── 01_database_exploration.ipynb  # DB stats, quality control
│   ├── 02_sequence_retrieval.ipynb    # Sequence retrieval with pbi package
│   ├── 03_ml_streaming.ipynb          # ML dataset preparation
│   ├── README.md
│   ├── bin/               # Previous versions (kept for reference)
│   └── exploration/       # Development notebooks
│
├── docs/                  # Documentation (MkDocs)
│   ├── index.md
│   ├── guides/            # Installation and usage guides
│   ├── database/          # Database documentation
│   ├── api/               # API reference
│   ├── reference/         # Command reference
│   ├── developer/         # This page
│   └── archive/           # Historical documentation
│
├── tests/                 # Unit tests
│   └── test_multi_host_parsing.py  # Host parsing and resolution tests
│
├── docker-compose.yml     # Docker orchestration (pipeline, analysis, api)
├── Dockerfile.analysis    # Analysis container (Jupyter Lab + pbi package)
├── Dockerfile.api         # API container (FastAPI)
├── setup.py               # Package configuration
└── mkdocs.yml             # Documentation configuration
```

## Key Components

### Snakemake Pipeline

**Location**: `workflow/`

The pipeline orchestrates data download, processing, and database creation:

- **`Snakefile`**: Main workflow definition, includes all rule files
- **`rules/phagescope.smk`**: Downloads phage metadata (CSV) and FASTA archives from PhageScope API for each of 14+ databases
- **`rules/database.smk`**: Merges CSV files, creates and optimizes DuckDB database, generates HTML validation reports
- **`rules/sequences.smk`**: Merges per-database FASTA files, creates pyfaidx indexes
- **`rules/hosts.smk`**: Parses host fields → resolves to NCBI assemblies → downloads host FASTA files → builds `host_fasta_mapping.json`

**Key scripts:**

| Script | Purpose |
|--------|---------|
| `scripts/preprocessing/mergers/merge_phage_metadata.py` | Merge per-database phage CSV files |
| `scripts/preprocessing/mergers/merge_annotated_proteins_metadata.py` | Merge protein annotation CSVs |
| `scripts/database/create_duckdb.py` | Create star-schema DuckDB from merged CSVs |
| `scripts/database/optimize_db.py` | Add indexes and views for performance |
| `scripts/database/validate_db.py` | Generate HTML validation/quality reports |
| `scripts/sequences/download_host_genomes_robust.py` | Multi-host parsing + NCBI download |
| `scripts/sequences/assembly_resolver.py` | NCBI Taxonomy + Assembly API lookups |
| `scripts/sequences/index_individual_hosts.py` | Build `host_fasta_mapping.json` |

### Python Package

**Location**: `src/pbi/`

The PBI package provides the primary interface for data access and ML dataset preparation:

- **`__init__.py`**: Exports main classes, defines `quick_connect()` and `get_default_paths()` (reads `DATA_PATH` env var)
- **`sequence_retrieval.py`**: `SequenceRetriever` — connects to DuckDB and FASTA files, provides metadata query methods, sequence retrieval, and phage-host pair retrieval
- **`negative_examples.py`**: `NegativeExampleGenerator` — generates non-interacting phage-host pairs for ML training (multiple strategies: random, taxonomy-aware, etc.)
- **`streaming_dataset.py`**: `PhageHostStreamingDataset`, `PhageHostIndexedDataset`, `phage_host_collate_fn` — PyTorch-compatible dataset classes for memory-efficient streaming

### REST API

**Location**: `api/`

FastAPI-based REST interface — **currently untested**:

- **`app.py`**: Main API application with endpoints for health check, stats, SQL queries, and FASTA export

### Documentation

**Location**: `docs/`

MkDocs-based documentation (this site):

- **`guides/`**: Installation, how-it-works, analysis usage, pipeline execution
- **`database/`**: Database schema and host resolution details
- **`api/`**: API reference (untested)
- **`reference/`**: Command reference
- **`developer/`**: This page
- **`archive/`**: Historical/development documentation

## Data Flow

```
PhageScope API (14+ databases)
      │
      ▼ [phagescope.smk]
Raw CSVs + compressed FASTA archives → /data/raw/
      │
      ▼ [preprocessing/mergers/]
Merged metadata CSVs + merged FASTA files → /data/intermediate/
      │
      ├──▶ [database.smk] → phage_database_optimized.duckdb → /data/processed/databases/
      └──▶ [sequences.smk] → all_phages.fasta + all_proteins.fasta → /data/processed/sequences/

NCBI RefSeq
      │
      ▼ [hosts.smk]
Individual host FASTA files → /data/processed/sequences/hosts/
host_fasta_mapping.json → /data/processed/sequences/

All outputs → pbi-data Docker volume
      │
      ├──▶ Analysis container (Jupyter Lab, port 8888) via pbi package
      └──▶ API container (FastAPI, port 8000) [untested]
```

## Development Workflow

1. **Data Pipeline**: Modify `workflow/rules/` and `workflow/scripts/` for data processing changes
2. **Python Package**: Update `src/pbi/` for new utilities or ML features
3. **API**: Extend `api/app.py` for new endpoints (test after adding)
4. **Documentation**: Update `docs/` for user-facing changes
5. **Testing**: Add tests to `tests/`

## Configuration Files

- **`workflow/config/config.yaml`**: Pipeline configuration (NCBI credentials, paths, PhageScope DBs)
- **`workflow/envs/*.yaml`**: Conda environment specifications
- **`setup.py`**: Python package metadata and dependencies
- **`mkdocs.yml`**: Documentation configuration
- **`docker-compose.yml`**: Container orchestration (pipeline, analysis, api services)
- **`.gitignore`**: Excludes `data/` directory (too large for git)

## Tests

**Location**: `tests/`

- **`test_multi_host_parsing.py`**: 31 unit tests for host field parsing and resolution logic

Run with:

```bash
python -m pytest tests/
```

## Resources

- [Snakemake Documentation](https://snakemake.readthedocs.io/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [MkDocs Documentation](https://www.mkdocs.org/)

---

For contributing guidelines, see the project README or open an issue on GitHub.


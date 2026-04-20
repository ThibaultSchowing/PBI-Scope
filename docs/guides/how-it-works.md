# How PBI Works

This page explains the internal architecture of PBI: the Snakemake pipeline, the `pbi` Python package, key data files, and the REST API.

## The Big Picture

PBI is a data pipeline that:

1. Downloads phage genomic data from [PhageScope](https://phagescope.deepomics.org/database) (which aggregates 14+ databases)
2. Parses host information from phage metadata and resolves it to NCBI RefSeq assemblies
3. Downloads bacterial reference genomes from NCBI
4. Merges everything into an optimized DuckDB database and indexed FASTA files
5. Exposes this data through a Python package (`pbi`) and optionally a REST API

The ultimate goal is to provide phage-host interaction data in an efficient, structured format for training neural networks and AI models.

---

## The Snakemake Pipeline

**Location**: `workflow/`

The pipeline is orchestrated by [Snakemake](https://snakemake.readthedocs.io/), a workflow manager that tracks file dependencies and only re-runs steps when inputs change.

### Pipeline Stages

```
workflow/Snakefile
     │
     ├── rules/phagescope.smk   → Download phage metadata (CSV) + FASTA archives
     │                             from PhageScope API for each of the 14+ databases
     │
     ├── rules/database.smk     → Merge CSV files, create and optimize DuckDB database,
     │                             generate HTML validation reports
     │
     ├── rules/sequences.smk    → Merge and index phage/protein FASTA files with pyfaidx
     │
     └── rules/hosts.smk        → Parse host fields → resolve to NCBI assemblies →
                                   download host FASTA files → build host_fasta_mapping.json
```

### Configuration

**`workflow/config/config.yaml`** — main pipeline configuration:
- PhageScope API endpoints and database list
- Output paths (all under `/data/` in Docker)
- NCBI credentials (`email`, `api_key`)
- Download parameters (concurrency, retries, timeouts)

### Key Scripts

| Script | Purpose |
|--------|---------|
| `workflow/scripts/preprocessing/mergers/` | Merge per-database CSV files into unified metadata |
| `workflow/scripts/database/create_duckdb.py` | Create the star-schema DuckDB database |
| `workflow/scripts/database/optimize_duckdb.py` | Add indexes and views for query performance |
| `workflow/scripts/database/validate_db.py` | Generate HTML validation reports |
| `workflow/scripts/sequences/` | FASTA merging, indexing, host genome downloads |
| `workflow/scripts/sequences/download_host_genomes_robust.py` | Multi-host parsing and NCBI download |

---

## The `pbi` Python Package

**Location**: `src/pbi/`

The `pbi` package is the primary way to interact with PBI data in Python. It handles database connections, sequence retrieval, and machine learning dataset preparation.

### Main Classes

#### `SequenceRetriever`

The central class for accessing the database and FASTA files.

```python
from pbi import quick_connect

# In Docker (paths auto-detected via DATA_PATH environment variable)
retriever = quick_connect()

# Manual initialization
from pbi import SequenceRetriever
retriever = SequenceRetriever(
    db_path="/data/processed/databases/phage_database_optimized.duckdb",
    phage_fasta_path="/data/processed/sequences/all_phages.fasta",
    protein_fasta_path="/data/processed/sequences/all_proteins.fasta",
    host_mapping_path="/data/processed/sequences/host_fasta_mapping.json"
)
```

**Key methods:**
- `get_phage_metadata(where=None, limit=None)` — query phage metadata
- `get_host_metadata(where=None)` — query host metadata
- `get_phage_host_pairs(where=None, limit=None, host_contig_mode='concat')` — get linked phage-host pairs
- `get_sequences_by_ids(ids, sequence_type='phage')` — retrieve FASTA sequences
- `get_stats()` — database and file statistics
- `export_fasta(df, path, id_col)` — export sequences to FASTA

#### `NegativeExampleGenerator`

Generates negative training examples (non-interacting phage-host pairs) for machine learning.

```python
from pbi import NegativeExampleGenerator

neg_gen = NegativeExampleGenerator(retriever)
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=pairs,
    strategy='mixed',
    positive_ratio=0.5
)
```

#### `PhageHostStreamingDataset` / `PhageHostIndexedDataset`

PyTorch-compatible dataset classes for memory-efficient streaming through large datasets.

```python
from pbi import PhageHostStreamingDataset, PhageHostIndexedDataset, phage_host_collate_fn
from torch.utils.data import DataLoader

dataset = PhageHostStreamingDataset(retriever, where_clause="p.Lifestyle = 'Lytic'")
loader = DataLoader(dataset, batch_size=32, collate_fn=phage_host_collate_fn)
```

### Key Data Files

The `pbi` package works with these key files produced by the pipeline:

| File | Location | Description |
|------|---------|-------------|
| `phage_database_optimized.duckdb` | `/data/processed/databases/` | Main DuckDB database with all phage metadata |
| `all_phages.fasta` + `.fai` | `/data/processed/sequences/` | All phage genome sequences, indexed with pyfaidx |
| `all_proteins.fasta` + `.fai` | `/data/processed/sequences/` | All protein sequences, indexed with pyfaidx |
| `host_fasta_mapping.json` | `/data/processed/sequences/` | Maps host assembly IDs to their FASTA file paths |
| Individual host FASTA files | `/data/processed/sequences/hosts/` | One FASTA file per downloaded host assembly |

#### The `host_fasta_mapping.json` File

This JSON file is the key index for host genome access. It maps each host assembly accession to the path of its downloaded FASTA file:

```json
{
  "GCF_000005845.2": "/data/processed/sequences/hosts/Escherichia_coli_GCF_000005845.2.fna",
  "GCF_000006945.2": "/data/processed/sequences/hosts/Salmonella_enterica_GCF_000006945.2.fna",
  ...
}
```

The `SequenceRetriever` uses this file to efficiently retrieve individual host sequences without loading all host FASTA data into memory.

### How `quick_connect()` Works

```python
def quick_connect():
    paths = get_default_paths()  # Reads DATA_PATH + PBI_PRIVATE_DATA_DIR
    return SequenceRetriever(
        db_path=paths['database'],
        phage_fasta_path=paths['phage_fasta'],
        protein_fasta_path=paths['protein_fasta'],
        host_mapping_path=paths['host_mapping'],  # Uses host_fasta_mapping.json
        private_phage_mapping_path=paths['private_phage_mapping'],
    )
```

In Docker, `DATA_PATH=/data/processed` and `PBI_PRIVATE_DATA_DIR=/private-data`, so `quick_connect()` can route both public and private sequence lookups.

---

## Host Resolution Process

Host genome resolution is a multi-stage process because phage metadata contains complex, semicolon-separated host fields like:

```
NA;GCA 900066335.1;UBA9502;Blautia obeum
```

### Resolution Stages

1. **Parsing** (`phage_host_candidates.csv`): Each host field is split into tokens, classified as assembly accession, species name, or other identifier.

2. **Resolution** (`phage_host_assemblies.csv`): Each token is resolved to an NCBI assembly accession via:
   - Direct assembly lookup (for `GCA_`/`GCF_` accessions)
   - NCBI Taxonomy + Assembly search (for species names)
   - Fallback species search (for other identifiers)

3. **Download**: Unique assemblies are downloaded from NCBI RefSeq, deduplicated across phages.

4. **Mapping**: `host_fasta_mapping.json` is built, mapping host IDs to downloaded FASTA files.

See the [Host Resolution Details](../database/host-resolution.md) page for full documentation.

---

## The REST API

**Location**: `api/`

The REST API is built with [FastAPI](https://fastapi.tiangolo.com/) and provides HTTP endpoints for querying the database and retrieving sequences.

> ⚠️ **Note**: The REST API is currently a **Work In Progress** and is not the recommended way to interact with PBI data. It has not been updated for host management. For analysis and machine learning, use the [analysis container](analysis-guide.md) with the `pbi` Python package directly.

### How the API Works

```python
# api/app.py — simplified structure
from fastapi import FastAPI
import duckdb

app = FastAPI()

# On startup, connects to DuckDB and indexes FASTA files
# Exposes endpoints for health checks, SQL queries, and sequence retrieval
```

Key endpoints:
- `GET /health` — health check
- `GET /stats` — database statistics
- `POST /query` — execute SQL queries
- `POST /phages` — retrieve phage sequences
- `POST /phages/fasta` — export FASTA format

See the [API Reference](../api/overview.md) for full documentation.

---

## Docker Services

The `docker-compose.yml` defines three services:

| Service | Image | Purpose | Port |
|---------|-------|---------|------|
| `pipeline` | `pbi-pipeline` | Runs Snakemake to build the database | — |
| `analysis` | `pbi-analysis` | Jupyter Lab with `pbi` package pre-installed | 8888 |
| `api` | `pbi-api` | FastAPI REST server | 8000 |

All services share the `pbi-data` Docker volume (read-only for analysis and API, read-write for pipeline).

---

## Data Flow Summary

```
PhageScope API (14+ databases)
         │
         ▼  [phagescope.smk]
   Raw CSVs + compressed FASTA archives
   /data/raw/
         │
         ▼  [database.smk + sequences.smk]
   Merged metadata + merged FASTA files
   /data/intermediate/
         │
         ▼  [database.smk]
   phage_database_optimized.duckdb   ←── all phage/protein metadata
   /data/processed/databases/
         │
   all_phages.fasta + .fai           ←── phage genome sequences
   all_proteins.fasta + .fai         ←── protein sequences
   /data/processed/sequences/
         │
NCBI RefSeq
         │
         ▼  [hosts.smk]
   Individual host FASTA files       ←── bacterial reference genomes
   host_fasta_mapping.json           ←── index: host_id → FASTA path
   /data/processed/sequences/
         │
         ▼
   pbi Python package (SequenceRetriever)
         │
         ├──▶ Jupyter Lab notebooks (analysis container, port 8888)
         └──▶ REST API (api container, port 8000) [untested]
```

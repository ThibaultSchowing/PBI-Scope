# PBI-Scope — AI Agent Guide

## What is this?

Dockerized phage-host bioinformatics pipeline that builds a unified data product from PhageScope public data, optional private datasets, and NCBI RefSeq host genomes. Outputs are accessed via the `pbi` Python package, a REST API, or Jupyter notebooks — all running in Docker containers.

See [README.md](README.md) for full description and citation.

## Repository map

| Path | Purpose |
|------|---------|
| `workflow/` | Snakemake pipeline (`rules/`, `scripts/`, `config/`, `schemas/`, `envs/`) |
| `src/pbi/` | Python package (`SequenceRetriever`, `BlastSearcher`, `APIClient`, etc.) |
| `api/` | FastAPI REST API |
| `tests/` | pytest suite (unit + integration + CI smoke) |
| `docs/` | MkDocs documentation |
| `notebooks/` | Jupyter examples (00–09) |
| `scripts/` | Standalone diagnostic/validation scripts |

## Build & test commands

```bash
# Build pipeline image (on remote server)
docker compose build pipeline

# Run full pipeline (on remote server, ~12-18 hours)
docker compose run --rm pipeline

# Run tests locally (no Docker needed for unit tests)
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_fasta_ids_and_naming.py -v

# Run CI subset (2 of 26 sources, inside Docker)
docker compose run --rm pipeline snakemake --cores 2 --use-conda --snakefile workflow/Snakefile.ci
```

> **Note:** Pipeline execution is performed on a remote server. Development and unit testing are done on a local machine without Docker containers. CI tests run inside a Docker container against real pipeline output.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATA_PATH` | `/data/processed` | Path to processed data (DB, FASTA, GFF3) |
| `PBI_PRIVATE_DATA_DIR` | `/private-data` | Private data mount root |
| `PBI_LOGS_DIR` | `/pipeline-logs` | Pipeline logs and reports mount |
| `NCBI_EMAIL` | — | NCBI API email (required) |
| `NCBI_API_KEY` | — | NCBI API key (optional, 10x rate limit) |
| `UID` / `GID` | `1000` | Host user ID for container file ownership |

## Critical rules

1. **Never edit files under `data/` or `/data/`** — pipeline outputs are immutable. Delete and rebuild instead.
2. **FASTA keys:** phage = `token0` (Phage_ID), protein = `token1` (Protein_ID). See `src/pbi/fasta_ids.py`. Old Prodigal headers (`>Protein # 2 # 685`) use `token0` when `token1 == "#"`.
3. **Phage_ID is NOT globally unique** — `(Phage_ID, Source_DB)` is the composite key. IMGVR and MetaVR share `IMGVR_UViG_*` IDs.
4. **Private data paths:** always use `PBI_PRIVATE_DATA_DIR` env var, never hardcode `/private-data`.
5. **Schema contracts:** `workflow/schemas/*.yaml` define required/optional columns. See `docs/developer/code-structure.md#schema-contracts` for the change matrix.
6. **Host resolution cache TTL:** 120 days. Delete `/pipeline-logs/csv/host_token_resolution_cache.json` to force refresh.
7. **genome_stats timeout:** 60s per file. Bad-block files are recorded as `stats_failed`, not fatal.

## Common pitfalls

- **Protein FASTA headers:** `>Phage Protein Source` (token1 = Protein_ID). After `merge_protein_fasta.py`, old `>Phage Protein` becomes `>Phage Protein Source`.
- **Cross-source duplicate Phage_ID:** IMGVR and MetaVR share `IMGVR_UViG_*` IDs — deduplicate on `(Phage_ID, Source_DB)`.
- **Host resolution cache:** 120-day TTL. Stale cache is logged as `⏰ Cache stale: ...` and re-resolved.
- **Private data ingestion:** `src/pbi/private_data.py` computes fingerprints but `ingest_private_sources_into_db()` uses `DELETE + INSERT BY NAME` without transaction — partial crash can leave half-deleted rows.
- **DuckDB build:** `create_duckdb.py` uses `read_csv(ignore_errors=true)` + `TRY_CAST` — rejected rows are silently dropped. Check `validate_db.py` reports for data quality.

## Detailed documentation

- **Architecture & code structure:** [`docs/developer/code-structure.md`](docs/developer/code-structure.md)
- **CI pipeline & smoke tests:** [`docs/developer/ci-tests.md`](docs/developer/ci-tests.md)
- **Installation & quick start:** [`docs/guides/installation.md`](docs/guides/installation.md)
- **Schema contracts & change matrix:** [`docs/developer/code-structure.md#schema-contracts`](docs/developer/code-structure.md#schema-contracts)
- **AI workflow & common tasks:** [`docs/developer/ai-workflow.md`](docs/developer/ai-workflow.md)
- **Notebook examples:** [`notebooks/README.md`](notebooks/README.md)
- **Future development:** [`docs/future-steps.md`](docs/future-steps.md)

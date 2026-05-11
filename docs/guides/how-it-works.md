# How PBI Works

PBI orchestrates a full phage-host data pipeline using Snakemake and Docker.

## Data inputs

- **Public phage input**: PhageScope exports
- **Optional private input**: `private_data/<Source_DB>/`
- **Host genome source**: NCBI RefSeq

## Public-data pinning configuration

`workflow/config/config.yaml` now includes:

- `public_data_provider.*` (`name`, `release`, `snapshot_date`, `schema_profile`, `api_base_url`, `provenance_mode`)
- `public_data_provenance.*` controls (`require_release_or_snapshot`, checksum/header capture, schema-mismatch behavior, and manifest output paths)

This keeps current `*_urls` maps intact while adding a provider/version foundation for future `phagescope_v1`/`phagescope_v2` transitions.

## Pipeline stages

```text
workflow/Snakefile
   |
   +-- phagescope.smk  -> download public phage metadata/FASTA + provenance manifests
   +-- database.smk    -> merge metadata + build/optimize DuckDB
   +-- sequences.smk   -> build/index phage & protein FASTA
   +-- hosts.smk       -> parse host fields, resolve assemblies, download host FASTA
```

When private source folders are present, validation and private mapping preparation run automatically before final outputs are finalized.

## Main outputs

- `phage_database_optimized.duckdb`
- `all_phages.fasta(.fai)`
- `all_proteins.fasta(.fai)`
- `host_fasta_mapping.json`
- `private_phage_mapping.json` (if private sources exist)
- `public_data_manifest.json/.csv` (public-source provenance)
- `pipeline_run_provenance.json/.csv` (run-level provider pinning)
- reports and logs

## Access model

- **Primary**: `pbi` package in the analysis container
- **REST API**: currently not supported for sequence-heavy retrieval (performance limitation)

## Why host data is handled outside DuckDB

Host genomes are large and variable; they are stored as individual FASTA files and mapped through JSON/CSV link files for efficient retrieval.

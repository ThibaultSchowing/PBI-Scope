# How PBI Works

PBI orchestrates a full phage-host data pipeline using Snakemake and Docker.

## Data inputs

- **Public phage input**: PhageScope exports
- **Optional private input**: `private_data/<Source_DB>/`
- **Host genome source**: NCBI RefSeq

## Pipeline stages

```text
workflow/Snakefile
   |
   +-- phagescope.smk  -> download public phage metadata/FASTA
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
- reports and logs

## Access model

- **Primary**: `pbi` package in the analysis container
- **REST API**: currently not supported for sequence-heavy retrieval (performance limitation)

## Why host data is handled outside DuckDB

Host genomes are large and variable; they are stored as individual FASTA files and mapped through JSON/CSV link files for efficient retrieval.

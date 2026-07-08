# PBI-Scope Story — one read walkthrough

This page explains the full PBI-Scope flow in execution order.

For setup and commands, use the [Installation Guide](installation.md).

## 1) What PhageScope brings

PhageScope aggregates several public phage resources into consistent exports. PBI-Scope uses those exports as its main **public** phage input (metadata and FASTA).

## 2) Why Docker is central

PBI-Scope relies on Docker to keep paths, environments, and large intermediate data consistent.

- `pipeline` builds data
- `analysis` reads data for notebooks/scripts
- `api` provides REST API for exploration

Named volumes and bind mounts keep outputs persistent and auditable.

## 3) What the pipeline does (in order)

1. **Download public phage data** from PhageScope sources
2. **Merge and normalize metadata** with schema contracts
3. **Build merged FASTA files** for phages and proteins + create indexes
4. **Validate private sources** (if folders exist in `private_data/`)
5. **Prepare private mappings** (private phages and hosts)
6. **Parse host fields** from phage metadata
7. **Resolve hosts** to NCBI assemblies
8. **Download host FASTAs** from NCBI RefSeq
9. **Create DuckDB database** and optimize analytical access
10. **Store reports and logs** (validation, quality, failure logs)

## 4) Resulting data product

After completion, PBI-Scope provides:

- DuckDB database for metadata exploration
- Indexed phage/protein FASTA files
- Host FASTA mapping for host retrieval
- Private phage mapping when private sources are present
- Pipeline logs and reports for traceability

## 5) How users work with it

The recommended interface is the analysis container with the `pbi` package.

- Use VS Code Dev Containers for full IDE workflow (preferred)
- Use Jupyter Lab for notebook-first workflow
- Use the REST API for quick exploration and metadata lookups

## 6) Where to go next

- [Installation](installation.md)
- [Analysis container](analysis-guide.md)
- [API Reference](../api/overview.md)
- [Private data ingestion](private-data-ingestion.md)
- [Notebooks README](https://github.com/ThibaultSchowing/PBI/blob/main/notebooks/README.md)

# Private Data Ingestion

PBI supports optional ingestion of private datasets placed inside the `private_data/`
directory at the repository root.

## Quick start

1. Create a subdirectory for each private source inside `private_data/`:

```text
private_data/
  Project_A/
    metadata.csv
    phage.fasta
    host.fasta
  Experiment_1/
    metadata.csv
    phage.fasta
    host.fasta
```

2. Validate before running the pipeline:

```bash
# From the repository root (requires `pip install -e .`)
pbi validate-private
```

3. Run the pipeline as usual. Private sources are detected automatically.

```bash
docker compose run --rm pipeline
```

Private sequence retrieval is prepared automatically during the workflow:

- Private phage FASTA records are kept in a dedicated private FASTA and indexed separately from the public PhageScope FASTA.
- Private host FASTA records are split to per-`Host_ID` files, added to `host_fasta_mapping.json`, and indexed with the same host indexing workflow.

When private source directories are removed from `private_data/`, rerunning the pipeline
re-synchronizes the manifest and removes stale private records from the database.

## Required files per source directory

| File | Required |
|------|----------|
| `metadata.csv` | ✅ |
| `phage.fasta` | ✅ |
| `host.fasta` | Optional (recommended) |

## `metadata.csv` columns

Required (case-sensitive):

| Column | Description |
|--------|-------------|
| `Phage_ID` | Unique phage identifier matching `phage.fasta` |
| `Host_ID` | Unique host identifier matching `host.fasta` |
| `Host_name` | Human-readable host species name |
| `Source_DB` | Must match the subdirectory name exactly |
| `interaction` | `temperate` or `virulent` (case-insensitive, stored lowercase) |

Optional columns: any extra columns are preserved in `private_entity_attributes`.

## FASTA identifier matching rules

- The sequence identifier is the **first whitespace-delimited token** of each `>` header line.
- `Phage_ID` values must each appear as an identifier in `phage.fasta`.
- If `host.fasta` is provided, `Host_ID` values must each appear as an identifier in it.
- Duplicate FASTA identifiers in the same file are rejected.

## Duplicate row policy

Rows that are duplicated on (`Phage_ID`, `Host_ID`, `Source_DB`) are accepted but
deduplicated at ingestion (first occurrence kept).

## Database synchronization notes

- `fact_phages.source_type` distinguishes public (`public`) vs private (`private`) phages.
- `private_phage_host_associations` stores `Phage_ID`, `Host_ID`, `Source_DB`, and `source_type` so private links can be traced back to their source dataset during resynchronization.

## Running `validate-private` without Docker

The `pbi` package installs a standalone CLI tool that runs entirely locally:

```bash
# Install the package (needed once)
pip install -e .

# From the repository root — automatically uses ./private_data/
pbi validate-private

# Or point to an arbitrary root
pbi validate-private --path /some/other/directory
```

No Docker required; no pipeline run triggered.

## Container integration (automatic)

`docker-compose.yml` always mounts `./private_data` at `/private-data` inside the
container (read-only). The pipeline configuration uses:

```yaml
private_data_root: "/private-data"
```

No additional environment variables or config changes are needed.

## Logs and reports

All HTML reports and log files are written to `./pipeline_logs/` at the repository root
(bind-mounted inside the container). Open the `.html` files directly in a browser:

```text
pipeline_logs/
  reports/
    database_validation.html
    phage_metadata_report.html
    ...
  logs/
    host_download.log
    host_download_failures.log
    ...
```

## Failure handling

- Private ingestion is non-blocking.
- Invalid or failed private sources are skipped; PhageScope data is always produced.
- End-of-run logs include an ingestion summary (sources ingested / skipped).

## README template

Use this template inside each private source directory:

```text
# <Source_DB>

## Files
- metadata.csv    — phage-host interaction table
- phage.fasta     — phage sequences (FASTA)
- host.fasta      — host sequences (FASTA)

## metadata.csv column notes
- Source_DB must equal "<Source_DB>" (directory name)
- interaction: temperate | virulent

## FASTA IDs
- Identifiers are the first whitespace-delimited token of each '>' header line.
- All Phage_ID / Host_ID values in metadata.csv must appear in the respective FASTA.

## Optional custom columns
- <column_name>: <description>
```

# Provenance and Version Pinning

This page explains how PBI pins upstream public data context and how to audit what was ingested.

## What is pinned

Public-source pinning is configured in `workflow/config/config.yaml`:

- `public_data_provider.name`
- `public_data_provider.release`
- `public_data_provider.snapshot_date`
- `public_data_provider.schema_profile`
- `public_data_provider.api_base_url`
- `public_data_provider.provenance_mode`

These values are recorded for every run, so downstream users can identify exactly which upstream snapshot/profile was used.

## How provenance is captured

During each public file download, PBI writes a sidecar record with:

- source URL and local path
- retrieval timestamp
- file size
- optional checksum (`sha256`)
- optional HTTP headers (`ETag`, `Last-Modified`)
- detected tabular columns + schema fingerprint
- status/error message

Then all sidecars are consolidated into:

- `pipeline_logs/csv/public_data_manifest.json`
- `pipeline_logs/csv/public_data_manifest.csv`
- `pipeline_logs/csv/pipeline_run_provenance.json`
- `pipeline_logs/csv/pipeline_run_provenance.csv`

## DuckDB provenance tables

The database build loads these files into:

- `dataset_provenance`
- `pipeline_run_provenance`

Quick checks:

```sql
SELECT status, COUNT(*) FROM dataset_provenance GROUP BY status;
SELECT provider_release, provider_snapshot_date, provider_schema_profile FROM pipeline_run_provenance;
```

## Private-data ingestion diagnostics

Private datasets are validated source-by-source from `private_data/<Source_DB>/`.
Validation output is written to:

- `private_data/private_manifest.json` (or `/private-data/private_manifest.json` in containers)

Important behavior:

- only `is_valid: true` sources are ingested
- invalid sources are skipped and listed with explicit `errors`
- `Source_DB` in each `metadata.csv` must match the folder name exactly

If a notebook query like `Source_DB = 'test_private'` returns `0`, first verify available private sources:

```sql
SELECT Source_DB, source_type, COUNT(*) AS phage_count
FROM fact_phages
GROUP BY Source_DB, source_type
ORDER BY source_type, Source_DB;
```

Then inspect:

- `private_manifest.json` for skipped sources and validation errors
- `pipeline_logs/logs/host_download_failures.log` for host-resolution/download failures
- `dataset_provenance` rows with `status = 'failed'` for public-source provenance failures

## Common error indicators

- **Source not ingested**: source missing from `fact_phages`, present in manifest with `is_valid: false`
- **Source name mismatch**: manifest error `Source_DB mismatch: expected only '<folder>'`
- **Public provenance failure**: `dataset_provenance.status='failed'` with non-empty `error_message`
- **Schema drift warning/failure**: schema fingerprint change in download logs and provenance record

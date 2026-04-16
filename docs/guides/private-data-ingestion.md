# Private Data Ingestion

PBI supports optional ingestion of private datasets mounted at runtime (not committed to git).

## Directory Contract

Provide one or more **private roots**.  
Each immediate subdirectory is treated as one private source (`source_db`):

```text
<private_root>/
  Project_A/
    metadata.csv
    phage.fasta
    host.fasta
  Experiment_1/
    metadata.csv
    phage.fasta
    host.fasta
```

## Required files

- `metadata.csv`
- `phage.fasta`
- `host.fasta`

## `metadata.csv` columns

Required (case-sensitive):

- `Phage_ID`
- `Host_ID`
- `Host_name`
- `Source_DB` (must match directory name exactly)
- `interaction` (`temperate` or `virulent`, case-insensitive input, stored lowercase)

Optional:

- Any extra columns are allowed and preserved in `private_entity_attributes`.

## FASTA identifier matching rules

- For both `phage.fasta` and `host.fasta`, the sequence identifier is the **first whitespace-delimited token** of each header line (`>` record).
- `Phage_ID` values must exist in `phage.fasta` identifiers.
- `Host_ID` values must exist in `host.fasta` identifiers.
- Duplicate FASTA identifiers are rejected.

## Duplicate row policy

- Duplicate rows on (`Phage_ID`, `Host_ID`, `Source_DB`) are accepted but deduplicated at ingestion.

## Validate before pipeline run

```bash
pbi validate-private --path /mnt/private_data
```

You can pass multiple roots:

```bash
pbi validate-private --path /mnt/private_data --path /mnt/other_private_root
```

Validation output is grouped by source directory with actionable errors.

## Pipeline configuration

In `workflow/config/config.yaml`:

- `private_ingestion_enabled: true|false`
- `private_data_roots: []` (list of root paths)

When enabled, PBI discovers all source directories under the configured roots and writes a manifest used for deterministic rebuilds.

## Runtime behavior and failure handling

- Private ingestion is non-blocking.
- If a source fails validation/ingestion, that source is skipped.
- PhageScope data still builds and the final database is produced.
- End-of-run logs include private source ingestion/skipping summary.

## README template for private sources

Use this template in each private source directory:

```text
# <Source_DB>

## Files
- metadata.csv
- phage.fasta
- host.fasta

## Notes
- Source_DB in metadata.csv must be "<Source_DB>"
- interaction values: temperate | virulent
- FASTA IDs must match metadata IDs (first token in FASTA headers)

## Optional custom columns
- <column_name>: <meaning>
```

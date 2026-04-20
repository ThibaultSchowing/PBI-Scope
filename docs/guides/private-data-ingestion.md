# Private Data Ingestion

PBI can ingest private sources from `private_data/` in addition to public PhageScope data.

## Required per source

```text
private_data/
  <Source_DB>/
    metadata.csv
    phage.fasta
    hosts/
      <Host_ID>.fna
```

## Mandatory rules

- `metadata.csv` is required
- `phage.fasta` is required
- host sequences are required as `hosts/<Host_ID>.fna`
- every `Host_ID` in metadata must map to a host FASTA file
- every `Phage_ID` in metadata must exist in `phage.fasta`

## Validate before pipeline

```bash
pbi validate-private
```

## Runtime behavior

- Valid private sources are ingested and linked with `source_type=private`
- Invalid sources are skipped (public pipeline still completes)
- Re-running pipeline synchronizes removals/additions

## Output mappings

- `private_phage_mapping.json` routes private phage retrieval
- `host_fasta_mapping.json` includes host paths (public + private)

## Logs

In Docker runs, logs/reports are available in `./pipeline_logs/`.

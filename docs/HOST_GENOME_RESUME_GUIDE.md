# Host Genome Download Resume Capability

## Overview

The host genome downloader (`download_host_genomes.py`) now includes **automatic resume capability** to handle workflow interruptions gracefully. If the download process is interrupted (e.g., network failure, system crash, manual stop), you can simply restart the workflow and it will continue from where it left off.

## How It Works

### Status Tracking

The downloader maintains a JSON status file (`host_download_status.json`) that tracks the download state for each unique host species:

- **`success`**: Genome was successfully downloaded
- **`failed`**: Download failed after all retry attempts
- **`not_attempted`**: Not yet processed (or being retried)

### Status File Location

The status file is automatically created in the same directory as the metadata output:

```
data/intermediate/csv/merged/host_download_status.json
```

### Resume Behavior

When you restart the downloader:

1. **Loads existing status**: Reads `host_download_status.json` if it exists
2. **Skips successful downloads**: Species marked as `success` are not re-downloaded
3. **Retries failed downloads**: Species marked as `failed` are attempted again
4. **Reconstructs metadata**: For skipped species, metadata is reconstructed from existing genome files

### Atomic Updates

The status file uses atomic write operations (write to temp file, then rename) to prevent corruption even if the process is killed mid-write.

## Usage

### Running the Downloader

No special flags needed! Resume capability is automatic:

```bash
# Via Snakemake (recommended)
snakemake download_host_genomes --use-conda

# Standalone
python workflow/scripts/sequences/download_host_genomes.py \
  --phage-csv data/intermediate/csv/merged/merged_phage_metadata.csv \
  --output-dir data/intermediate/fasta/hosts \
  --metadata data/intermediate/csv/merged/host_metadata.csv
```

### Interrupting the Download

You can safely interrupt the download at any time:

- **Ctrl+C**: Keyboard interrupt
- **Kill process**: `kill <PID>`
- **System crash**: Power loss, OOM kill, etc.

### Resuming After Interruption

Simply run the same command again:

```bash
snakemake download_host_genomes --use-conda
```

The downloader will:
- Show resume summary in the logs
- Skip already-downloaded species
- Continue with remaining species

### Example Output

```
🔧 Initialized HostGenomeDownloader
   Phage CSV: data/intermediate/csv/merged/merged_phage_metadata.csv
   Output directory: data/intermediate/fasta/hosts
   Metadata output: data/intermediate/csv/merged/host_metadata.csv
   Status file: data/intermediate/csv/merged/host_download_status.json
   NCBI email: phage.pipeline@example.com
   Resuming: 42 successful, 3 failed from previous run

📊 Resume Summary:
   Total species: 150
   Already completed: 42
   To process: 108
```

## Managing the Status File

### View Status

Check the current status of all species:

```bash
cat data/intermediate/csv/merged/host_download_status.json | jq
```

Example output:
```json
{
  "Escherichia coli": "success",
  "Staphylococcus aureus": "success",
  "Pseudomonas aeruginosa": "failed",
  "Bacillus subtilis": "success"
}
```

### Count Status Types

```bash
# Count successful downloads
jq '[.[] | select(. == "success")] | length' host_download_status.json

# Count failed downloads
jq '[.[] | select(. == "failed")] | length' host_download_status.json
```

### Reset Status (Force Re-download)

To force re-download of all or specific species:

**Option 1: Delete status file** (re-download everything):
```bash
rm data/intermediate/csv/merged/host_download_status.json
```

**Option 2: Edit status file** (re-download specific species):
```bash
# Edit the JSON file manually to change status to "not_attempted"
# or remove the entry entirely
```

**Option 3: Delete genome files** (re-download missing files):
```bash
# Delete specific genome file
rm data/intermediate/fasta/hosts/Escherichia_coli_*.fna

# The downloader will detect the missing file and re-download
```

### Clear Failed Downloads

To retry all failed downloads, edit the status file to remove or change failed entries:

```bash
# Option 1: Remove all failed entries
jq 'with_entries(select(.value != "failed"))' host_download_status.json > temp.json
mv temp.json host_download_status.json

# Option 2: Change failed to not_attempted
jq 'map_values(if . == "failed" then "not_attempted" else . end)' host_download_status.json > temp.json
mv temp.json host_download_status.json
```

## Metadata Reconstruction

When resuming, the downloader reconstructs metadata for already-downloaded species by:

1. **Finding genome files**: Scans output directory for matching `.fna` files
2. **Extracting information**: Parses Host_ID and accession from filename
3. **Calculating statistics**: Computes genome length and GC content from FASTA file
4. **Using file metadata**: Uses file modification time as download date

Reconstructed metadata has `Source: "reconstructed"` to distinguish from fresh downloads.

## Troubleshooting

### Status File Corrupted

If the status file becomes corrupted (invalid JSON), the downloader will:
- Log a warning: `Could not load status file: <error>. Starting fresh.`
- Start with an empty status (re-download all)
- Create a new, valid status file

### Metadata Reconstruction Fails

If reconstruction fails for a species marked as successful:
- Warning logged: `Could not reconstruct metadata, will re-download`
- Status changed to `not_attempted`
- Species will be re-downloaded

### Different Number of Species

If the number of species in your phage metadata CSV changes:
- **New species**: Will be downloaded
- **Removed species**: Status file still has entry but species won't be processed

This is harmless. To clean up unused entries:
```bash
# Manually edit status file or regenerate by deleting and re-running
rm host_download_status.json
```

## Best Practices

1. **Don't manually edit genome files**: If you modify downloaded genome files, delete the status entry or the file itself to trigger re-download

2. **Keep status file with data**: The status file is part of your data provenance. Consider backing it up or version controlling it.

3. **Monitor failures**: Check the status file periodically to identify persistent failures:
   ```bash
   jq 'to_entries | map(select(.value == "failed")) | from_entries' host_download_status.json
   ```

4. **Resume quickly after interruption**: The sooner you resume, the less likely NCBI assemblies will change

## Comparison with Optimized Version

Both `download_host_genomes.py` and `download_host_genomes_optimized.py` support resume capability:

| Feature | Original | Optimized |
|---------|----------|-----------|
| Resume capability | ✅ JSON status file | ✅ SQLite database + JSON |
| Status tracking | Success/Failed | Success/Failed/Skipped + reason |
| Metadata reconstruction | ✅ From files | ✅ From database |
| Cache management | Basic | Advanced |
| Progress tracking | Basic summary | Real-time ETA |

For most use cases, the original version's resume capability is sufficient. The optimized version provides additional features like detailed failure categorization and intelligent caching.

## See Also

- [Migration Guide: Optimized Downloader](MIGRATION_GUIDE_OPTIMIZED_DOWNLOADER.md)
- [FASTA Download Guide](FASTA_DOWNLOAD_GUIDE.md)
- [Genome Download Optimization](genome_download_optimization.md)

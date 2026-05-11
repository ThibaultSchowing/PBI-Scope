# Pipeline Logs Reference

All files produced by the PBI pipeline that are useful for monitoring and post-run analysis are written under **`pipeline_logs/`** (bind-mounted from `./pipeline_logs` in the repository root to `/pipeline-logs` inside the container).

The directory is organised into three sub-directories:

| Sub-directory | Purpose |
|---|---|
| `logs/` | Plain-text and CSV logs emitted during rule execution |
| `reports/` | HTML validation reports and the host-status summary CSV |
| `csv/` | Intermediate CSV/JSON data files useful for log analysis |

> **Local runs (without Docker)** — the `PBI_LOGS_DIR` environment variable controls where these files land.  When unset, the Snakefile falls back to the value of `PBI_DATA_DIR` (default: `data/`), so the same relative paths appear under `data/` instead of `pipeline_logs/`.

---

## `logs/` — Execution logs

### `host_download.log`

**Config key**: `host_download_log`

Verbose log of the `download_host_genomes` rule.  Each downloaded, skipped, or failed genome is recorded here with timestamps.

```bash
# Watch progress in real time
tail -f pipeline_logs/logs/host_download.log

# Count successful downloads
grep -c "✅" pipeline_logs/logs/host_download.log

# List failed accessions
grep "❌" pipeline_logs/logs/host_download.log
```

---

### `host_download_failures.log`

**Config key**: `host_failure_log`

Structured failure log written at the end of `download_host_genomes`.  Each line describes a host token that could not be resolved or a genome that could not be downloaded, with the reason categorised.

Common categories:

- `No assembly found` — species absent from NCBI RefSeq
- `GTDB identifier` — placeholder IDs such as `sp001234567` (filtered automatically)
- `Generic name` — e.g. `Acidovorax sp.` without strain information
- `Network error` — transient NCBI connection failures
- `Empty / placeholder` — `-`, `unknown host`, etc.

---

### `host_fasta_qc.csv`

**Config key**: `host_fasta_qc_log`

CSV produced by the `index_individual_host_sequences` rule.  One row per FASTA file that was evaluated.  Load directly with pandas for analysis.

Key columns:

| Column | Description |
|---|---|
| `Host_ID` | Unique host identifier |
| `fasta_path` | Absolute path to the FASTA file |
| `status` | `indexed` / `rejected` / `warning` |
| `reason` | Human-readable reason for rejection or warning |
| `duplicate_headers` | Number of duplicate sequence identifiers found |
| `identical_sequences` | Number of identical sequences detected |

```python
import pandas as pd
qc = pd.read_csv("pipeline_logs/logs/host_fasta_qc.csv")

# Files rejected due to duplicate headers
print(qc[qc["status"] == "rejected"])

# Files with duplicate sequence content (indexed but flagged)
print(qc[qc["identical_sequences"] > 0])
```

---

### `create_host_mapping.log`

**Config key**: `create_host_mapping_log`

Log of the `create_host_mapping` rule, which builds the JSON mapping from `Host_ID` to individual FASTA file paths.  Useful for diagnosing missing or mismatched files.

---

### `index_individual_host_sequences.log`

**Config key**: `index_individual_host_sequences_log`

Log of the `index_individual_host_sequences` rule.  Records which FASTA files were indexed with pyfaidx and which were rejected by the QC checks.

---

### `create_host_status_report.log`

**Config key**: `create_host_status_report_log`

Log of the `create_host_status_report` rule, which joins the four host-tracking CSVs into `host_status_report.csv` (see below).

---

### `merge_phage_fasta.log`

**Config key**: `merge_phage_fasta_log`

Log from the rule that merges per-source phage FASTA files into a single `all_phages.fasta`.

---

### `merge_protein_fasta.log`

**Config key**: `merge_protein_fasta_log`

Log from the rule that merges per-source protein FASTA files into a single `all_proteins.fasta`.

---

### `index_phage_sequences.log`

**Config key**: `index_phage_sequences_log`

Log from the rule that creates the pyfaidx `.fai` index for `all_phages.fasta`.

---

### `index_protein_sequences.log`

**Config key**: `index_protein_sequences_log`

Log from the rule that creates the pyfaidx `.fai` index for `all_proteins.fasta`.

---

## `reports/` — HTML reports and summary CSVs

### `database_validation.html`

**Config key**: `database_validation_report_output`

Comprehensive HTML report generated after the DuckDB database is built.  Covers row counts, null-value rates, cross-table join statistics, and data-quality checks.

---

### `host_status_report.csv`

**Config key**: `host_status_report`

Combined per-phage host-status table produced by `create_host_status_report`.  One row per `(Phage_ID, Host_Token)` pair, joining data from `phage_host_candidates.csv`, `phage_host_assemblies.csv`, `assembly_metadata.csv`, and `host_fasta_qc.csv`.

Key columns:

| Column | Description |
|---|---|
| `Phage_ID` | Phage identifier |
| `Host_Token` | Individual parsed host token |
| `Token_Type` | `assembly_accession` / `species_name` / `other` |
| `Assembly_Accession` | Resolved assembly accession (if any) |
| `Assembly_Level` | `Complete Genome` / `Chromosome` / `Scaffold` / `Contig` |
| `Downloaded` | Whether the FASTA was successfully downloaded |
| `Indexed` | Whether the FASTA was successfully indexed |
| `QC_Status` | `indexed` / `rejected` / `warning` |

```python
import pandas as pd
report = pd.read_csv("pipeline_logs/reports/host_status_report.csv")

# How many phages have at least one resolved and indexed host?
resolved = report[report["Indexed"] == True]
print(f"Phages with ≥1 indexed host: {resolved['Phage_ID'].nunique()}")

# Phages with no indexed host at all
all_phage_ids = report["Phage_ID"].unique()
phages_with_host = resolved["Phage_ID"].unique()
missing = set(all_phage_ids) - set(phages_with_host)
print(f"Phages with no indexed host: {len(missing)}")
```

---

### Feature metadata reports (`*_report.html`)

One HTML report per feature is generated by the metadata-merging rules.  Each report summarises per-source row counts, column coverage, and data-quality indicators for the merged metadata CSV.

| File | Feature |
|---|---|
| `phage_metadata_report.html` | Core phage metadata |
| `annotated_proteins_metadata_report.html` | Annotated protein sequences |
| `transcription_terminator_metadata_report.html` | Transcription terminators |
| `phage_trna_tmrna_metadata_report.html` | tRNA / tmRNA features |
| `phage_anti_crispr_metadata_report.html` | Anti-CRISPR proteins |
| `phage_virulent_factor_metadata_report.html` | Virulence factors |
| `phage_transmembrane_protein_metadata_report.html` | Transmembrane proteins |
| `crispr_array_metadata_report.html` | CRISPR arrays |
| `antimicrobial_resistance_gene_metadata_report.html` | AMR genes |

---

## `csv/` — Intermediate data files for analysis

These files are produced during the host-genome download and resolution steps.  They are bind-mounted so that they survive container restarts and are immediately accessible from the host for log analysis without needing to enter the container.

### `.host_indexes_complete`

**Config key**: `host_index_complete_flag`

Hidden sentinel file created by Snakemake's `touch()` after all host FASTA files have been indexed successfully.  Its existence is the only signal Snakemake needs to know the indexing step is complete.

---

### `host_metadata.csv`

**Config key**: `host_metadata_output`

Per-assembly metadata for every successfully downloaded host genome.  One row per unique assembly accession.

Key columns:

| Column | Description |
|---|---|
| `Host_ID` | Unique host identifier (`{species}_{accession}`) |
| `Species_Name` | Original species name from phage metadata |
| `Assembly_Accession` | NCBI accession (GCF_ preferred) |
| `Assembly_Level` | `Complete Genome` / `Chromosome` / `Scaffold` / `Contig` |
| `Genome_Length` | Total genome size in base pairs |
| `GC_Content` | GC percentage |
| `Sequence_Count` | Number of sequences in the assembly |
| `Download_Date` | Timestamp of the download |

```python
import pandas as pd
meta = pd.read_csv("pipeline_logs/csv/host_metadata.csv")
print(f"Total host genomes: {len(meta)}")
print(meta["Assembly_Level"].value_counts())
```

---

### `assembly_metadata.csv`

**Config key**: `assembly_metadata_output`

Detailed NCBI Assembly metadata retrieved during the resolution step.  Broader than `host_metadata.csv`; includes RefSeq category, submission date, and other assembly attributes.

---

### `phage_host_links.csv`

**Config key**: `phage_host_links_output`

Flat mapping of phage → assembly accession links.  One row per unique `(Phage_ID, Assembly_Accession)` pair.  This is the authoritative table loaded into DuckDB to build the phage–host relationship.

Key columns:

| Column | Description |
|---|---|
| `Phage_ID` | Phage identifier |
| `Assembly_Accession` | Resolved NCBI accession |
| `Host_Raw` | Original un-parsed host field (for traceability) |
| `Confidence` | Float 0–1 reflecting resolution quality |

---

### `phage_host_candidates.csv`

**Config key**: `phage_host_candidates_output`

Lossless, auditable record of every host token parsed from the phage metadata.  One row per `(Phage_ID, token)` pair — this is the input to the resolution step.

Key columns:

| Column | Description |
|---|---|
| `Phage_ID` | Phage identifier |
| `Host_Raw` | Original un-parsed Host field |
| `Host_Token` | Individual token extracted from the field |
| `Token_Type` | `assembly_accession` / `species_name` / `other` |
| `Token_Order` | 1-based position in the original field |

Useful for auditing the parser: every token that entered the pipeline is visible here, including those that were ultimately unresolvable.

---

### `phage_host_assemblies.csv`

**Config key**: `phage_host_assemblies_output`

Per-token resolution results.  One row per `(Phage_ID, Assembly_Accession)` pair, produced after NCBI resolution.  Includes confidence scores and resolution metadata.

Key columns:

| Column | Description |
|---|---|
| `Phage_ID` | Phage identifier |
| `Host_Token` | Specific token that was resolved |
| `Assembly_Accession` | Resolved NCBI accession |
| `Resolution_Source` | `accession_in_host_field` / `species_to_taxid_to_assembly` / `fallback` |
| `Confidence` | Float 0–1 |
| `Assembly_Level` | `Complete Genome` / `Chromosome` / `Scaffold` / `Contig` |
| `Ambiguous` | `True` when multiple equally-plausible hits exist |

```python
import pandas as pd
assemblies = pd.read_csv("pipeline_logs/csv/phage_host_assemblies.csv")

# Resolution source distribution
print(assemblies["Resolution_Source"].value_counts())

# Ambiguous resolutions
print(assemblies[assemblies["Ambiguous"] == True][["Phage_ID", "Host_Token", "Ambiguity_Reason"]])
```

---

### `host_token_resolution_cache.json`

**Config key**: `host_resolution_cache_output`

Persistent JSON cache mapping host tokens to their resolved NCBI assembly accessions.  Reused across reruns when `reuse_host_resolution_cache: true` (the default), so expensive NCBI taxonomy/assembly lookups are not repeated for tokens that have already been resolved.

To force a full re-resolution pass (ignoring this cache):

```bash
snakemake --cores 4 --use-conda \
  --forcerun download_host_genomes \
  --config reuse_host_resolution_cache=false
```

The cache is a plain JSON object and can be inspected or edited manually if needed.

---

## Quick-reference table

| File (relative to `pipeline_logs/`) | Config key | Format | Produced by rule |
|---|---|---|---|
| `logs/host_download.log` | `host_download_log` | text | `download_host_genomes` |
| `logs/host_download_failures.log` | `host_failure_log` | text | `download_host_genomes` |
| `logs/host_fasta_qc.csv` | `host_fasta_qc_log` | CSV | `index_individual_host_sequences` |
| `logs/create_host_mapping.log` | `create_host_mapping_log` | text | `create_host_mapping` |
| `logs/index_individual_host_sequences.log` | `index_individual_host_sequences_log` | text | `index_individual_host_sequences` |
| `logs/create_host_status_report.log` | `create_host_status_report_log` | text | `create_host_status_report` |
| `logs/merge_phage_fasta.log` | `merge_phage_fasta_log` | text | `merge_phage_fasta` |
| `logs/merge_protein_fasta.log` | `merge_protein_fasta_log` | text | `merge_protein_fasta` |
| `logs/index_phage_sequences.log` | `index_phage_sequences_log` | text | `index_phage_sequences` |
| `logs/index_protein_sequences.log` | `index_protein_sequences_log` | text | `index_protein_sequences` |
| `reports/database_validation.html` | `database_validation_report_output` | HTML | `validate_database` |
| `reports/host_status_report.csv` | `host_status_report` | CSV | `create_host_status_report` |
| `reports/phage_metadata_report.html` | `phage_metadata_report_output` | HTML | `generate_report` |
| `reports/annotated_proteins_metadata_report.html` | `annotated_proteins_metadata_report_output` | HTML | `generate_report` |
| `reports/transcription_terminator_metadata_report.html` | `transcription_terminator_metadata_report_output` | HTML | `generate_report` |
| `reports/phage_trna_tmrna_metadata_report.html` | `phage_trna_tmrna_metadata_report_output` | HTML | `generate_report` |
| `reports/phage_anti_crispr_metadata_report.html` | `phage_anti_crispr_metadata_report_output` | HTML | `generate_report` |
| `reports/phage_virulent_factor_metadata_report.html` | `phage_virulent_factor_metadata_report_output` | HTML | `generate_report` |
| `reports/phage_transmembrane_protein_metadata_report.html` | `phage_transmembrane_protein_metadata_report_output` | HTML | `generate_report` |
| `reports/crispr_array_metadata_report.html` | `crispr_array_metadata_report_output` | HTML | `generate_report` |
| `reports/antimicrobial_resistance_gene_metadata_report.html` | `antimicrobial_resistance_gene_metadata_report_output` | HTML | `generate_report` |
| `csv/.host_indexes_complete` | `host_index_complete_flag` | flag | `index_individual_host_sequences` |
| `csv/host_metadata.csv` | `host_metadata_output` | CSV | `download_host_genomes` |
| `csv/assembly_metadata.csv` | `assembly_metadata_output` | CSV | `download_host_genomes` |
| `csv/phage_host_links.csv` | `phage_host_links_output` | CSV | `download_host_genomes` |
| `csv/phage_host_candidates.csv` | `phage_host_candidates_output` | CSV | `download_host_genomes` |
| `csv/phage_host_assemblies.csv` | `phage_host_assemblies_output` | CSV | `download_host_genomes` |
| `csv/host_token_resolution_cache.json` | `host_resolution_cache_output` | JSON | `download_host_genomes` |
| `csv/public_data_manifest.json` | `public_data_provenance.manifest_json_output` | JSON | `build_public_data_provenance_manifest` |
| `csv/public_data_manifest.csv` | `public_data_provenance.manifest_csv_output` | CSV | `build_public_data_provenance_manifest` |
| `csv/pipeline_run_provenance.json` | `public_data_provenance.pipeline_run_provenance_json_output` | JSON | `build_public_data_provenance_manifest` |
| `csv/pipeline_run_provenance.csv` | `public_data_provenance.pipeline_run_provenance_csv_output` | CSV | `build_public_data_provenance_manifest` |

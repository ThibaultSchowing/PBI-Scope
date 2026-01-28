# Robust Host Genome Retrieval from NCBI

## Overview

The robust host genome retrieval system provides a comprehensive, reproducible, and scalable strategy for downloading bacterial genome assemblies from NCBI. It addresses all key requirements for production-quality genome retrieval:

1. **NCBI Assembly database as authoritative source** - Uses Assembly database, not Nucleotide
2. **Heterogeneous identifier support** - Handles GCF/GCA, BioSample, BioProject, species names, strain names
3. **Explicit ambiguity handling** - Acknowledges and manages name ambiguity
4. **Quality-based filtering** - RefSeq > GenBank, latest versions, assembly level ranking
5. **Metadata via Entrez, sequences via FTP** - Best practices for retrieval
6. **Failure mode mitigation** - Handles duplicates, partial genomes, outdated assemblies

## Architecture

### Components

1. **AssemblyResolver** (`assembly_resolver.py`)
   - Normalizes heterogeneous identifiers to assembly accessions
   - Quality-based ranking of assemblies
   - Explicit ambiguity handling for species names

2. **RobustHostGenomeDownloader** (`download_host_genomes_robust.py`)
   - End-to-end pipeline for host genome retrieval
   - Metadata-only mode for disk space conservation
   - Download resumption with validation
   - Phage-host assembly linking

3. **Database Tables**
   - `dim_assembly_metadata` - Comprehensive assembly information
   - `dim_phage_host_links` - Links phages to host assemblies
   - `dim_hosts` - Backward-compatible host metadata

## Key Features

### 1. Assembly Resolution

The `AssemblyResolver` class provides robust resolution from various identifier types:

```python
from assembly_resolver import AssemblyResolver

resolver = AssemblyResolver(
    email="your.email@example.com",
    api_key="optional_api_key"
)

# Resolve from species name
assemblies = resolver.resolve("Escherichia coli", prefer_refseq=True)
best = assemblies[0]  # Highest quality assembly

# Resolve from assembly accession
assembly = resolver.get_best_assembly("GCF_000005845.2")

# Resolve from BioSample
assemblies = resolver.resolve("SAMN02604091")
```

#### Supported Identifier Types

- **Assembly Accessions**: `GCF_000005845.2`, `GCA_000001405.29`
- **BioSample**: `SAMN02604091`, `SAMD00000001`
- **BioProject**: `PRJNA224116`, `PRJEB1234`
- **Species Names**: `"Escherichia coli"`, `"Staphylococcus aureus"`
- **Strain Names**: `"Escherichia coli K12"`
- **TaxID**: `562` (E. coli)

### 2. Quality-Based Ranking

Assemblies are ranked by quality score based on:

1. **RefSeq Category** (highest priority)
   - Reference genome: +10,000
   - Representative genome: +5,000
   - NA: 0

2. **Assembly Level**
   - Complete Genome: +1,000
   - Chromosome: +500
   - Scaffold: +100
   - Contig: +50

3. **Latest Version**: +10

### 3. Metadata-Only Mode

Save disk space by retrieving only metadata without downloading sequences:

```yaml
# config.yaml
metadata_only_mode: true  # Only gather metadata, skip downloads
```

This creates:
- Host metadata CSV (backward compatible)
- Assembly metadata CSV (comprehensive)
- Phage-host links CSV

### 4. Download Resumption

Preserve already downloaded genomes from previous runs:

```yaml
skip_existing_downloads: true  # Don't re-download existing files
validate_file_checksums: true  # Validate integrity of existing files
```

### 5. File Retrieval Strategy

#### Essential Files (Always Downloaded)

- `*_genomic.fna.gz` - Genomic nucleotide FASTA
- `*_genomic.gff.gz` - Gene annotations (GFF3)
- `*_protein.faa.gz` - Translated proteins
- `*_assembly_report.txt` - Quality metrics

#### Optional Files

- `*_cds_from_genomic.fna.gz` - CDS sequences
- `*_genomic.gbff.gz` - GenBank flat file
- `*_feature_table.txt.gz` - Feature table
- `*_assembly_stats.txt` - Assembly statistics

Enable optional file download:

```yaml
download_optional_files: true
```

## Usage

### Snakemake Integration

The robust downloader is integrated into the Snakemake pipeline via the `hosts.smk` rule:

```python
rule download_host_genomes:
    input:
        phage_csv = config["phage_metadata_merged_output"]
    output:
        metadata = config["host_metadata_output"],
        assembly_metadata = config["assembly_metadata_output"],
        phage_host_links = config["phage_host_links_output"]
    params:
        use_robust_downloader = True  # Enable robust downloader
    script:
        "../scripts/sequences/download_host_genomes_robust.py"
```

### Configuration

Add to `config.yaml`:

```yaml
# Host genome settings
host_genomes_intermediate: "/data/intermediate/fasta/hosts"
host_metadata_output: "/data/intermediate/csv/merged/host_metadata.csv"
assembly_metadata_output: "/data/intermediate/csv/merged/assembly_metadata.csv"
phage_host_links_output: "/data/intermediate/csv/merged/phage_host_links.csv"

# NCBI settings
ncbi_email: "your.email@example.com"  # Required
ncbi_api_key: "${NCBI_API_KEY}"       # Optional, for higher rate limits

# Download behavior
metadata_only_mode: false              # Set true to skip downloads
skip_existing_downloads: true          # Skip already downloaded files
validate_file_checksums: true          # Validate file integrity
use_robust_downloader: true            # Use robust downloader (recommended)
```

### Command Line Usage

```bash
# Metadata-only mode
python workflow/scripts/sequences/download_host_genomes_robust.py \
  --phage-csv data/phages.csv \
  --output-dir data/genomes \
  --metadata-output data/host_metadata.csv \
  --assembly-metadata data/assembly_metadata.csv \
  --phage-host-links data/phage_host_links.csv \
  --ncbi-email your.email@example.com \
  --metadata-only

# Full download with validation
python workflow/scripts/sequences/download_host_genomes_robust.py \
  --phage-csv data/phages.csv \
  --output-dir data/genomes \
  --metadata-output data/host_metadata.csv \
  --ncbi-email your.email@example.com \
  --skip-existing \
  --validate-checksums
```

## Database Schema

### dim_assembly_metadata

Comprehensive assembly information:

| Column | Type | Description |
|--------|------|-------------|
| Assembly_Accession | VARCHAR | GCF_/GCA_ accession |
| Assembly_Name | VARCHAR | Assembly name |
| Organism_Name | VARCHAR | Full organism name |
| Species_TaxID | INTEGER | NCBI taxonomy ID |
| Strain | VARCHAR | Strain designation |
| Assembly_Level | VARCHAR | Complete/Chromosome/Scaffold/Contig |
| RefSeq_Category | VARCHAR | reference/representative/na |
| BioSample | VARCHAR | BioSample accession |
| BioProject | VARCHAR | BioProject accession |
| FTP_Path | VARCHAR | NCBI FTP path |
| Submission_Date | VARCHAR | Submission date |
| Is_Latest | BOOLEAN | Latest version flag |
| Quality_Score | INTEGER | Calculated quality score |
| Is_RefSeq | BOOLEAN | RefSeq vs GenBank |
| Download_Status | VARCHAR | success/failed |
| Download_Date | VARCHAR | Download date |
| Metadata_Only | BOOLEAN | Metadata-only mode flag |

### dim_phage_host_links

Links phages to their host assemblies:

| Column | Type | Description |
|--------|------|-------------|
| Phage_ID | VARCHAR | Phage identifier |
| Host_Species | VARCHAR | Species name |
| Host_Full_Name | VARCHAR | Full host designation |
| Assembly_Accession | VARCHAR | Host assembly accession |
| Assembly_Level | VARCHAR | Assembly completeness |
| RefSeq_Category | VARCHAR | Assembly category |
| Link_Quality | VARCHAR | direct/genbank |

### dim_hosts (Backward Compatible)

Legacy host metadata format:

| Column | Type | Description |
|--------|------|-------------|
| Host_ID | VARCHAR | Host identifier |
| Species_Name | VARCHAR | Species name |
| Strain_Name | VARCHAR | Strain name |
| Assembly_Accession | VARCHAR | Assembly accession |
| Assembly_Name | VARCHAR | Assembly name |
| Assembly_Level | VARCHAR | Assembly level |
| Genome_Length | BIGINT | Genome length (bp) |
| GC_Content | DOUBLE | GC content (%) |
| RefSeq_Category | VARCHAR | RefSeq category |
| Download_Date | VARCHAR | Download date |
| Source | VARCHAR | Data source |

## Comparison to Legacy Downloader

### Legacy Downloader

**Strengths:**
- Simple implementation
- Uses NCBI datasets CLI (when available)
- Basic retry logic

**Limitations:**
- No systematic identifier normalization
- Limited assembly quality ranking
- No metadata-only mode
- No systematic phage-host linking
- Limited failure recovery
- Uses efetch for sequences (not recommended)

### Robust Downloader

**Improvements:**

1. **Identifier Normalization**
   - Handles 6+ identifier types systematically
   - Explicit ambiguity detection and reporting

2. **Quality Control**
   - Multi-criteria assembly ranking
   - Preference for RefSeq over GenBank
   - Latest version tracking

3. **Operational Efficiency**
   - Metadata-only mode saves disk space
   - Download resumption prevents re-downloads
   - File integrity validation

4. **Data Quality**
   - Systematic phage-host assembly linking
   - Comprehensive metadata tracking
   - Failure mode detection

5. **Best Practices**
   - Metadata via Entrez, sequences via FTP
   - Assembly database as authoritative source
   - Clear distinction between genome types

## Failure Modes and Mitigation

### 1. Duplicate Assemblies

**Problem:** Multiple assemblies exist for same organism

**Mitigation:**
- Quality-based ranking selects best assembly
- Preference for reference > representative genomes
- RefSeq preferred over GenBank
- Latest version tracking

### 2. Partial Genomes

**Problem:** Incomplete or low-quality assemblies

**Mitigation:**
- Assembly level ranking (Complete > Chromosome > Scaffold > Contig)
- Quality score calculation
- Assembly status tracking
- Optional requirement for complete genomes only

### 3. Outdated Assemblies

**Problem:** Old assembly versions

**Mitigation:**
- `is_latest` flag tracking
- Latest version preference in ranking
- Submission date tracking

### 4. Naming Inconsistencies

**Problem:** Non-standard species/strain names

**Mitigation:**
- TaxID resolution for validation
- Explicit ambiguity acknowledgment
- Multiple name format support
- Warning logs for ambiguous names

### 5. Download Failures

**Problem:** Network errors, missing files

**Mitigation:**
- Retry logic with exponential backoff
- Essential vs optional file distinction
- Download status tracking
- Resume capability

### 6. FTP Path Changes

**Problem:** NCBI FTP paths may change

**Mitigation:**
- Dynamic FTP path retrieval from Assembly database
- Multiple file suffix support
- Graceful degradation for missing optional files

## Testing

### Unit Tests

```bash
# Test assembly resolver
python tests/test_assembly_resolver.py

# Test robust downloader
python tests/test_robust_genome_download.py

# Test legacy compatibility
python tests/test_host_genome_download.py
```

### Integration Tests

```bash
# Test with NCBI API (requires NCBI_EMAIL)
export NCBI_EMAIL="your.email@example.com"
export NCBI_API_KEY="your_api_key"  # Optional
python tests/test_assembly_resolver.py
python tests/test_robust_genome_download.py
```

## Performance

### Rate Limiting

- **Without API key**: 3 requests/second
- **With API key**: 10 requests/second

### Typical Performance

- **Metadata-only**: ~1-2 seconds per species
- **Full download**: ~30-60 seconds per genome (depends on size)
- **Resume mode**: ~0.1 seconds per existing genome

### Optimization Tips

1. Use metadata-only mode when disk space is limited
2. Enable skip_existing for incremental updates
3. Use NCBI API key for faster metadata retrieval
4. Consider batching large-scale downloads

## Migration Guide

### From Legacy to Robust Downloader

1. Update `config.yaml`:
   ```yaml
   use_robust_downloader: true
   assembly_metadata_output: "/data/intermediate/csv/merged/assembly_metadata.csv"
   phage_host_links_output: "/data/intermediate/csv/merged/phage_host_links.csv"
   ```

2. Run pipeline:
   ```bash
   snakemake --use-conda download_host_genomes
   ```

3. Verify new tables in database:
   ```sql
   SELECT COUNT(*) FROM dim_assembly_metadata;
   SELECT COUNT(*) FROM dim_phage_host_links;
   ```

### Backward Compatibility

The robust downloader maintains backward compatibility by:
- Still generating `host_metadata.csv` in legacy format
- Preserving `dim_hosts` table structure
- Maintaining `host_fasta_mapping.json` format
- Supporting existing downstream tools

## References

- [NCBI Assembly Database](https://www.ncbi.nlm.nih.gov/assembly/)
- [NCBI FTP Structure](https://ftp.ncbi.nlm.nih.gov/genomes/)
- [Entrez Programming Utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [RefSeq vs GenBank](https://www.ncbi.nlm.nih.gov/books/NBK50679/)

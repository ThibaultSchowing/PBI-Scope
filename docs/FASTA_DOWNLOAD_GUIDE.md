# FASTA Download Guide

This guide provides comprehensive information about how FASTA files are downloaded and organized in the PBI pipeline.

## Table of Contents

1. [Overview](#overview)
2. [Download Procedures](#download-procedures)
3. [File Organization](#file-organization)
4. [Species Name Resolution](#species-name-resolution)
5. [Configuration](#configuration)
6. [Troubleshooting](#troubleshooting)

## Overview

The PBI pipeline downloads three types of FASTA files:

1. **Phage Sequences** - Phage genomes from 14 databases
2. **Protein Sequences** - Phage protein sequences from the same databases
3. **Host Genomes** - Bacterial host genomes from NCBI RefSeq

All downloaded files are organized, validated, and indexed for efficient access through the PBI API and Python package.

## Download Procedures

### Phage and Protein FASTA Downloads

**Source**: Pre-packaged archives from PhageScope API (`phageapi.deepomics.org`)

**Databases Included**:
- GenBank, RefSeq, DDBJ, EMBL (primary databases)
- PhagesDB (curated phage database)
- GPD, GVD, MGV, TemPhD, CHVD, IGVD, GOV2, STV (specialized phage databases)

**Workflow**:
1. Download `.tar.gz` archives from PhageScope API
2. Extract to source-specific directories
3. Merge all sources into single FASTA files
4. Index with pyfaidx for fast random access

**File Locations**:
- Downloaded archives: `/data/raw/phage_fasta_compressed/`, `/data/raw/protein_fasta_compressed/`
- Extracted files: `/data/raw/phage_fasta_extracted/`, `/data/raw/protein_fasta_extracted/`
- Merged by source: `/data/intermediate/fasta/phages/`, `/data/intermediate/fasta/proteins/`
- Final merged: `/data/processed/sequences/all_phages.fasta`, `/data/processed/sequences/all_proteins.fasta`
- Indexes: `.fai` files alongside FASTA files

### Host Genome Downloads

**Source**: NCBI RefSeq bacterial reference genomes

**Download Strategy**:
1. **Extract Host Species**: Parse unique host species from phage metadata CSV
2. **Validate Species Names**: Filter out invalid identifiers (GTDB, unknown, etc.)
3. **Search RefSeq**: Find best available reference genome for each species
4. **Download Genome**: Use NCBI datasets CLI (primary) or Entrez API (fallback)
5. **Calculate Stats**: Compute genome length and GC content
6. **Generate Metadata**: Create comprehensive host metadata CSV

**Download Methods**:

1. **NCBI Datasets CLI** (Primary Method)
   - Faster and more reliable
   - Better for batch downloads
   - Requires `datasets` command-line tool

2. **Entrez API** (Fallback Method)
   - Used when datasets CLI unavailable or fails
   - More flexible but slower
   - Requires NCBI email and API key

**File Locations**:
- Individual genomes: `/data/intermediate/fasta/hosts/{Species_Name}_{Assembly_Accession}.fna`
- Merged file: `/data/processed/sequences/all_hosts.fasta`
- Index: `/data/processed/sequences/all_hosts.fasta.fai`
- Metadata: `/data/intermediate/csv/merged/host_metadata.csv`
- Cache (optimized): `/data/cache/genomes/`
- Cache database: `/data/cache/metadata.db`

**File Naming Convention**:
```
{Genus}_{species}_{Assembly_Accession}.fna

Examples:
- Escherichia_coli_GCF_000005845.2.fna
- Staphylococcus_aureus_GCF_000013425.1.fna
- Pseudomonas_aeruginosa_GCF_000006765.1.fna
```

## File Organization

### Complete Directory Structure

```
data/
├── raw/                                      # Downloaded raw data
│   ├── phage_fasta_compressed/               # Phage FASTA archives (.tar.gz)
│   ├── phage_fasta_extracted/                # Extracted phage FASTA files
│   ├── protein_fasta_compressed/             # Protein FASTA archives (.tar.gz)
│   └── protein_fasta_extracted/              # Extracted protein FASTA files
│
├── intermediate/                             # Intermediate processing files
│   ├── fasta/
│   │   ├── hosts/                            # Individual host genome files
│   │   │   ├── Escherichia_coli_GCF_000005845.2.fna
│   │   │   ├── Staphylococcus_aureus_GCF_000013425.1.fna
│   │   │   └── ...
│   │   ├── phages/                           # Phage FASTA by source
│   │   │   ├── GenBank.fasta
│   │   │   ├── RefSeq.fasta
│   │   │   └── ...
│   │   └── proteins/                         # Protein FASTA by source
│   │       ├── GenBank.fasta
│   │       ├── RefSeq.fasta
│   │       └── ...
│   └── csv/
│       └── merged/
│           ├── merged_phage_metadata.csv     # Source for host extraction
│           └── host_metadata.csv             # Generated host information
│
├── processed/                                # Final processed files
│   ├── sequences/
│   │   ├── all_phages.fasta                  # All phages merged
│   │   ├── all_phages.fasta.fai              # Index for phages
│   │   ├── all_proteins.fasta                # All proteins merged
│   │   ├── all_proteins.fasta.fai            # Index for proteins
│   │   ├── all_hosts.fasta                   # All hosts merged
│   │   └── all_hosts.fasta.fai               # Index for hosts
│   └── databases/
│       └── phage_database.duckdb             # Complete database
│
├── cache/                                    # Cache for optimized downloader
│   ├── genomes/                              # Cached genome files
│   │   ├── Escherichia_coli_GCF_000005845.2.fna
│   │   └── ...
│   └── metadata.db                           # SQLite cache database
│
└── logs/                                     # Download and processing logs
    ├── host_download.log
    ├── host_download_failures.log
    └── ...
```

### File Size Estimates

| Category | Compressed | Extracted | Final Merged | Notes |
|----------|-----------|-----------|--------------|-------|
| Phages | ~2-5 GB | ~5-10 GB | ~10-15 GB | Depends on database versions |
| Proteins | ~3-8 GB | ~8-20 GB | ~20-30 GB | Larger than phages |
| Hosts | N/A | ~5-50 GB | ~50-100 GB | Depends on number of unique hosts |

**Storage Recommendations**:
- Minimum: 100 GB for complete pipeline
- Recommended: 200+ GB for cache and intermediate files
- Use SSD for better I/O performance during indexing

## Species Name Resolution

### From Phage Metadata to Host Genome

**Step-by-Step Process**:

1. **Extract Host Names from Phage Metadata**
   - Source: `merged_phage_metadata.csv` column `Host`
   - Filter out invalid entries:
     - Null/empty values
     - `-` (dash)
     - `unknown` (case-insensitive)
     - `unidentified` (case-insensitive)

2. **Normalize to Species Names**
   - Extract first two words: `Genus species`
   - Example: `Escherichia coli K-12` → `Escherichia coli`
   - Validate genus name starts with capital letter

3. **Validate Species Names**
   - **Skip GTDB Identifiers**: Pattern `sp\d{9}` (e.g., `sp000302535`)
   - GTDB identifiers are not NCBI species names
   - Skipping reduces failed downloads by ~80%

4. **Search NCBI RefSeq**
   - Query: `"{Species name}"[Organism] AND "latest refseq"[Filter]`
   - Filters:
     - RefSeq database only (higher quality)
     - Latest versions only
     - Bacterial genomes

5. **Select Best Assembly**
   - **Priority Order**:
     1. Reference genome (highest priority)
     2. Representative genome
     3. Complete genome level
     4. Chromosome level
     5. Scaffold level
     6. Latest version

6. **Download and Validate**
   - Download using datasets CLI or Entrez API
   - Validate FASTA format (must start with `>`)
   - Validate content is not empty
   - Calculate genome statistics

### Examples

**Valid Host Name Processing**:
```
Input: "Escherichia coli strain K-12"
→ Normalized: "Escherichia coli"
→ Search: NCBI RefSeq for "Escherichia coli"
→ Found: GCF_000005845.2 (E. coli K-12 substr. MG1655)
→ Downloaded: Escherichia_coli_GCF_000005845.2.fna
```

**GTDB Identifier (Skipped)**:
```
Input: "Acidovorax sp000302535"
→ Detected: GTDB identifier pattern
→ Action: Skip (not a valid NCBI species name)
→ Log: "⏭️ Skipping Acidovorax sp000302535: GTDB identifier detected"
```

**Unknown Host (Filtered)**:
```
Input: "unknown"
→ Action: Filtered out during CSV parsing
→ Not processed
```

## Configuration

### Environment Variables

**Required**:
```bash
export NCBI_EMAIL="your.email@example.com"
```

**Recommended** (for higher rate limits):
```bash
export NCBI_API_KEY="your_api_key_here"
```

Get your API key from: https://www.ncbi.nlm.nih.gov/account/settings/

### Configuration Files

**Primary Config**: `workflow/config/config.yaml`
```yaml
# Host genome settings
host_genomes_intermediate: "/data/intermediate/fasta/hosts"
host_metadata_output: "/data/intermediate/csv/merged/host_metadata.csv"
ncbi_email: "phage.pipeline@example.com"  # Update with your email
max_host_download_retries: 3
host_download_delay: 0.5  # seconds between requests
```

**Optimized Downloader Config**: `workflow/config/genome_download_config.yaml`
```yaml
download:
  requests_per_second: 3         # Without API key
  requests_per_second_with_api_key: 10  # With API key
  max_retries: 3
  
cache:
  enabled: true
  directory: "data/cache/genomes"
  
validation:
  skip_gtdb_identifiers: true    # Highly recommended
```

### Rate Limiting

**NCBI Rate Limits**:
- **Without API key**: 3 requests/second
- **With API key**: 10 requests/second

**Implementation**:
- Token bucket algorithm ensures compliance
- Automatic detection of API key
- Exponential backoff on failures
- Prevents IP blocking

## Troubleshooting

### Common Issues

#### Issue: "Too many requests" error

**Symptoms**: HTTP 429 errors from NCBI

**Solutions**:
1. Verify rate limiter is active (check logs)
2. Set `NCBI_API_KEY` for higher limits
3. Reduce `requests_per_second` in config
4. Add delay between retries

**Check rate limiting**:
```bash
grep "rate limit" data/logs/genome_download.log
```

#### Issue: Many download failures

**Symptoms**: High percentage of failed downloads

**Solutions**:
1. **Enable GTDB filtering**: Set `skip_gtdb_identifiers: true`
2. **Check NCBI email**: Must be set correctly
3. **Verify network**: Test NCBI connectivity
4. **Review failures**: Check `data/failed_downloads.txt` for patterns

**Categorize failures**:
```bash
# View failure categories
cat data/failed_downloads.txt | grep ":" | sort | uniq -c
```

#### Issue: Downloads are very slow

**Symptoms**: < 0.5 genomes/second

**Solutions**:
1. **Get API key**: Increases rate to 10 req/sec
2. **Enable caching**: Check `cache.enabled: true`
3. **Use datasets CLI**: Install `ncbi-datasets-cli`
4. **Check network**: Test NCBI connectivity speed

**Monitor progress**:
```bash
tail -f data/logs/genome_download.log | grep "Rate:"
```

#### Issue: Cache not working

**Symptoms**: Re-downloading same genomes

**Solutions**:
1. **Check cache directory**: Verify permissions and space
2. **Check SQLite database**: `sqlite3 data/cache/metadata.db "SELECT COUNT(*) FROM genomes;"`
3. **Verify cache enabled**: `cache.enabled: true` in config

**Test cache**:
```bash
# Run twice, second run should be much faster
ls -lh data/cache/genomes/ | wc -l
```

#### Issue: Invalid FASTA files

**Symptoms**: Empty files or missing headers

**Solutions**:
1. **Use fasta-2line format**: Set in config (default)
2. **Validate downloads**: Check file sizes > 0
3. **Check file content**: `head -n 1 {file}.fna` should show `>`

**Validate FASTA**:
```bash
# Check FASTA headers
for f in data/intermediate/fasta/hosts/*.fna; do 
  head -n 1 "$f" | grep "^>" || echo "Invalid: $f"
done
```

### Performance Tips

1. **Use NCBI API Key**
   - 3x faster downloads (10 vs 3 req/sec)
   - Free from NCBI account settings

2. **Enable Caching**
   - Resume interrupted downloads
   - Skip already-downloaded genomes
   - 95%+ cache hit rate on re-runs

3. **Monitor Progress**
   - Check `data/progress.json` for statistics
   - View ETA and completion rate
   - Identify bottlenecks

4. **Optimize Storage**
   - Use SSD for cache directory
   - Compress old downloads if space limited
   - Clean cache periodically if needed

### Getting Help

**Check Logs**:
```bash
# Main download log
tail -100 data/logs/genome_download.log

# Host-specific log
tail -100 data/logs/host_download.log

# Failures
cat data/failed_downloads.txt
```

**Verify Configuration**:
```bash
# Check environment variables
echo $NCBI_EMAIL
echo $NCBI_API_KEY

# Validate config files
cat workflow/config/genome_download_config.yaml
```

**Report Issues**:
- Include relevant log excerpts
- Specify number of species processed
- Include failure categories
- Check documentation first

## Related Documentation

- **Optimization Details**: [genome_download_optimization.md](genome_download_optimization.md)
- **Installation Guide**: [Installation Guide](guides/installation.md)
- **Docker Setup**: [Docker Guide](guides/docker-guide.md)

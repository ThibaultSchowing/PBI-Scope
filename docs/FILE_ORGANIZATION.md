# FASTA File Organization Structure

This document provides a visual overview of how FASTA files are organized in the PBI pipeline.

## Complete Directory Tree

```
PBI/
├── workflow/
│   ├── config/
│   │   ├── config.yaml                          # Main configuration
│   │   └── genome_download_config.yaml          # Optimized downloader config
│   │
│   ├── scripts/
│   │   └── sequences/
│   │       ├── download_host_genomes.py         # Original host downloader
│   │       ├── download_host_genomes_optimized.py  # Optimized downloader
│   │       ├── index_sequences.py               # Create pyfaidx indexes
│   │       └── sequence_retrieval.py            # Query-based sequence access
│   │
│   └── rules/
│       ├── hosts.smk                            # Host genome rules
│       ├── sequences.smk                        # Phage/protein rules
│       └── ...
│
├── data/                                        # All data files (gitignored)
│   ├── raw/                                     # Downloaded raw archives
│   │   ├── phage_fasta_compressed/
│   │   │   ├── GenBank.tar.gz
│   │   │   ├── RefSeq.tar.gz
│   │   │   └── ... (14 databases)
│   │   │
│   │   ├── phage_fasta_extracted/
│   │   │   ├── GenBank/
│   │   │   │   └── *.fasta
│   │   │   ├── RefSeq/
│   │   │   │   └── *.fasta
│   │   │   └── ...
│   │   │
│   │   ├── protein_fasta_compressed/
│   │   │   ├── GenBank.tar.gz
│   │   │   ├── RefSeq.tar.gz
│   │   │   └── ... (13 databases)
│   │   │
│   │   └── protein_fasta_extracted/
│   │       ├── GenBank/
│   │       │   └── *.fasta
│   │       ├── RefSeq/
│   │       │   └── *.fasta
│   │       └── ...
│   │
│   ├── intermediate/                           # Intermediate processing
│   │   ├── fasta/
│   │   │   ├── hosts/                          # Individual host genomes
│   │   │   │   ├── Escherichia_coli_GCF_000005845.2.fna
│   │   │   │   ├── Staphylococcus_aureus_GCF_000013425.1.fna
│   │   │   │   ├── Pseudomonas_aeruginosa_GCF_000006765.1.fna
│   │   │   │   └── ... (hundreds of files)
│   │   │   │
│   │   │   ├── phages/                         # Merged by source
│   │   │   │   ├── GenBank.fasta
│   │   │   │   ├── RefSeq.fasta
│   │   │   │   ├── DDBJ.fasta
│   │   │   │   └── ... (14 files)
│   │   │   │
│   │   │   └── proteins/                       # Merged by source
│   │   │       ├── GenBank.fasta
│   │   │       ├── RefSeq.fasta
│   │   │       ├── DDBJ.fasta
│   │   │       └── ... (13 files)
│   │   │
│   │   └── csv/
│   │       └── merged/
│   │           ├── merged_phage_metadata.csv   # Input for host extraction
│   │           └── host_metadata.csv           # Host download results
│   │
│   ├── processed/                              # Final outputs
│   │   ├── sequences/
│   │   │   ├── all_phages.fasta                # All phages merged (10-15 GB)
│   │   │   ├── all_phages.fasta.fai            # pyfaidx index
│   │   │   ├── all_proteins.fasta              # All proteins merged (20-30 GB)
│   │   │   ├── all_proteins.fasta.fai          # pyfaidx index
│   │   │   ├── all_hosts.fasta                 # All hosts merged (50-100 GB)
│   │   │   └── all_hosts.fasta.fai             # pyfaidx index
│   │   │
│   │   └── databases/
│   │       └── phage_database.duckdb           # Complete queryable DB
│   │
│   ├── cache/                                  # Cache for optimized downloader
│   │   ├── genomes/                            # Cached host genomes
│   │   │   ├── Escherichia_coli_GCF_000005845.2.fna
│   │   │   └── ... (identical to intermediate/fasta/hosts)
│   │   │
│   │   └── metadata.db                         # SQLite cache database
│   │
│   └── logs/                                   # Logs and progress files
│       ├── host_download.log
│       ├── host_download_failures.log
│       ├── genome_download.log                 # Optimized downloader log
│       ├── failed_downloads.txt                # Categorized failures
│       └── progress.json                       # Download progress tracker
│
├── docs/                                       # Documentation
│   ├── FASTA_DOWNLOAD_GUIDE.md                # This guide
│   ├── ENVIRONMENT_SETUP.md                   # Environment setup
│   ├── MIGRATION_GUIDE_OPTIMIZED_DOWNLOADER.md
│   └── genome_download_optimization.md
│
└── tests/                                      # Test files
    ├── test_fasta_validation.py
    ├── test_host_genome_download.py
    └── test_integration_genome_download.py
```

## File Type Summary

| Location | File Type | Count | Size (Typical) | Purpose |
|----------|-----------|-------|----------------|---------|
| `raw/phage_fasta_compressed/` | `.tar.gz` | 14 | 200-500 MB each | Downloaded archives |
| `raw/phage_fasta_extracted/` | `.fasta` | Thousands | Variable | Extracted phage sequences |
| `raw/protein_fasta_compressed/` | `.tar.gz` | 13 | 300-800 MB each | Downloaded archives |
| `raw/protein_fasta_extracted/` | `.fasta` | Thousands | Variable | Extracted protein sequences |
| `intermediate/fasta/hosts/` | `.fna` | 100-500 | 2-10 MB each | Individual host genomes |
| `intermediate/fasta/phages/` | `.fasta` | 14 | 500 MB - 2 GB each | Phages by source |
| `intermediate/fasta/proteins/` | `.fasta` | 13 | 1-3 GB each | Proteins by source |
| `processed/sequences/` | `.fasta` | 3 | 10-100 GB each | Final merged files |
| `processed/sequences/` | `.fai` | 3 | KB - MB | pyfaidx indexes |
| `cache/genomes/` | `.fna` | 100-500 | 2-10 MB each | Cached host genomes |

## Data Flow Diagram

### Phage and Protein FASTA Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    PhageScope API                            │
│           (phageapi.deepomics.org)                          │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Download .tar.gz archives
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/raw/phage_fasta_compressed/                    │
│         data/raw/protein_fasta_compressed/                  │
│                                                             │
│  • GenBank.tar.gz                                          │
│  • RefSeq.tar.gz                                           │
│  • DDBJ.tar.gz, EMBL.tar.gz, ...                          │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Extract archives
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/raw/phage_fasta_extracted/                     │
│         data/raw/protein_fasta_extracted/                   │
│                                                             │
│  GenBank/                                                  │
│    ├── NC_000001.fasta                                     │
│    ├── NC_000002.fasta                                     │
│    └── ...                                                 │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Merge by source
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/intermediate/fasta/phages/                     │
│         data/intermediate/fasta/proteins/                   │
│                                                             │
│  • GenBank.fasta (all GenBank sequences)                   │
│  • RefSeq.fasta (all RefSeq sequences)                     │
│  • ...                                                     │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Merge all sources
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/processed/sequences/                           │
│                                                             │
│  • all_phages.fasta (10-15 GB)                             │
│  • all_proteins.fasta (20-30 GB)                           │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Create pyfaidx index
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/processed/sequences/                           │
│                                                             │
│  • all_phages.fasta.fai                                    │
│  • all_proteins.fasta.fai                                  │
└─────────────────────────────────────────────────────────────┘
```

### Host Genome Workflow

```
┌─────────────────────────────────────────────────────────────┐
│    data/intermediate/csv/merged/                            │
│                                                             │
│    merged_phage_metadata.csv                               │
│    (Contains "Host" column with species names)             │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Extract unique hosts
                         │ Filter out: null, '-', 'unknown'
                         │ Normalize to: 'Genus species'
                         │ Skip GTDB: 'sp\d{9}'
                         ↓
┌─────────────────────────────────────────────────────────────┐
│              Validated Species List                         │
│                                                             │
│  • Escherichia coli                                        │
│  • Staphylococcus aureus                                   │
│  • Pseudomonas aeruginosa                                  │
│  • ... (100-500 species)                                   │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Search NCBI RefSeq
                         │ Find best assembly (reference > representative > complete)
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                     NCBI RefSeq                             │
│                                                             │
│  Search: "Species name"[Organism] AND "latest refseq"      │
│  Return: Assembly accession (e.g., GCF_000005845.2)        │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Download genome
                         │ Method 1: NCBI datasets CLI (fast)
                         │ Method 2: Entrez API (fallback)
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/intermediate/fasta/hosts/                      │
│         (or data/cache/genomes/ for optimized)             │
│                                                             │
│  • Escherichia_coli_GCF_000005845.2.fna                    │
│  • Staphylococcus_aureus_GCF_000013425.1.fna              │
│  • Pseudomonas_aeruginosa_GCF_000006765.1.fna             │
│  • ... (100-500 files)                                     │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Calculate stats (length, GC%)
                         │ Generate metadata
                         ↓
┌─────────────────────────────────────────────────────────────┐
│    data/intermediate/csv/merged/                            │
│                                                             │
│    host_metadata.csv                                       │
│    (Host_ID, Species, Strain, Accession, Stats, ...)      │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Merge all host genomes
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/processed/sequences/                           │
│                                                             │
│  • all_hosts.fasta (50-100 GB)                             │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Create pyfaidx index
                         ↓
┌─────────────────────────────────────────────────────────────┐
│         data/processed/sequences/                           │
│                                                             │
│  • all_hosts.fasta.fai                                     │
└─────────────────────────────────────────────────────────────┘
```

## File Naming Conventions

### Host Genomes

**Pattern**: `{Genus}_{species}_{Assembly_Accession}.fna`

**Examples**:
- `Escherichia_coli_GCF_000005845.2.fna`
- `Staphylococcus_aureus_GCF_000013425.1.fna`
- `Pseudomonas_aeruginosa_GCF_000006765.1.fna`
- `Bacillus_subtilis_GCF_000009045.1.fna`

**Components**:
- `Genus`: Capitalized genus name
- `species`: Lowercase species epithet
- `Assembly_Accession`: NCBI RefSeq accession (GCF_XXXXXXXXX.X)
- Extension: `.fna` (FASTA nucleic acid)

### Phage and Protein Files

**Pattern**: `{Database}.fasta`

**Examples**:
- `GenBank.fasta`
- `RefSeq.fasta`
- `PhagesDB.fasta`
- `MGV.fasta`

### Index Files

**Pattern**: `{Original_filename}.fai`

**Examples**:
- `all_phages.fasta.fai`
- `all_proteins.fasta.fai`
- `all_hosts.fasta.fai`

## Storage Requirements

### By Pipeline Stage

| Stage | Storage Required | Notes |
|-------|------------------|-------|
| **Raw Downloads** | 20-50 GB | Compressed archives |
| **Extracted** | 50-100 GB | Uncompressed FASTA |
| **Intermediate** | 60-120 GB | Merged by source + hosts |
| **Processed** | 80-200 GB | Final merged + indexes |
| **Cache** | 5-50 GB | Host genomes only |
| **Total** | **215-520 GB** | Full pipeline |

### Optimization Tips

1. **Delete raw archives after extraction** (saves 20-50 GB):
   ```bash
   rm -rf data/raw/phage_fasta_compressed/*
   rm -rf data/raw/protein_fasta_compressed/*
   ```

2. **Delete extracted files after merging** (saves 50-100 GB):
   ```bash
   rm -rf data/raw/phage_fasta_extracted/*
   rm -rf data/raw/protein_fasta_extracted/*
   ```

3. **Keep only final merged files** (saves 60-120 GB):
   ```bash
   rm -rf data/intermediate/fasta/phages/*
   rm -rf data/intermediate/fasta/proteins/*
   # Keep hosts for individual access
   ```

4. **Minimum required** (80-200 GB):
   - `data/processed/sequences/all_*.fasta` + `.fai`
   - `data/intermediate/fasta/hosts/*.fna`
   - `data/intermediate/csv/merged/*.csv`
   - `data/processed/databases/*.duckdb`

## Access Patterns

### Direct File Access

**Individual host genome**:
```bash
cat data/intermediate/fasta/hosts/Escherichia_coli_GCF_000005845.2.fna
```

**Merged files**:
```bash
# Too large for cat, use samtools or pyfaidx
samtools faidx data/processed/sequences/all_hosts.fasta "NC_000913.3"
```

### Via Python (pyfaidx)

```python
from pyfaidx import Fasta

# Open indexed file
hosts = Fasta('data/processed/sequences/all_hosts.fasta')

# Get sequence by ID
seq = hosts['NC_000913.3']
print(f"Length: {len(seq)}")
print(f"Sequence: {seq[:100]}")
```

### Via PBI API

```python
from pbi import quick_connect

# Connect to database and sequences
retriever = quick_connect()

# Get host genome
host_genome = retriever.get_host_genome('Escherichia_coli_GCF_000005845.2')
```

## Maintenance

### Regular Cleanup

```bash
# Check storage usage
du -sh data/*

# Clean cache if space limited
rm -rf data/cache/genomes/*
rm -f data/cache/metadata.db

# Remove old logs
find data/logs -name "*.log" -mtime +30 -delete
```

### Verify File Integrity

```bash
# Check for empty files
find data/intermediate/fasta/hosts -name "*.fna" -size 0

# Verify FASTA format
for f in data/intermediate/fasta/hosts/*.fna; do
    head -n 1 "$f" | grep -q "^>" || echo "Invalid: $f"
done

# Check index files exist
ls data/processed/sequences/*.fai
```

## Related Documentation

- [FASTA Download Guide](FASTA_DOWNLOAD_GUIDE.md) - Comprehensive download documentation
- [Environment Setup](ENVIRONMENT_SETUP.md) - Setting up for downloads
- [Genome Download Quickstart](archive/GENOME_DOWNLOAD_QUICKSTART.md) - Quick start guide (archived)

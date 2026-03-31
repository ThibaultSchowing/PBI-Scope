# Database Overview

The PBI database consists of two main components: the **phage metadata database** (DuckDB) and the **host genome data** (individual FASTA files + mapping index).

## Phage Metadata Database

- **Database Engine**: DuckDB (columnar, embedded analytical database)
- **Schema**: Star schema with 1 fact table and 8 dimension tables
- **Total Size**: ~15 GB (optimized) / ~18 GB (unoptimized)
- **Total Phages**: ~873,000
- **Total Proteins**: ~43 million
- **Data Sources**: 14+ major phage databases via PhageScope

## Host Genome Data

- **Storage**: Individual FASTA files, one per assembly
- **Index**: `host_fasta_mapping.json` maps host IDs to file paths
- **Source**: NCBI RefSeq bacterial reference genomes
- **Coverage**: ~9,000 unique assembly accessions attempted; variable success rate depending on NCBI availability
- **Location**: `/data/processed/sequences/` (in Docker)

The host genome data is **not stored in the DuckDB database** — it is kept as separate FASTA files for memory efficiency, since individual host genomes can be very large. The `pbi` Python package uses `host_fasta_mapping.json` to locate and retrieve host sequences on demand.

See [Host Resolution Details](host-resolution.md) for information on how host species names are parsed and resolved to NCBI assemblies.

---

## Database Schema

```
                     dim_proteins ──┐
                  dim_terminators ──┤
                  dim_anti_crispr ──┤
             dim_virulent_factors ──┤
       dim_transmembrane_proteins ──┤──▶ fact_phages (central)
                   dim_trna_tmrna ──┤
dim_antimicrobial_resistance_genes ─┤
                  dim_crispr_array ─┘
```

All dimension tables link to `fact_phages` via **`Phage_ID`** foreign key, enabling comprehensive multi-dimensional analysis.

Host genome information is linked via external CSV/JSON files rather than a database table — see [Host-Phage Link Files](#host-phage-link-files-csv--json) below.

## Database Tables

### Fact Table: `fact_phages`

Central table containing core phage metadata.

**Key Columns:**
- `Phage_ID` (Primary Key): Unique phage identifier
- `Source_DB`: Origin database (GenBank, RefSeq, PhagesDB, etc.)
- `Length`: Genome length in base pairs
- `GC_content`: GC content percentage
- `Taxonomy`: Taxonomic classification
- `Host`: Bacterial host species
- `Lifestyle`: Lytic, Lysogenic, or Unknown

**Row Count**: ~873,718 phages

**Example Query:**
```sql
SELECT Source_DB, COUNT(*) as count, AVG(Length) as avg_length
FROM fact_phages
GROUP BY Source_DB
ORDER BY count DESC;
```

### Dimension Tables

#### `dim_proteins`

Protein annotations with functional predictions and physicochemical properties.

**Key Columns:**
- `Protein_ID` (Primary Key)
- `Phage_ID` (Foreign Key)
- `Product`: Protein function/description
- `Protein_length`: Length in amino acids
- `Molecular_weight`: Molecular weight
- `Isoelectric_point`: pI value
- `Source_DB`: Origin database

**Row Count**: ~43,088,582 proteins

#### `dim_terminators`

Transcription terminator predictions.

**Key Columns:**
- `Phage_ID` (Foreign Key)
- `terminator_type`: Type of terminator
- `start`, `end`: Genomic coordinates
- `confidence`: Prediction confidence score
- `strand`: DNA strand orientation

**Row Count**: ~6,462,417 terminators

#### `dim_anti_crispr`

Anti-CRISPR protein predictions.

**Key Columns:**
- `Phage_ID` (Foreign Key)
- `Protein_ID`: Associated protein
- `Source_DB`: Prediction source
- `Score`: Confidence score

**Row Count**: ~307,329 anti-CRISPR proteins

#### `dim_virulent_factors`

Virulence factor annotations aligned to VFDB.

**Key Columns:**
- `Phage_ID` (Foreign Key)
- `Protein_ID`: Associated protein
- `VF_ID`: VFDB identifier
- `VF_Name`: Virulence factor name
- `Source_DB`: Origin database

**Row Count**: ~41,609 virulence factors

#### `dim_transmembrane_proteins`

Transmembrane helix predictions (TMHMM).

**Key Columns:**
- `Phage_ID` (Foreign Key)
- `Protein_ID`: Associated protein
- `predicted_tmhs_number`: Number of transmembrane helices
- `protein_length`: Protein length
- `topology`: Membrane topology

**Row Count**: ~4,020,770 predictions

#### `dim_trna_tmrna`

tRNA and tmRNA predictions with sequences.

**Key Columns:**
- `trna_tmrna_id` (Primary Key)
- `Phage_ID` (Foreign Key)
- `trna_type`: Amino acid specificity
- `start`, `end`: Genomic coordinates
- `sequence`: RNA sequence
- `Source_DB`: Origin database

**Row Count**: ~702,607 tRNA/tmRNA features

#### `dim_crispr_array`

CRISPR array metadata.

**Key Columns:**
- `Phage_ID` (Foreign Key)
- `array_id`: Array identifier
- `repeat_sequence`: CRISPR repeat sequence
- `spacer_count`: Number of spacers

**Row Count**: ~56,652 arrays

#### `dim_antimicrobial_resistance_genes`

Antimicrobial resistance gene annotations.

**Key Columns:**
- `Phage_ID` (Foreign Key)
- `gene_id`: Gene identifier
- `gene_name`: AMR gene name
- `resistance_type`: Type of resistance

**Row Count**: ~2,602 genes

---

## Host-Phage Link Files (CSV / JSON)

> ⚠️ **These are flat files, not database tables.** Host genome data is intentionally kept outside the DuckDB database because individual host genomes can be very large. The files below provide the link between phage records and their associated bacterial host assemblies.

The pipeline produces the following host-related files in `/data/processed/sequences/` (inside Docker):

| File | Type | Description |
|------|------|-------------|
| `phage_host_candidates.csv` | CSV file | One row per (Phage_ID, token): lossless record of every host candidate parsed from the raw Host field. Used for auditing and traceability. |
| `phage_host_assemblies.csv` | CSV file | One row per (Phage_ID, Assembly_Accession): authoritative flat mapping of phages to resolved NCBI assembly accessions. Drives genome downloads. |
| `phage_host_links.csv` | CSV file | One row per unique (Phage_ID, Assembly_Accession) pair. Backward-compatible output used by the `pbi` package to retrieve phage–host pairs. |
| `host_metadata.csv` | CSV file | One row per unique assembly: per-assembly metadata (level, RefSeq category, quality score, etc.). |
| `assembly_metadata.csv` | CSV file | Detailed NCBI assembly metadata for each downloaded host genome. |
| `host_fasta_mapping.json` | JSON file | Maps each host assembly accession (e.g. `GCF_000005845.2`) to the path of its downloaded FASTA file. Used by `SequenceRetriever` for fast on-demand access. |
| Individual FASTA files | FASTA (`.fna`) | One file per downloaded host assembly, stored under `hosts/`. |

### Key Columns in `phage_host_links.csv`

| Column | Description |
|--------|-------------|
| `Phage_ID` | Phage identifier (matches `fact_phages.Phage_ID`) |
| `Assembly_Accession` | Resolved NCBI assembly accession |
| `Host_Raw` | Original un-parsed Host field (traceability) |
| `Confidence` | Float 0–1 indicating resolution confidence |
| `Resolution_Source` | How the accession was resolved (`accession_in_host_field` / `species_to_taxid_to_assembly` / `fallback`) |

See [Host Resolution Details](host-resolution.md) for a full description of how host fields are parsed and resolved to NCBI assemblies.

---

## Data Sources

The database integrates data from **14 major phage databases** via PhageScope:

| Database | Type | Approx. Records | Focus Area |
|----------|------|-----------------|------------|
| **GenBank** | General | ~200,000 | Comprehensive phage collection |
| **RefSeq** | Curated | ~15,000 | Reference phage genomes |
| **PhagesDB** | Specialized | ~2,000 | Mycobacteriophages |
| **EMBL** | European | ~50,000 | European phage data |
| **DDBJ** | Japanese | ~30,000 | Japanese phage data |
| **GOV2** | Viral genomes | ~100,000 | Ocean viral genomes |
| **MGV** | Metagenomics | ~50,000 | Gut virome data |
| **GVD** | Metagenomics | ~40,000 | Global virome database |
| **IMGVR** | IMG/VR | ~30,000 | IMG viral database |
| **GPD** | Specialized | ~20,000 | Gut phage database |
| **CHVD** | Specialized | ~5,000 | Chicken virome data |
| **STV** | Environmental | ~3,000 | Soil/plant phages |
| **TemPhD** | Specialized | ~2,000 | Temperate phages |
| **IGVD** | Specialized | ~1,000 | Insect gut viruses |

## Indexes and Optimization

The database includes **14 targeted indexes** for optimal query performance:

### Primary Key Indexes
- `fact_phages.Phage_ID`
- `dim_proteins.Protein_ID`
- `dim_trna_tmrna.trna_tmrna_id`

### Foreign Key Indexes
All dimension tables have indexes on `Phage_ID` for efficient joins.

### Source Tracking Indexes
All tables include indexes on `Source_DB` for source-based filtering.

### Example Optimized Queries

```sql
-- Fast: Uses Phage_ID index
SELECT * FROM dim_proteins 
WHERE Phage_ID = 'NC_000866';

-- Fast: Uses Source_DB index
SELECT COUNT(*) FROM fact_phages 
WHERE Source_DB = 'GenBank';

-- Fast: Uses both indexes
SELECT p.* 
FROM dim_proteins p
JOIN fact_phages f ON p.Phage_ID = f.Phage_ID
WHERE f.Source_DB = 'RefSeq' AND f.Length > 100000;
```

## Analytical Views

The database includes pre-built views for common analyses:

### `phage_summary`
Aggregated statistics by data source.

```sql
SELECT * FROM phage_summary;
```

### `phage_complete_profile`
Comprehensive phage characterization with all dimension counts.

```sql
SELECT * FROM phage_complete_profile 
WHERE protein_count > 100;
```

### `phage_size_distribution`
Genome size categorization analysis.

```sql
SELECT * FROM phage_size_distribution;
```

## Data Validation & Quality

### Automated Validation

The pipeline performs comprehensive quality control:

1. **Schema Validation**
   - Table existence verification (all 9 tables)
   - Column presence and data type checks
   - Index verification

2. **Data Integrity**
   - Duplicate detection (Phage_ID, Protein_ID, etc.)
   - Orphaned record detection (foreign key consistency)
   - NULL value distribution analysis

3. **Statistical Validation**
   - Row count summaries
   - Source distribution analysis
   - Numerical range validation (genome sizes, GC content, TMH counts)

4. **Relationship Verification**
   - Foreign key consistency across all dimension tables
   - Source database alignment

### Validation Reports

HTML reports are generated with:
- Visual database schema diagram
- Row count statistics for all tables
- Data quality metrics with pass/fail indicators
- Distribution charts for key metrics
- Warning flags for data quality issues

**View Reports:**

Reports are generated in the `workflow/reports/` directory after running the pipeline. They include:
- Database Validation Report
- Phage Metadata Report
- Annotated Proteins Report
- And more for each data type

### Database Validation Report

!!! note "Report scope"
    The validation report below was generated **before host data was added** to the pipeline. It reflects the state of the DuckDB database (all phage tables) and does not yet include host-phage link statistics.

The full interactive report is embedded below. You can also [open it in a new tab](../reports/database_validation.html){target="_blank"}.

<div style="border: 1px solid #ccc; border-radius: 4px; overflow: hidden; margin: 1rem 0;">
<iframe src="../../reports/database_validation.html" width="100%" height="900px" style="border: none; display: block;"></iframe>
</div>

## Sequence Files

In addition to the database, the pipeline generates indexed FASTA files:

### Phage Genomes
- **File**: `data/sequences/all_phages.fasta`
- **Index**: `data/sequences/all_phages.fasta.fai`
- **Size**: ~40 GB
- **Records**: ~873,000 phage genomes

### Protein Sequences
- **File**: `data/sequences/all_proteins.fasta`
- **Index**: `data/sequences/all_proteins.fasta.fai`
- **Size**: ~60 GB
- **Records**: ~43 million protein sequences

Both files are indexed with **pyfaidx** for fast random access.

## Usage Examples

### Python/DuckDB

```python
import duckdb

# Connect to database
conn = duckdb.connect('data/databases/phage_database_optimized.duckdb')

# Get database statistics
stats = conn.execute("""
    SELECT 
        (SELECT COUNT(*) FROM fact_phages) as phages,
        (SELECT COUNT(*) FROM dim_proteins) as proteins,
        (SELECT COUNT(*) FROM dim_trna_tmrna) as trna
""").fetchone()

print(f"Phages: {stats[0]:,}")
print(f"Proteins: {stats[1]:,}")
print(f"tRNA/tmRNA: {stats[2]:,}")

# Complex analytical query
results = conn.execute("""
    SELECT 
        f.Source_DB,
        COUNT(DISTINCT f.Phage_ID) as phage_count,
        AVG(f.Length) as avg_length,
        AVG(f.GC_content) as avg_gc,
        COUNT(DISTINCT p.Protein_ID) as protein_count
    FROM fact_phages f
    LEFT JOIN dim_proteins p ON f.Phage_ID = p.Phage_ID
    GROUP BY f.Source_DB
    ORDER BY phage_count DESC
""").df()

print(results)

conn.close()
```

### SQL Queries

```sql
-- Find large phages with many proteins
SELECT 
    f.Phage_ID,
    f.Length,
    f.Host,
    COUNT(p.Protein_ID) as protein_count
FROM fact_phages f
JOIN dim_proteins p ON f.Phage_ID = p.Phage_ID
WHERE f.Length > 200000
GROUP BY f.Phage_ID, f.Length, f.Host
HAVING COUNT(p.Protein_ID) > 200
ORDER BY f.Length DESC;

-- Analyze tRNA distribution
SELECT 
    trna_type,
    COUNT(*) as count,
    COUNT(DISTINCT Phage_ID) as phage_count
FROM dim_trna_tmrna
WHERE trna_type IS NOT NULL
GROUP BY trna_type
ORDER BY count DESC;

-- Find phages with anti-CRISPR systems
SELECT 
    f.Phage_ID,
    f.Host,
    f.Lifestyle,
    COUNT(a.Protein_ID) as anti_crispr_count
FROM fact_phages f
JOIN dim_anti_crispr a ON f.Phage_ID = a.Phage_ID
GROUP BY f.Phage_ID, f.Host, f.Lifestyle
HAVING COUNT(a.Protein_ID) > 0
ORDER BY anti_crispr_count DESC;
```

## Performance Considerations

- **Database Size**: ~15 GB (optimized with columnar storage)
- **Query Performance**: Fast analytical queries thanks to indexes and columnar format
- **Memory Usage**: DuckDB is memory-efficient, but complex queries may need >8 GB RAM
- **Disk I/O**: Use SSD for better performance

## Next Steps

- [API Reference](../api/overview.md) - Query the database via REST API
- [Command Reference](../reference/commands.md) - Common database operations
- [Installation Guide](../guides/installation.md) - Set up your local environment

---

**Note**: The database is read-only in production. For updates, re-run the pipeline with updated source data.

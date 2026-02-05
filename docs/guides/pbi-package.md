# PBI Package Usage Guide

The `pbi` package provides a simple Python interface for accessing and querying the PBI (Phage Bacteria Interaction) database. This guide covers the main features and usage patterns.

## Installation

The `pbi` package is automatically available when using the Docker analysis container or when installed locally from the repository.

```bash
# For local installation
cd /path/to/PBI
pip install -e .
```

## Quick Start

The easiest way to get started is using the `quick_connect()` function:

```python
from pbi import quick_connect

# Connect to database (automatically uses correct paths in Docker)
retriever = quick_connect()

# Get database statistics
stats = retriever.get_stats()
print(f"Total phages: {stats['database']['phages']:,}")
```

## Core Classes

### SequenceRetriever

The main class for interacting with the database and retrieving sequences.

```python
from pbi import SequenceRetriever

# Manual initialization (if not using quick_connect)
retriever = SequenceRetriever(
    db_path="/path/to/phage_database.duckdb",
    phage_fasta_path="/path/to/all_phages.fasta",
    protein_fasta_path="/path/to/all_proteins.fasta",
    host_mapping_path="/path/to/host_fasta_mapping.json"  # Optional
)
```

### NegativeExampleGenerator

For generating negative training examples for machine learning models.

```python
from pbi import NegativeExampleGenerator

# Create generator
neg_gen = NegativeExampleGenerator(retriever)

# Generate balanced dataset
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=pairs,
    strategy='mixed',
    positive_ratio=0.5
)
```

## Retrieving Metadata

### Phage Metadata

Get metadata for phages without retrieving sequences:

```python
# Get all phage metadata
metadata = retriever.get_phage_metadata()

# Filter by source database
phagesdb = retriever.get_phage_metadata("Source_DB = 'PhagesDB'", limit=1000)

# Filter by lifestyle
lytic_phages = retriever.get_phage_metadata("Lifestyle = 'Lytic'")

# Filter by completeness
complete = retriever.get_phage_metadata("Completeness = 'Complete'")

# Combine filters
large_lytic = retriever.get_phage_metadata(
    "Lifestyle = 'Lytic' AND Length > 100000"
)
```

**Available Metadata Fields:**
- `Phage_ID` - Unique identifier
- `Source_DB` - Source database (RefSeq, GenBank, PhagesDB, etc.)
- `Length` - Genome length in base pairs
- `GC_content` - GC content percentage
- `Taxonomy` - Taxonomic classification
- `Completeness` - Genome completeness status
- `Host` - Host organism name
- `Lifestyle` - Temperate/Lytic/Unknown
- `Cluster` - Cluster assignment
- `Subcluster` - Subcluster assignment

### Host Metadata

Get metadata for bacterial hosts:

```python
# Get all host metadata
hosts = retriever.get_host_metadata()

# Filter by species
ecoli = retriever.get_host_metadata("Species_Name LIKE '%Escherichia%'")

# Filter by assembly quality
complete_genomes = retriever.get_host_metadata(
    "Assembly_Level = 'Complete Genome'"
)

# Filter by RefSeq status
reference = retriever.get_host_metadata("RefSeq_Category = 'reference genome'")
```

**Available Metadata Fields:**
- `Host_ID` - Unique identifier
- `Species_Name` - Bacterial species
- `Strain_Name` - Strain designation
- `Assembly_Accession` - NCBI assembly ID
- `Assembly_Name` - Assembly name
- `Assembly_Level` - Quality level (Complete Genome, Chromosome, Scaffold, Contig)
- `Genome_Length` - Host genome size
- `GC_Content` - Host GC percentage
- `RefSeq_Category` - Reference genome status
- `Download_Date` - When downloaded
- `Source` - Data source

### Combined Phage-Host Metadata

Get metadata for phage-host interaction pairs:

```python
# Get all pairs metadata
pairs_meta = retriever.get_phage_host_metadata()

# Filter by phage source
phagesdb_pairs = retriever.get_phage_host_metadata(
    "p.Source_DB = 'PhagesDB'", 
    limit=1000
)

# Filter by lifestyle
lytic_pairs = retriever.get_phage_host_metadata("p.Lifestyle = 'Lytic'")

# Complex filters
quality_pairs = retriever.get_phage_host_metadata(
    "p.Completeness = 'Complete' AND h.Assembly_Level = 'Complete Genome'"
)
```

**Available Fields:**
- All phage metadata fields (prefixed with `Phage_`)
- All host metadata fields (prefixed with `Host_`)

## Retrieving Sequences

### Phage Sequences

```python
# Query-based retrieval
phages = retriever.get_phage_sequences(
    "SELECT Phage_ID FROM fact_phages WHERE Length > 50000",
    limit=100
)

# Direct ID-based retrieval
sequences = retriever.get_sequences_by_ids(
    phage_ids=['NC_000866', 'NC_001416'],
    sequence_type='phage'
)
```

### Protein Sequences

```python
# Get proteins by query
proteins = retriever.get_protein_sequences(
    "SELECT Protein_ID FROM dim_proteins WHERE Molecular_weight > 50000",
    limit=100
)

# Get proteins for a specific phage
proteins = retriever.get_protein_sequences_by_phage('NC_000866')
```

### Host Sequences

```python
# Get host sequences
hosts = retriever.get_host_sequences(
    "SELECT Host_ID FROM dim_hosts WHERE Species_Name LIKE '%Escherichia%'",
    limit=10
)
```

### Phage-Host Pairs with Sequences

Get interaction pairs with both sequences and metadata:

```python
# Get all pairs
pairs = retriever.get_phage_host_pairs()

# Filter by phage source
pairs = retriever.get_phage_host_pairs(
    "p.Source_DB = 'PhagesDB'", 
    limit=1000
)

# Filter by lifestyle
pairs = retriever.get_phage_host_pairs("p.Lifestyle = 'Lytic'")

# Filter by host assembly quality
pairs = retriever.get_phage_host_pairs(
    "h.Assembly_Level = 'Complete Genome'"
)

# Multiple filters
pairs = retriever.get_phage_host_pairs(
    "p.Lifestyle = 'Lytic' AND p.Length > 50000 AND h.Assembly_Level = 'Complete Genome'",
    limit=5000
)
```

**Returned DataFrame includes:**
- Sequences: `Phage_Sequence`, `Host_Sequence`
- Metadata: `Phage_Source`, `Phage_Taxonomy`, `Phage_Completeness`, `Phage_Lifestyle`, 
  `Phage_Cluster`, `Phage_Subcluster`, `Species_Name`, `Host_Assembly_Level`, 
  `Host_RefSeq_Category`
- Metrics: `Phage_Length`, `Phage_GC`, `Host_Length`, `Host_GC`

## Exporting Data

### Export to FASTA

```python
# Export phages to FASTA
retriever.export_fasta(
    phages_df, 
    "output_phages.fasta", 
    id_col='Phage_ID'
)

# Export proteins to FASTA
retriever.export_fasta(
    proteins_df, 
    "output_proteins.fasta",
    id_col='Protein_ID'
)
```

## Database Statistics

```python
stats = retriever.get_stats()

# Access statistics
print(f"Phages in database: {stats['database']['phages']:,}")
print(f"Proteins in database: {stats['database']['proteins']:,}")
print(f"Hosts in database: {stats['database']['hosts']:,}")
print(f"Phage-host associations: {stats['database']['phage_host_associations']:,}")

print(f"Phages in FASTA: {stats['fasta']['phages']:,}")
print(f"Proteins in FASTA: {stats['fasta']['proteins']:,}")
print(f"Hosts in FASTA: {stats['fasta']['hosts']:,}")
```

## Advanced SQL Queries

You can use SQL queries directly for complex filtering:

```python
# Complex phage query
query = """
SELECT Phage_ID 
FROM fact_phages 
WHERE Length > 50000 
  AND GC_content BETWEEN 40 AND 60
  AND Lifestyle = 'Lytic'
  AND Source_DB IN ('PhagesDB', 'RefSeq')
"""
phages = retriever.get_phage_sequences(query)

# Complex protein query
query = """
SELECT p.Protein_ID
FROM dim_proteins p
JOIN fact_phages ph ON p.Phage_ID = ph.Phage_ID
WHERE p.Molecular_weight > 50000
  AND ph.Source_DB = 'PhagesDB'
"""
proteins = retriever.get_protein_sequences(query)
```

## Working with DataFrames

All retrieval methods return pandas DataFrames for easy data manipulation:

```python
import pandas as pd

# Get metadata
phages = retriever.get_phage_metadata()

# Filter and analyze
lytic = phages[phages['Lifestyle'] == 'Lytic']
print(f"Average length of lytic phages: {lytic['Length'].mean():.0f} bp")

# Group by source
by_source = phages.groupby('Source_DB').agg({
    'Phage_ID': 'count',
    'Length': 'mean',
    'GC_content': 'mean'
})
print(by_source)

# Export to CSV
phages.to_csv('phage_metadata.csv', index=False)
```

## Error Handling

```python
try:
    # Attempt to get host data
    hosts = retriever.get_host_metadata()
except ValueError as e:
    print(f"Host data not available: {e}")
    print("Run the host genome download workflow first")
except FileNotFoundError as e:
    print(f"Database file not found: {e}")
```

## Best Practices

1. **Use `quick_connect()` in Docker**: It automatically finds the correct paths
2. **Use metadata methods for exploration**: They're faster than retrieving sequences
3. **Apply filters in SQL**: More efficient than filtering DataFrames
4. **Limit results during development**: Use `limit` parameter to test queries
5. **Close connections**: Call `retriever.close()` when done

```python
# Example workflow
retriever = quick_connect()

try:
    # Explore metadata first
    meta = retriever.get_phage_metadata("Source_DB = 'PhagesDB'", limit=10)
    print(f"Found {len(meta)} phages")
    
    # Get specific IDs
    phage_ids = meta['Phage_ID'].tolist()
    
    # Retrieve sequences only for needed phages
    sequences = retriever.get_sequences_by_ids(phage_ids, sequence_type='phage')
    
    # Export results
    retriever.export_fasta(sequences, "selected_phages.fasta")
    
finally:
    retriever.close()
```

## Complete Example

Here's a complete example workflow:

```python
from pbi import quick_connect
import pandas as pd

# Connect
retriever = quick_connect()

# Get statistics
stats = retriever.get_stats()
print(f"Database contains {stats['database']['phages']:,} phages")

# Explore phage metadata
phages = retriever.get_phage_metadata()
print(f"\nSource distribution:")
print(phages['Source_DB'].value_counts())

print(f"\nLifestyle distribution:")
print(phages['Lifestyle'].value_counts())

# Get high-quality phage-host pairs
pairs = retriever.get_phage_host_pairs(
    where_clause="""
        p.Completeness = 'Complete' 
        AND p.Lifestyle = 'Lytic'
        AND h.Assembly_Level = 'Complete Genome'
    """,
    limit=1000
)

print(f"\nFound {len(pairs)} high-quality pairs")
print(f"Unique phages: {pairs['Phage_ID'].nunique()}")
print(f"Unique hosts: {pairs['Host_ID'].nunique()}")

# Export pairs
pairs[['Phage_ID', 'Host_ID', 'Phage_Source', 'Species_Name']].to_csv(
    'phage_host_pairs.csv',
    index=False
)

# Close connection
retriever.close()
print("\n✅ Done!")
```

## Getting Help

```python
# Print available methods and examples
retriever.help()
```

## Next Steps

- See [Machine Learning Guide](machine-learning.md) for ML dataset preparation
- See [Analysis Guide](analysis-guide.md) for Jupyter notebook usage
- Check example notebooks in the `notebooks/` directory
- Refer to the [Database Schema](../database/overview.md) for available tables and fields

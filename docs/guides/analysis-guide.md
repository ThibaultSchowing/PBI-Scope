# Direct Data Access Guide

This guide explains how to efficiently access and analyze the PBI database using the dedicated analysis container, bypassing the REST API overhead for bulk operations.

## 🎯 Overview

The PBI analysis container provides **direct access** to the DuckDB database and FASTA files, enabling:

- **5-50x faster** bulk data retrieval compared to the REST API
- **Batch processing** of millions of records without memory issues
- **Safe read-only access** to production data
- **Interactive analysis** with Jupyter Lab
- **Zero network overhead** - direct file system access

## 🏗️ Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Pipeline   │────▶│  pbi-data    │◀────│   Analysis   │
│  (writes)    │     │   volume     │     │  (read-only) │
└──────────────┘     └──────────────┘     └──────────────┘
                           │
                           │
                     ┌─────┴─────┐
                     │    API    │
                     │(read-only)│
                     └───────────┘
```

**Key Design Principles:**

- **Shared Volume, Separate Services**: Pipeline writes data, analysis reads it
- **Read-Only Mounts**: `:ro` flag prevents accidental data corruption
- **Direct File Access**: Zero network overhead
- **Batch Processing**: Process large datasets in chunks to avoid OOM errors
- **Hybrid Approach**: DuckDB for metadata + SequenceRetriever for sequences

## 🚀 Quick Start

### 1. Build and Start the Analysis Service

```bash
# Build the analysis container
docker compose build analysis

# Start the analysis service
docker compose up -d analysis

# Access Jupyter Lab
# Open http://localhost:8888 in your browser
```

### 2. Open Example Notebook

Navigate to `notebooks/analysis_direct_access_guide.ipynb` in Jupyter Lab to see complete examples.

### 3. Create Your First Analysis

Create a new notebook in Jupyter Lab:

```python
import duckdb
from pathlib import Path
from pbi import SequenceRetriever

# Connect to database (read-only)
DB_PATH = "/data/processed/databases/phage_database_optimized.duckdb"
conn = duckdb.connect(DB_PATH, read_only=True)

# Query phages
query = """
SELECT Phage_ID, Accession, Length, GC_Content
FROM fact_phages
WHERE Length > 100000
LIMIT 10
"""
df = conn.execute(query).fetchdf()
print(df)

# Initialize SequenceRetriever
retriever = SequenceRetriever(
    db_path=DB_PATH,
    phage_fasta_path="/data/processed/sequences/all_phages.fasta",
    protein_fasta_path="/data/processed/sequences/all_proteins.fasta",
    host_mapping_path="/data/processed/sequences/host_fasta_mapping.json"
)

# Get sequences
phage_ids = df['Phage_ID'].tolist()
sequences = retriever.get_sequences_by_ids(phage_ids, sequence_type='phage')

# Cleanup
conn.close()
```

## 📊 Common Use Cases

### Use Case 1: Bulk Metadata Export

Export large datasets efficiently using DuckDB's native capabilities:

```python
import duckdb

conn = duckdb.connect("/data/processed/databases/phage_database_optimized.duckdb", 
                      read_only=True)

# Export to Parquet (most efficient)
query = """
COPY (
    SELECT p.*, ph.Host_Name, ph.Host_Genus
    FROM fact_phages p
    LEFT JOIN fact_phage_host ph ON p.Phage_ID = ph.Phage_ID
    WHERE p.Length > 50000
) TO '/workspace/exports/large_phages.parquet' (FORMAT PARQUET)
"""
conn.execute(query)

# Export to CSV
query = """
COPY (
    SELECT * FROM fact_phages
    WHERE Completeness = 'complete'
) TO '/workspace/exports/complete_phages.csv' (HEADER, DELIMITER ',')
"""
conn.execute(query)

conn.close()
```

**Performance**: Exports millions of records in seconds, compared to minutes via API.

### Use Case 2: Batch Sequence Retrieval

Retrieve sequences for thousands of phages efficiently:

```python
from pbi import SequenceRetriever
import duckdb
import pandas as pd

# Get phage IDs from database
conn = duckdb.connect("/data/processed/databases/phage_database_optimized.duckdb",
                      read_only=True)
query = """
SELECT Phage_ID FROM fact_phages
WHERE Completeness = 'complete' AND Length > 50000
"""
phage_ids_df = conn.execute(query).fetchdf()
conn.close()

# Process in batches to avoid memory issues
retriever = SequenceRetriever(
    db_path="/data/processed/databases/phage_database_optimized.duckdb",
    phage_fasta_path="/data/processed/sequences/all_phages.fasta",
    protein_fasta_path="/data/processed/sequences/all_proteins.fasta"
)

BATCH_SIZE = 1000
all_sequences = {}

for i in range(0, len(phage_ids_df), BATCH_SIZE):
    batch_ids = phage_ids_df.iloc[i:i+BATCH_SIZE]['Phage_ID'].tolist()
    batch_sequences = retriever.get_sequences_by_ids(batch_ids, sequence_type='phage')
    all_sequences.update(batch_sequences)
    print(f"Processed {i + len(batch_sequences)} sequences...")
```

**Performance**: Retrieves ~1000 sequences per second using indexed FASTA access.

### Use Case 3: Complex Joins and Analysis

Combine multiple tables for sophisticated analyses:

```python
import duckdb
import pandas as pd
import matplotlib.pyplot as plt

conn = duckdb.connect("/data/processed/databases/phage_database_optimized.duckdb",
                      read_only=True)

# Find phages with specific protein annotations
query = """
SELECT 
    p.Phage_ID,
    p.Accession,
    p.Length,
    p.GC_Content,
    COUNT(DISTINCT pr.Protein_ID) as Protein_Count,
    ph.Host_Genus,
    ph.Host_Name
FROM fact_phages p
LEFT JOIN fact_proteins pr ON p.Phage_ID = pr.Phage_ID
LEFT JOIN fact_phage_host ph ON p.Phage_ID = ph.Phage_ID
WHERE pr.Annotation LIKE '%terminase%'
GROUP BY p.Phage_ID, p.Accession, p.Length, p.GC_Content, 
         ph.Host_Genus, ph.Host_Name
HAVING COUNT(DISTINCT pr.Protein_ID) > 0
ORDER BY p.Length DESC
"""

results = conn.execute(query).fetchdf()
conn.close()

# Visualize
plt.figure(figsize=(10, 6))
plt.scatter(results['Length'] / 1000, results['GC_Content'] * 100, 
            alpha=0.6, s=50)
plt.xlabel('Genome Length (kb)')
plt.ylabel('GC Content (%)')
plt.title('Phages with Terminase Proteins')
plt.tight_layout()
plt.savefig('/workspace/exports/terminase_phages.png', dpi=300)
plt.show()
```

### Use Case 4: Machine Learning Dataset Preparation

Prepare datasets for ML models:

```python
from pbi import SequenceRetriever, NegativeExampleGenerator
import duckdb

# Connect to database
conn = duckdb.connect("/data/processed/databases/phage_database_optimized.duckdb",
                      read_only=True)

# Get positive examples (known phage-host pairs)
positive_query = """
SELECT 
    p.Phage_ID,
    ph.Host_ID,
    p.Length as Phage_Length,
    p.GC_Content as Phage_GC,
    ph.Host_Name
FROM fact_phages p
INNER JOIN fact_phage_host ph ON p.Phage_ID = ph.Phage_ID
WHERE p.GC_Content IS NOT NULL
  AND p.Length > 10000
"""
positive_pairs = conn.execute(positive_query).fetchdf()
conn.close()

# Initialize retriever
retriever = SequenceRetriever(
    db_path="/data/processed/databases/phage_database_optimized.duckdb",
    phage_fasta_path="/data/processed/sequences/all_phages.fasta",
    protein_fasta_path="/data/processed/sequences/all_proteins.fasta",
    host_mapping_path="/data/processed/sequences/host_fasta_mapping.json"
)

# Generate negative examples
neg_gen = NegativeExampleGenerator(retriever)
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=positive_pairs,
    strategy='mixed',
    positive_ratio=0.5
)

# Export for training
dataset.to_parquet('/workspace/exports/phage_host_ml_dataset.parquet')
print(f"Dataset created: {len(dataset)} samples")
```

## ⚙️ Configuration

### Docker Compose Service

The analysis service is defined in `docker-compose.yml`:

```yaml
analysis:
  build:
    context: .
    dockerfile: Dockerfile.analysis
  container_name: pbi-analysis
  ports:
    - "8888:8888"
  volumes:
    # Read-only access to data
    - pbi-data:/data:ro
    # Persistent notebook storage
    - ./notebooks:/workspace
  environment:
    - DATA_PATH=/data/processed
  networks:
    - pbi-network
  restart: unless-stopped
```

### Environment Variables

- `DATA_PATH`: Base path for processed data (default: `/data/processed`)

### Volume Mounts

- `pbi-data:/data:ro` - **Read-only** access to database and FASTA files
- `./notebooks:/workspace` - Persistent storage for notebooks and exports

## 🎓 Best Practices

### 1. Always Use Read-Only Connections

```python
# ✅ GOOD: Read-only connection
conn = duckdb.connect(db_path, read_only=True)

# ❌ BAD: Writable connection (risk of corruption)
conn = duckdb.connect(db_path)
```

**Why?** The data volume is mounted as `:ro` (read-only) to prevent accidental modifications. Additionally, using `read_only=True` in DuckDB prevents database lock conflicts.

### 2. Process Data in Batches

```python
# ✅ GOOD: Batch processing
BATCH_SIZE = 1000
for offset in range(0, total_count, BATCH_SIZE):
    query = f"SELECT * FROM fact_phages LIMIT {BATCH_SIZE} OFFSET {offset}"
    batch = conn.execute(query).fetchdf()
    # Process batch...

# ❌ BAD: Loading everything at once
all_data = conn.execute("SELECT * FROM fact_phages").fetchdf()  # 800K+ rows!
```

**Why?** Loading millions of records into memory will cause out-of-memory errors and crash the Jupyter kernel.

### 3. Use DuckDB's Native Export Functions

```python
# ✅ GOOD: Direct export (fast, memory-efficient)
conn.execute("""
    COPY (SELECT * FROM fact_phages WHERE Length > 50000)
    TO '/workspace/exports/large_phages.parquet' (FORMAT PARQUET)
""")

# ❌ BAD: Load then export (slow, memory-intensive)
df = conn.execute("SELECT * FROM fact_phages WHERE Length > 50000").fetchdf()
df.to_parquet('/workspace/exports/large_phages.parquet')
```

**Why?** DuckDB can stream results directly to disk without loading into memory, making it orders of magnitude faster for large datasets.

### 4. Filter Data in SQL, Not Pandas

```python
# ✅ GOOD: Filter in database
query = """
SELECT * FROM fact_phages
WHERE Length > 50000 AND Completeness = 'complete'
"""
df = conn.execute(query).fetchdf()

# ❌ BAD: Load everything then filter
all_phages = conn.execute("SELECT * FROM fact_phages").fetchdf()
filtered = all_phages[(all_phages['Length'] > 50000) & 
                      (all_phages['Completeness'] == 'complete')]
```

**Why?** Filtering in SQL is faster and more memory-efficient, as only the filtered data is transferred.

### 5. Close Connections Properly

```python
# ✅ GOOD: Ensure cleanup
try:
    conn = duckdb.connect(db_path, read_only=True)
    # Work...
finally:
    conn.close()

# Or use context manager
with duckdb.connect(db_path, read_only=True) as conn:
    # Work...
# Auto-closes
```

**Why?** Proper cleanup prevents resource leaks and ensures database locks are released.

### 6. Monitor Memory Usage

```python
# Check memory usage in notebook
import psutil
import os

process = psutil.Process(os.getpid())
memory_mb = process.memory_info().rss / 1024 / 1024
print(f"Current memory usage: {memory_mb:.2f} MB")
```

## 🐛 Troubleshooting

### Issue 1: "Database is locked" Error

**Symptom:**
```
duckdb.IOException: IO Error: Could not set lock on file
```

**Solutions:**
1. Ensure you're using `read_only=True`:
   ```python
   conn = duckdb.connect(db_path, read_only=True)
   ```

2. Check if another process has the database open in write mode

3. Verify the volume is mounted as read-only (`:ro`)

### Issue 2: Out of Memory Errors

**Symptom:**
```
MemoryError: Unable to allocate array
```
or kernel crashes

**Solutions:**
1. Reduce batch size:
   ```python
   BATCH_SIZE = 1000  # Instead of 10000
   ```

2. Use DuckDB aggregations instead of loading raw data:
   ```python
   # Good: Aggregate in database
   stats = conn.execute("SELECT AVG(Length), STD(Length) FROM fact_phages").fetchdf()
   
   # Bad: Load all data
   all_lengths = conn.execute("SELECT Length FROM fact_phages").fetchdf()
   ```

3. Stream results to disk using `COPY`:
   ```python
   conn.execute("COPY (...) TO 'output.parquet'")
   ```

4. Monitor memory and restart kernel if needed

### Issue 3: Slow Sequence Retrieval

**Symptom:**
Retrieving sequences takes several minutes

**Solutions:**
1. Verify FASTA index files exist:
   ```python
   from pathlib import Path
   fasta_file = Path("/data/processed/sequences/all_phages.fasta")
   index_file = Path(str(fasta_file) + ".fai")
   print(f"Index exists: {index_file.exists()}")
   ```

2. Retrieve sequences in batches, not individually:
   ```python
   # Good: Batch retrieval
   sequences = retriever.get_sequences_by_ids(phage_ids)
   
   # Bad: Individual retrieval
   for phage_id in phage_ids:
       seq = retriever.get_sequences_by_ids([phage_id])
   ```

3. Use `preload=True` when initializing SequenceRetriever

### Issue 4: Jupyter Lab Not Accessible

**Symptom:**
Cannot connect to http://localhost:8888

**Solutions:**
1. Check if container is running:
   ```bash
   docker ps | grep pbi-analysis
   ```

2. Check logs for errors:
   ```bash
   docker logs pbi-analysis
   ```

3. Verify port mapping:
   ```bash
   docker port pbi-analysis
   ```

4. Restart the service:
   ```bash
   docker compose restart analysis
   ```

### Issue 5: Path Not Found Errors

**Symptom:**
```
FileNotFoundError: /data/processed/databases/phage_database_optimized.duckdb
```

**Solutions:**
1. Verify you're running in the Docker container (not locally)

2. Check if pipeline has completed:
   ```bash
   docker compose run --rm pipeline
   ```

3. Inspect volume contents:
   ```bash
   docker run --rm -v pbi-data:/data alpine ls -lh /data/processed/databases
   ```

4. Ensure paths use `/data/processed` (Docker) not `./data/processed` (local)

## 📈 Performance Tips

### Optimize SQL Queries

1. **Use appropriate indexes** (already optimized in PBI database)

2. **Select only needed columns**:
   ```python
   # Good
   SELECT Phage_ID, Length, GC_Content FROM fact_phages
   
   # Bad
   SELECT * FROM fact_phages
   ```

3. **Use LIMIT for exploration**:
   ```python
   # Explore data structure with small sample
   sample = conn.execute("SELECT * FROM fact_phages LIMIT 100").fetchdf()
   ```

4. **Leverage WHERE clauses**:
   ```python
   WHERE Length > 50000 AND Completeness = 'complete'
   ```

### Parallel Processing

For CPU-intensive tasks, use multiprocessing:

```python
from multiprocessing import Pool
from functools import partial

def process_batch(batch_ids, retriever):
    sequences = retriever.get_sequences_by_ids(batch_ids, sequence_type='phage')
    # Process sequences...
    return results

# Split IDs into batches
batches = [phage_ids[i:i+1000] for i in range(0, len(phage_ids), 1000)]

# Process in parallel (careful with memory!)
with Pool(processes=4) as pool:
    results = pool.map(partial(process_batch, retriever=retriever), batches)
```

**⚠️ Note**: Be careful with memory when using parallel processing. Monitor usage closely.

### Caching Results

Cache expensive computations:

```python
import pickle
from pathlib import Path

cache_file = Path("/workspace/.cache/expensive_query.pkl")

if cache_file.exists():
    # Load from cache
    with open(cache_file, 'rb') as f:
        results = pickle.load(f)
else:
    # Compute and cache
    results = conn.execute(expensive_query).fetchdf()
    cache_file.parent.mkdir(exist_ok=True)
    with open(cache_file, 'wb') as f:
        pickle.dump(results, f)
```

## 🔄 Workflow Example: Complete Analysis Pipeline

Here's a complete example analyzing E. coli phages:

```python
import duckdb
from pbi import SequenceRetriever
import pandas as pd
import matplotlib.pyplot as plt
from Bio.SeqUtils import gc_fraction
from Bio.Seq import Seq

# 1. Setup
DB_PATH = "/data/processed/databases/phage_database_optimized.duckdb"
conn = duckdb.connect(DB_PATH, read_only=True)

# 2. Query E. coli phages
query = """
SELECT DISTINCT
    p.Phage_ID,
    p.Accession,
    p.Length,
    p.GC_Content,
    ph.Host_Name
FROM fact_phages p
INNER JOIN fact_phage_host ph ON p.Phage_ID = ph.Phage_ID
WHERE (ph.Host_Genus LIKE '%Escherichia%' 
       OR ph.Host_Name LIKE '%coli%')
  AND p.GC_Content IS NOT NULL
ORDER BY p.Length DESC
"""
ecoli_phages = conn.execute(query).fetchdf()
print(f"Found {len(ecoli_phages)} E. coli phages")

# 3. Visualize distribution
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].hist(ecoli_phages['Length'] / 1000, bins=50, edgecolor='black')
axes[0].set_xlabel('Genome Length (kb)')
axes[0].set_title('E. coli Phage Length Distribution')

axes[1].hist(ecoli_phages['GC_Content'] * 100, bins=50, edgecolor='black')
axes[1].set_xlabel('GC Content (%)')
axes[1].set_title('E. coli Phage GC Distribution')

plt.tight_layout()
plt.savefig('/workspace/exports/ecoli_phages_analysis.png', dpi=300)

# 4. Retrieve sequences (sample)
retriever = SequenceRetriever(
    db_path=DB_PATH,
    phage_fasta_path="/data/processed/sequences/all_phages.fasta",
    protein_fasta_path="/data/processed/sequences/all_proteins.fasta"
)

sample_ids = ecoli_phages.head(100)['Phage_ID'].tolist()
sequences = retriever.get_sequences_by_ids(sample_ids, sequence_type='phage')

# 5. Calculate sequence statistics
seq_stats = []
for phage_id, seq_str in sequences.items():
    seq = Seq(seq_str)
    seq_stats.append({
        'Phage_ID': phage_id,
        'Calculated_GC': gc_fraction(seq),
        'A_count': seq_str.count('A'),
        'T_count': seq_str.count('T'),
        'G_count': seq_str.count('G'),
        'C_count': seq_str.count('C')
    })

seq_stats_df = pd.DataFrame(seq_stats)
results = ecoli_phages.merge(seq_stats_df, on='Phage_ID')

# 6. Export results
results.to_csv('/workspace/exports/ecoli_phages_complete.csv', index=False)
results.to_parquet('/workspace/exports/ecoli_phages_complete.parquet')

# 7. Cleanup
conn.close()

print("✅ Analysis complete!")
print(f"   Analyzed: {len(results)} phages")
print(f"   Outputs: /workspace/exports/")
```

## 🆚 API vs Direct Access Comparison

| Aspect | REST API | Direct Access |
|--------|----------|---------------|
| **Speed** | Baseline | 5-50x faster |
| **Bulk Operations** | ⚠️ Limited by request size | ✅ No limits |
| **Batch Processing** | ❌ Multiple requests needed | ✅ Single query |
| **Export Large Data** | ❌ Pagination required | ✅ Direct export |
| **Sequence Retrieval** | ⚠️ Network overhead | ✅ Direct file access |
| **Complex Joins** | ❌ Limited | ✅ Full SQL power |
| **Use Case** | External integrations | Bulk analysis |

**When to Use Each:**

**Use API when:**
- External applications need access
- Need cross-network access
- Working with small datasets (< 1000 records)
- Want standardized REST interface

**Use Direct Access when:**
- Analyzing large datasets (> 10,000 records)
- Need complex SQL queries with joins
- Exporting bulk data
- Interactive exploratory analysis
- Building ML datasets

## 📚 Additional Resources

- **Example Notebook**: `notebooks/analysis_direct_access_guide.ipynb`
- **Docker Guide**: [docs/guides/docker-guide.md](docker-guide.md)
- **DuckDB Documentation**: https://duckdb.org/docs/
- **pyfaidx Documentation**: https://github.com/mdshw5/pyfaidx
- **Jupyter Lab Documentation**: https://jupyterlab.readthedocs.io/

## 🙋 Getting Help

If you encounter issues:

1. Check this troubleshooting guide
2. Review the example notebook
3. Check Docker logs: `docker logs pbi-analysis`
4. Open an issue on GitHub with:
   - Error message
   - Steps to reproduce
   - Environment details (Docker version, OS, etc.)

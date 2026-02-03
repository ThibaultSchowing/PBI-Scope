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

**Option A: Using `quick_connect()` (Recommended)**

The easiest way to get started - automatically handles all paths:

```python
from pbi import quick_connect

# Connect to database with all sequence files
# This automatically uses DATA_PATH environment variable in Docker
retriever = quick_connect()

# Get database statistics
stats = retriever.get_stats()
print(f"Phages: {stats['database']['phages']:,}")
print(f"Proteins: {stats['database']['proteins']:,}")
print(f"Hosts: {stats['database']['hosts']:,}")

# Query and retrieve sequences
df = retriever.query_phages("SELECT * FROM fact_phages WHERE Length > 100000 LIMIT 10")
phage_ids = df['Phage_ID'].tolist()
sequences = retriever.get_sequences_by_ids(phage_ids, sequence_type='phage')
```

**Option B: Manual Connection (Advanced)**

For more control over connection parameters:

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

## 🗄️ Accessing the Database

### Understanding the PBI Package

The `pbi` Python package provides a high-level interface to the PBI database and sequence files:

**Main Components:**

1. **`quick_connect()`** - Convenience function for instant database access
2. **`SequenceRetriever`** - Core class for querying metadata and retrieving sequences
3. **`NegativeExampleGenerator`** - ML utility for generating negative training examples

**How it works in Docker:**

The `pbi` package automatically detects the `DATA_PATH` environment variable set in the Docker container (`/data/processed`) and uses it to locate the database and FASTA files. This means you don't need to specify paths manually.

### Retrieving Genomes and Metadata

**1. Get Phage Genomes**

```python
from pbi import quick_connect

retriever = quick_connect()

# Method 1: Query-based retrieval
df = retriever.query_phages("""
    SELECT Phage_ID, Accession, Length, GC_Content, Completeness
    FROM fact_phages 
    WHERE Length > 50000 AND Completeness = 'complete'
    LIMIT 100
""")

# Get sequences for these phages
sequences = retriever.get_sequences_by_ids(
    df['Phage_ID'].tolist(), 
    sequence_type='phage'
)

# Method 2: Direct ID-based retrieval
phage_ids = ['phage_001', 'phage_002', 'phage_003']
sequences = retriever.get_sequences_by_ids(phage_ids, sequence_type='phage')

# sequences is a dict: {phage_id: sequence_string}
for phage_id, seq in sequences.items():
    print(f"{phage_id}: {len(seq)} bp")
```

**2. Get Host Genomes**

```python
from pbi import quick_connect

retriever = quick_connect()

# Query hosts
hosts_df = retriever.query_hosts("""
    SELECT Host_ID, Host_Name, Host_Genus, Host_Family
    FROM dim_hosts
    WHERE Host_Genus = 'Escherichia'
    LIMIT 10
""")

# Get host sequences
host_sequences = retriever.get_sequences_by_ids(
    hosts_df['Host_ID'].tolist(),
    sequence_type='host'
)
```

**3. Get Protein Sequences**

```python
from pbi import quick_connect

retriever = quick_connect()

# Query proteins from a specific phage
proteins_df = retriever.query_proteins("""
    SELECT Protein_ID, Phage_ID, Annotation, Length
    FROM fact_proteins
    WHERE Phage_ID = 'NC_000001'
    AND Annotation LIKE '%terminase%'
""")

# Get protein sequences
protein_sequences = retriever.get_sequences_by_ids(
    proteins_df['Protein_ID'].tolist(),
    sequence_type='protein'
)
```

**4. Get Metadata Without Sequences**

If you only need metadata (no sequences), use direct database queries:

```python
from pbi import quick_connect

retriever = quick_connect()

# Use the underlying database connection
stats = retriever.get_stats()
print(f"Total phages: {stats['database']['phages']:,}")

# Or query directly
import duckdb
conn = duckdb.connect("/data/processed/databases/phage_database_optimized.duckdb", read_only=True)

# Get phage metadata
metadata = conn.execute("""
    SELECT p.*, ph.Host_Name, ph.Host_Genus
    FROM fact_phages p
    LEFT JOIN fact_phage_host ph ON p.Phage_ID = ph.Phage_ID
    WHERE p.GC_Content > 0.5
""").fetchdf()

conn.close()
```

**5. Get Phage-Host Interaction Pairs**

```python
from pbi import quick_connect

retriever = quick_connect()

# Get known phage-host interactions
pairs = retriever.get_phage_host_pairs(limit=1000)

# Returns DataFrame with columns:
# - Phage_ID
# - Host_ID  
# - Phage_Length
# - Phage_GC
# - Host_Name
# - Host_Genus
```

### Common Query Patterns

**Filter by taxonomy:**

```python
# E. coli phages
ecoli_phages = retriever.query_phages("""
    SELECT DISTINCT p.*
    FROM fact_phages p
    INNER JOIN fact_phage_host ph ON p.Phage_ID = ph.Phage_ID
    WHERE ph.Host_Genus LIKE '%Escherichia%'
    OR ph.Host_Name LIKE '%coli%'
""")
```

**Filter by genome characteristics:**

```python
# Large, complete phages with high GC content
large_phages = retriever.query_phages("""
    SELECT * FROM fact_phages
    WHERE Length > 100000
    AND Completeness = 'complete'
    AND GC_Content > 0.55
    ORDER BY Length DESC
""")
```

**Join multiple tables:**

```python
import duckdb

conn = duckdb.connect("/data/processed/databases/phage_database_optimized.duckdb", read_only=True)

# Get phages with their proteins and hosts
complex_query = conn.execute("""
    SELECT 
        p.Phage_ID,
        p.Accession,
        p.Length,
        COUNT(DISTINCT pr.Protein_ID) as Protein_Count,
        ph.Host_Name,
        ph.Host_Genus
    FROM fact_phages p
    LEFT JOIN fact_proteins pr ON p.Phage_ID = pr.Phage_ID
    LEFT JOIN fact_phage_host ph ON p.Phage_ID = ph.Phage_ID
    GROUP BY p.Phage_ID, p.Accession, p.Length, ph.Host_Name, ph.Host_Genus
    HAVING COUNT(DISTINCT pr.Protein_ID) > 10
""").fetchdf()

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

Prepare datasets for ML models using the convenience `quick_connect()` function:

```python
from pbi import quick_connect, NegativeExampleGenerator

# Connect using quick_connect (automatically uses correct paths)
retriever = quick_connect()

# Get positive examples (known phage-host pairs)
positive_pairs = retriever.get_phage_host_pairs(limit=5000)

# Filter for quality
positive_pairs = positive_pairs[
    (positive_pairs['Phage_Length'] > 10000) &
    (positive_pairs['Phage_GC'].notna())
]

# Generate negative examples
neg_gen = NegativeExampleGenerator(retriever)
dataset = neg_gen.generate_balanced_dataset(
    positive_pairs=positive_pairs,
    strategy='mixed',  # Combines random, GC-based, and taxonomy-based negatives
    positive_ratio=0.5
)

# Export for training
dataset.to_parquet('/workspace/exports/phage_host_ml_dataset.parquet')
print(f"Dataset created: {len(dataset)} samples")
print(f"Positive: {(dataset['Label'] == 1).sum()}")
print(f"Negative: {(dataset['Label'] == 0).sum()}")
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

## 🔧 Package Management & Custom Environments

### Installing Additional Packages

The analysis container comes with a comprehensive scientific computing stack. To install additional packages:

**1. Install packages temporarily (current session only)**

From a Jupyter notebook or terminal:

```python
# Install Python package
!pip install scikit-learn xgboost lightgbm

# Install from conda-forge (if conda is available)
!conda install -c conda-forge package_name
```

**2. Install packages persistently**

To make packages available across container restarts, modify `Dockerfile.analysis`:

```dockerfile
# Add your packages to the RUN pip install command
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org \
    jupyterlab==4.0.9 \
    duckdb>=0.9.0 \
    # ... existing packages ...
    scikit-learn>=1.3.0 \
    xgboost>=2.0.0 \
    lightgbm>=4.0.0 \
    plotly>=5.0.0
```

Then rebuild the container:

```bash
docker compose build analysis
docker compose up -d analysis
```

### Creating Custom Analysis Environments

You can create specialized analysis environments for different projects:

**Option 1: Use Conda environments inside the container**

```python
# Create a new conda environment
!conda create -n my_analysis python=3.10 -y

# Activate and install packages
!conda activate my_analysis && conda install pandas numpy scikit-learn -y

# Use in Jupyter by installing ipykernel
!conda activate my_analysis && pip install ipykernel
!conda activate my_analysis && python -m ipykernel install --user --name my_analysis
```

Then select the "my_analysis" kernel from Jupyter's kernel menu.

**Option 2: Create a separate Docker service**

Add a new service to `docker-compose.yml` for specialized analysis:

```yaml
analysis-ml:
  build:
    context: .
    dockerfile: Dockerfile.analysis-ml  # Your custom Dockerfile
  container_name: pbi-analysis-ml
  ports:
    - "8889:8888"  # Different port
  volumes:
    - pbi-data:/data:ro
    - ./notebooks:/workspace
    - ./workflow:/app/workflow:ro
    - ./src:/app/src:ro
  environment:
    - DATA_PATH=/data/processed
    - PYTHONPATH=/app
  networks:
    - pbi-network
  restart: unless-stopped
```

Create `Dockerfile.analysis-ml` with your custom package set:

```dockerfile
FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project
COPY . /app/
ENV PYTHONPATH=/app:$PYTHONPATH

# Install PBI package
RUN pip install -e /app/

# Install ML-specific packages
RUN pip install \
    jupyterlab \
    duckdb pyfaidx pandas numpy \
    scikit-learn xgboost lightgbm \
    torch torchvision \
    transformers \
    optuna \
    mlflow

# Configure Jupyter
RUN jupyter lab --generate-config && \
    echo "c.ServerApp.token = ''" >> ~/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.password = ''" >> ~/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.allow_root = True" >> ~/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.ip = '0.0.0.0'" >> ~/.jupyter/jupyter_lab_config.py && \
    echo "c.ServerApp.port = 8888" >> ~/.jupyter/jupyter_lab_config.py

EXPOSE 8888
ENV DATA_PATH=/data/processed

CMD ["jupyter", "lab", "--allow-root", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--notebook-dir=/workspace"]
```

Start your custom environment:

```bash
docker compose build analysis-ml
docker compose up -d analysis-ml
# Access at http://localhost:8889
```

**Option 3: Use Python virtual environments**

From a Jupyter terminal:

```bash
# Create virtual environment
python -m venv /workspace/.venvs/my_project
source /workspace/.venvs/my_project/bin/activate
pip install specific-packages

# Install kernel for Jupyter
pip install ipykernel
python -m ipykernel install --user --name=my_project --display-name="My Project"
```

### Writing Custom Functions

**Where to write reusable functions:**

**1. In the PBI package** (for general-purpose functionality)

Add functions to `/app/src/pbi/` and they'll be available via `from pbi import ...`

Example - add to `src/pbi/utils.py`:

```python
def calculate_phage_metrics(retriever, phage_ids):
    """Calculate comprehensive metrics for phage genomes."""
    # Your implementation
    pass
```

Use in notebooks:

```python
from pbi.utils import calculate_phage_metrics
metrics = calculate_phage_metrics(retriever, phage_ids)
```

**2. In a shared notebook utilities module**

Create `notebooks/utils.py`:

```python
# Custom analysis functions
def plot_gc_distribution(df, output_path):
    import matplotlib.pyplot as plt
    plt.hist(df['GC_Content'])
    plt.savefig(output_path)
```

Use in any notebook:

```python
import sys
sys.path.insert(0, '/workspace')
from utils import plot_gc_distribution

plot_gc_distribution(df, '/workspace/exports/gc_plot.png')
```

**3. In individual notebooks** (for one-off analyses)

Define functions directly in notebook cells for exploratory work.

### Best Practices for Custom Environments

1. **Document your dependencies**: Keep a `requirements.txt` or `environment.yml` file
2. **Version control**: Track your custom Dockerfiles and conda environments
3. **Test in isolation**: Use separate containers to avoid dependency conflicts
4. **Share configurations**: Use Docker Compose profiles for different team members
5. **Resource limits**: Set memory/CPU limits for resource-intensive ML environments

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
   
   **If index files are missing**: Re-run the pipeline as it should create them automatically:
   ```bash
   docker compose run --rm pipeline
   ```
   
   **Alternative**: Manually create indexes (requires pyfaidx installed):
   ```bash
   docker compose exec analysis python -c "from pyfaidx import Fasta; Fasta('/data/processed/sequences/all_phages.fasta')"
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

For CPU-intensive tasks, use multiprocessing with caution:

```python
from multiprocessing import Pool

def process_batch(batch_ids):
    """
    Create a new retriever instance in each worker process.
    
    Note: SequenceRetriever contains database connections and file handles
    that cannot be pickled across processes. Always create a new instance
    in the worker function.
    """
    from pbi import SequenceRetriever
    
    # Create new retriever in worker process
    retriever = SequenceRetriever(
        db_path="/data/processed/databases/phage_database_optimized.duckdb",
        phage_fasta_path="/data/processed/sequences/all_phages.fasta",
        protein_fasta_path="/data/processed/sequences/all_proteins.fasta"
    )
    
    sequences = retriever.get_sequences_by_ids(batch_ids, sequence_type='phage')
    # Process sequences...
    return results

# Split IDs into batches
batches = [phage_ids[i:i+1000] for i in range(0, len(phage_ids), 1000)]

# Process in parallel
with Pool(processes=4) as pool:
    results = pool.map(process_batch, batches)
```

**⚠️ Important Notes:**
- Always create new SequenceRetriever instances in worker processes
- Database connections and file handles are not pickle-able
- Monitor memory usage closely - each process will load its own FASTA indexes
- For large-scale parallel processing, consider using Dask or Ray instead

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

## 💻 Connecting with VSCode

While Jupyter Lab in the browser is convenient, you can also connect to the remote Jupyter server using **VSCode** for a more integrated development experience.

### Prerequisites

1. **VSCode** installed on your local machine
2. **Jupyter extension** for VSCode installed (from Microsoft)
3. PBI analysis service running: `docker compose up -d analysis`

### Connection Steps

#### Method 1: Direct Kernel Connection (Recommended)

1. **Get the Jupyter Server URL with Token**

   ```bash
   # Get the Jupyter server URL with authentication token
   docker logs pbi-analysis 2>&1 | grep "http://127.0.0.1:8888/lab?token="
   ```

   This will output something like:
   ```
   http://127.0.0.1:8888/lab?token=abc123def456...
   ```

2. **Open VSCode and Create/Open a Notebook**

   - Create a new `.ipynb` file or open an existing one
   - Click on "Select Kernel" in the top-right corner
   - Choose "Existing Jupyter Server"

3. **Enter the Jupyter Server URL**

   - Paste the complete URL with token from step 1
   - VSCode will connect to the remote Jupyter server
   - You can now run cells directly in VSCode!

4. **Test the Connection**

   Create a new notebook and run:

   ```python
   from pbi import quick_connect
   
   # This should work if connected to the Docker container
   retriever = quick_connect()
   stats = retriever.get_stats()
   print(f"Connected! Database has {stats['database']['phages']:,} phages")
   ```

#### Method 2: Port Forwarding (Alternative)

If you're running the Docker container on a remote server, you may need port forwarding:

1. **SSH Port Forward** (if on remote server)

   ```bash
   ssh -L 8888:localhost:8888 user@remote-server
   ```

2. **Follow Method 1** steps above with `http://localhost:8888/lab?token=...`

### Advantages of VSCode

- **Integrated Development**: Edit code, notebooks, and documentation in one place
- **Git Integration**: Easy version control for your analysis notebooks
- **IntelliSense**: Better code completion and suggestions
- **Debugging**: Advanced debugging capabilities
- **Extensions**: Use other VSCode extensions alongside Jupyter
- **Multi-file Editing**: Work with multiple notebooks and Python files simultaneously

### Tips for VSCode + Jupyter

1. **Save Your Server URL**: VSCode remembers the server URL, so you only need to enter it once
2. **Restart Kernel**: Use the "Restart Kernel" button in the top menu if needed
3. **Variable Inspector**: Enable the variable inspector in VSCode for easier debugging
4. **Keyboard Shortcuts**: VSCode uses standard Jupyter keyboard shortcuts (Shift+Enter, etc.)

### Troubleshooting VSCode Connection

**Issue**: "Failed to connect to Jupyter server"
- **Solution**: Verify the analysis service is running: `docker ps | grep pbi-analysis`
- **Solution**: Check the token is correct: `docker logs pbi-analysis | grep token`

**Issue**: "Cannot import pbi module"
- **Solution**: Make sure you're connected to the Docker container's kernel, not your local Python
- **Solution**: Verify kernel name shows "Python 3 (ipykernel)" from the remote server

**Issue**: "Connection timeout"
- **Solution**: If on remote server, ensure SSH port forwarding is active
- **Solution**: Check firewall settings allow port 8888

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

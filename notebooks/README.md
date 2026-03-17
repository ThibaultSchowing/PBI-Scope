# PBI Jupyter Notebooks

This directory contains Jupyter notebooks for exploring and analyzing the PBI phage genomics database.

## Main Notebooks

These notebooks serve as the primary guides for working with PBI data:

### 📊 `01_database_exploration.ipynb` — Database Exploration and Quality Control
Comprehensive guide to understanding the database contents and data quality:
- Database statistics and overview
- Phage source database distribution
- Phage quality metrics (completeness, lifestyle, genome length, GC content)
- Host genome coverage analysis
- Phage-host pair statistics
- Understanding missing sequences (phages without hosts, hosts without genomes)

### 🔬 `02_sequence_retrieval.ipynb` — Sequence Retrieval with the PBI Package
Complete guide to retrieving data using the PBI Python package:
- Connecting to the database with `pbi.quick_connect()`
- Querying phage and host metadata with filtering
- LIMIT / OFFSET pagination
- Retrieving DNA sequences (phage, host, protein)
- Phage-host pairs with sequences as DataFrames
- Batch iteration for large datasets

### 🤖 `03_ml_streaming.ipynb` — AI/ML with Phage-Host Data
End-to-end machine learning workflow from raw data to model training:
- **Part 1 (DataFrame approach):** EDA, feature engineering, negative example generation, Random Forest baseline
- **Part 2 (Streaming approach):** Memory-efficient `PhageHostStreamingDataset`, `PhageHostIndexedDataset`, batch iterators, custom transforms, train/test splitting

### 📦 `04_data_release_exploration.ipynb` — Data Release Smoke Test & Exploration
Standalone notebook distributed alongside the Zenodo data release (no PBI package required — only `duckdb` and `pandas`):
- Connect to the DuckDB database in read-only mode and verify all tables
- Explore phage metadata: source distribution, genome length, GC content, lifestyle, host organisms
- Inspect annotation coverage per phage (proteins, terminators, AMR genes, CRISPR, etc.)
- Browse all CSV files in `phages/` and `hosts/` with row counts and column previews
- Host download status from JSON files
- Clickable links to HTML data-merging and validation reports in `reports/`
- Example cross-table SQL queries

## Subdirectories

### `exploration/`
Development notebooks used while building the database. Useful as historical reference:
- `expl_1.ipynb` — Initial database exploration
- `expl_2_PhageScope.ipynb` — PhageScope data integration
- `expl_3_VRHdb.ipynb` — VRHdb database integration
- `expl_4_INPHARED.ipynb` — INPHARED database integration
- `expl_5_TestDB.ipynb` — Database testing and validation
- `expl_6_Fasta.ipynb` — FASTA file handling and indexing
- `expl_7_hostgenomes.ipynb` — Host genome retrieval and processing

### `bin/`
Previous versions of the main notebooks, kept for reference:
- `quality_control.ipynb` — Predecessor to `01_database_exploration.ipynb`
- `use_1_pbi.ipynb` — Predecessor to `02_sequence_retrieval.ipynb`
- `ml_1_phage_host_dataset.ipynb` — Predecessor to `03_ml_streaming.ipynb` (ML part)
- `example_streaming_ml.ipynb` — Predecessor to `03_ml_streaming.ipynb` (streaming part)
- `analysis_direct_access_guide.ipynb` — Direct DuckDB access guide

## Getting Started

### Using the Analysis Docker Service (Recommended)

```bash
# Start the analysis container
docker compose up -d analysis

# Access Jupyter Lab at http://localhost:8888
```

> ⚠️ **Security Note**: The analysis service runs Jupyter Lab without authentication for local development convenience. Do not expose port 8888 to untrusted networks. For remote access, use SSH tunneling.

### Local Development

```bash
# Install the PBI package
pip install -e .

# Start Jupyter Lab from the project root
jupyter lab

# Navigate to the notebooks/ directory
```

## Key Concepts

### Missing Sequences
When iterating over phage-host pairs, warnings like the following are expected:
```
⚠️  Host sequence not found for ID: GCF_979243125_1
```
This happens because not every phage has a host genome downloaded. The code automatically **skips** such pairs while keeping the warning. This is the correct behavior — a stream of phage-host pairs must have both sequences available.

### Connection Pattern
All notebooks use the same connection pattern:
```python
import pbi
retriever = pbi.quick_connect()  # auto-detects database and FASTA paths
# ... work with retriever ...
retriever.close()
```

## Troubleshooting

### Kernel Crashes / Out of Memory
- Use `LIMIT` to work with smaller datasets first
- Use the streaming/batch iterator approach for large datasets
- Use DuckDB aggregations instead of loading everything into pandas

### Database Lock Error
Always use read-only connections (the PBI package does this by default):
```python
conn = duckdb.connect(db_path, read_only=True)
```

### Path Not Found
- **In Docker:** Paths like `/data/processed/...` are set automatically via `DATA_PATH`
- **Locally:** Set the `DATA_PATH` environment variable or use project-relative paths

## Additional Resources

- [PBI Package Guide](../docs/guides/pbi-package.md)
- [Analysis Guide](../docs/guides/analysis-guide.md)
- [Machine Learning Guide](../docs/guides/machine-learning.md)
- [Docker Guide](../docs/guides/docker-guide.md)
- [PBI Documentation](https://thibaultschowing.github.io/PBI/)

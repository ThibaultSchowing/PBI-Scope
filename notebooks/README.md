# PBI Jupyter Notebooks

This directory contains Jupyter notebooks for exploring and analyzing the PBI phage genomics database.

## Analysis Notebooks

### 🚀 **analysis_direct_access_guide.ipynb** (NEW - Recommended)
**Comprehensive guide for efficient bulk data analysis using the Analysis service**

This is the primary notebook for working with large-scale phage genomics data. It demonstrates:

- **Direct Database Access**: Query DuckDB directly without API overhead (5-50x faster)
- **Batch Processing**: Efficiently process millions of records
- **Memory Management**: Handle large datasets without out-of-memory errors
- **Data Export**: Export to Parquet, CSV, and other formats
- **Real-World Examples**: Complete E. coli phages analysis workflow
- **Best Practices**: Read-only connections, proper resource cleanup, performance tips

**When to use this notebook:**
- Analyzing large datasets (>10,000 records)
- Exporting bulk data for external analysis
- Building machine learning datasets
- Complex SQL queries with multi-table joins
- Performance-critical operations

**Requirements:** Analysis Docker container must be running (`docker compose up -d analysis`)

## Exploration Notebooks

These notebooks were used during database development and exploration:

- **expl_1.ipynb**: Initial database exploration
- **expl_2_PhageScope.ipynb**: PhageScope data integration
- **expl_3_VRHdb.ipynb**: VRHdb database integration
- **expl_4_INPHARED.ipynb**: INPHARED database integration
- **expl_5_TestDB.ipynb**: Database testing and validation
- **expl_6_Fasta.ipynb**: FASTA file handling and indexing
- **expl_7_hostgenomes.ipynb**: Host genome retrieval and processing

## Machine Learning Notebooks

### ml_1_phage_host_dataset.ipynb
**Creating balanced datasets for phage-host interaction prediction**

Demonstrates:
- Generating positive phage-host pairs
- Creating negative examples using multiple strategies
- Building balanced datasets for ML training
- Dataset validation and statistics
- Exporting datasets to `/workspace/ml_datasets/` (writable in container)

**Important:** Files are saved to `/workspace/ml_datasets/` which is local to the analysis container. To access exported files from your host machine:
```bash
# Copy files from container to host
docker cp pbi-analysis:/workspace/ml_datasets/phage_host_features.csv ./

# Or mount /workspace as a volume in docker-compose.yml
```

### example_streaming_ml.ipynb
**PyTorch-compatible streaming datasets for memory-efficient ML workflows**

Demonstrates:
- **Streaming datasets** for large-scale data (memory-efficient iteration)
- **Indexed datasets** with shuffling and random access
- **Simple batch iterators** for non-PyTorch workflows
- **Custom transforms** for data preprocessing
- **Performance comparison** of different approaches
- **Train/test splitting** using SQL WHERE clauses

**Features:**
- Compatible with PyTorch DataLoader
- Works without PyTorch for pandas-based workflows
- Handles missing sequences gracefully
- Provides helpful warnings for empty datasets

**Note:** Uses case-insensitive filters (`LOWER()`) to handle database variations.

## Usage Examples

### use_1_pbi.ipynb
**Basic usage of the PBI Python package**

Introduction to:
- Connecting to the database
- Querying metadata
- Retrieving sequences
- Working with the `SequenceRetriever` class

## Getting Started

### Using the Analysis Service (Recommended)

**⚠️ Security Note**: The analysis service runs Jupyter Lab without authentication for local development convenience. **Do not expose port 8888 to untrusted networks.** For remote access, use SSH tunneling:

```bash
# On remote server
docker compose up -d analysis

# On local machine
ssh -L 8888:localhost:8888 user@remote-server
# Then access http://localhost:8888 locally
```

1. **Start the Analysis container:**
   ```bash
   docker compose up -d analysis
   ```

2. **Access Jupyter Lab:**
   - Open http://localhost:8888 in your browser
   - Navigate to `analysis_direct_access_guide.ipynb`

3. **Start analyzing:**
   - Follow the examples in the notebook
   - Modify queries for your specific use case
   - Export results for further analysis

### Local Development

If running locally (not in Docker):

```bash
# Ensure the PBI package is installed
pip install -e .

# Start Jupyter Lab
jupyter lab

# Navigate to notebooks directory
```

**Note:** Local notebooks need to use local paths (e.g., `./data/processed/...`) instead of Docker paths (`/data/processed/...`).

## Best Practices

1. **Always use read-only database connections:**
   ```python
   conn = duckdb.connect(db_path, read_only=True)
   ```

2. **Process data in batches** to avoid memory issues:
   ```python
   BATCH_SIZE = 1000
   for offset in range(0, total, BATCH_SIZE):
       batch = conn.execute(f"... LIMIT {BATCH_SIZE} OFFSET {offset}").fetchdf()
   ```

3. **Close connections** when done:
   ```python
   try:
       conn = duckdb.connect(db_path, read_only=True)
       # Your work here
   finally:
       conn.close()
   ```

4. **Export large datasets** using DuckDB's native functions:
   ```python
   conn.execute("COPY (...) TO 'output.parquet' (FORMAT PARQUET)")
   ```

## Troubleshooting

### Kernel Crashes / Out of Memory

**Problem:** Jupyter kernel crashes when loading large datasets

**Solutions:**
- Reduce batch size in queries
- Use `LIMIT` to test with smaller datasets first
- Export to disk instead of loading into memory
- Use DuckDB aggregations instead of pandas operations

### Database Locked Error

**Problem:** `IO Error: Could not set lock on file`

**Solution:** Always use `read_only=True` when connecting:
```python
conn = duckdb.connect(db_path, read_only=True)
```

### Path Not Found

**Problem:** `FileNotFoundError: /data/processed/...`

**Solutions:**
- **In Docker:** Use absolute Docker paths: `/data/processed/...`
- **Locally:** Use relative paths: `./data/processed/...` or set `DATA_PATH` environment variable

### Jupyter Lab Not Accessible

**Problem:** Cannot connect to http://localhost:8888

**Solutions:**
```bash
# Check if container is running
docker ps | grep pbi-analysis

# Check logs for errors
docker logs pbi-analysis

# Restart the service
docker compose restart analysis
```

## Additional Resources

- **Analysis Guide**: [docs/guides/analysis-guide.md](../docs/guides/analysis-guide.md)
- **Docker Guide**: [docs/guides/docker-guide.md](../docs/guides/docker-guide.md)
- **Machine Learning Guide**: [docs/guides/machine-learning.md](../docs/guides/machine-learning.md)
- **PBI Documentation**: https://thibaultschowing.github.io/PBI/

## Contributing

When creating new notebooks:

1. Add a descriptive filename (e.g., `analysis_your_topic.ipynb`)
2. Include a clear title and introduction in the first cell
3. Document your methodology and findings
4. Add the notebook to this README with a brief description
5. Ensure the notebook works in both Docker and local environments (or note requirements)

## Questions or Issues?

- Check the [Analysis Guide](../docs/guides/analysis-guide.md) for detailed troubleshooting
- Review example notebooks for reference implementations
- Open an issue on GitHub with your question

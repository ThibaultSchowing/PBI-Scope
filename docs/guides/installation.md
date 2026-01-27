# Installation Guide

Get started with PBI for local development and analysis.

## Prerequisites

- **Operating System**: Linux/macOS (Windows via WSL2)
- **Python**: 3.8 or higher
- **Conda**: For managing environments
- **Internet**: For data downloads
- **Disk Space**: >50 GB recommended (>100 GB for full dataset)
- **RAM**: >32 GB recommended for smooth execution without swapping
- **Time**: Building the full database takes 2-4 hours on first run

## ⚙️ Environment Variables and Data Paths

**Before you start**, understand where PBI will store data:

### Default Behavior

By default, PBI stores all data in the `./data/` directory relative to your project root:

```bash
PBI/
├── data/                          # ~150+ GB total
│   ├── raw/                       # ~50 GB (downloaded archives)
│   ├── intermediate/              # ~50 GB (processing files)
│   └── processed/                 # ~50 GB (final database & sequences)
│       ├── databases/
│       ├── sequences/
│       └── reports/
```

**⚠️ Important**: Make sure you have at least **150 GB of free disk space** in your project directory, or configure a custom location (see below).

### Custom Data Directory (Recommended)

To store data in a different location (e.g., on a larger disk), set the `PBI_DATA_DIR` environment variable **before** running the pipeline:

```bash
# Set custom data directory (replace with your desired path)
export PBI_DATA_DIR="/mnt/large-disk/pbi-data"

# Make it persistent (add to ~/.bashrc or ~/.zshrc)
echo 'export PBI_DATA_DIR="/mnt/large-disk/pbi-data"' >> ~/.bashrc
```

The pipeline will then use:
- `/mnt/large-disk/pbi-data/raw/`
- `/mnt/large-disk/pbi-data/intermediate/`
- `/mnt/large-disk/pbi-data/processed/`

### Environment Variables Reference

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `PBI_DATA_DIR` | Base directory for all pipeline data | `./data` | No |
| `DATA_PATH` | Path for API to find processed data | `data/processed` | Only for API |
| `NCBI_EMAIL` | Your email for NCBI API | - | For genome downloads |
| `NCBI_API_KEY` | NCBI API key (increases rate limit) | - | Optional but recommended |

**For API usage**, set `DATA_PATH` to point to the processed data:

```bash
# If using default location
export DATA_PATH="data/processed"

# If using custom PBI_DATA_DIR
export DATA_PATH="/mnt/large-disk/pbi-data/processed"
```

## Step-by-Step Installation

### 1. Clone the Repository

```bash
git clone https://github.com/ThibaultSchowing/PBI.git
cd PBI

# Verify repository structure
ls -la
# Should see: workflow/, src/, data/, notebooks/, docs/, README.md, etc.
```

### 2. Install Anaconda/Miniconda

If you don't have Conda installed:

```bash
# Download Miniconda (lightweight)
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# Install
bash Miniconda3-latest-Linux-x86_64.sh

# Verify installation
conda --version
```

Make sure the `conda` command is in your PATH.

### 3. Install PBI Package

Create a virtual environment and install the PBI package:

```bash
# Create and activate environment
conda create -n pbi python=3.10
conda activate pbi

# Install PBI package in development mode
pip install -e .

# Verify installation
python -c "import pbi; print(f'✅ PBI v{pbi.__version__} installed successfully')"
```

### 4. Build the Database

**⚠️ Important**: The first run downloads ~50 GB of data and may take 2-4 hours depending on your connection.

#### Basic Execution

```bash
# Run the Snakemake pipeline
# Use 2-4 cores for first run (I/O bottleneck)
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda --printshellcmds
```

#### With Caching (Optional but Recommended)

If you plan to modify or update the data frequently, use caching:

```bash
# Create cache directory
mkdir -p /mnt/snakemake-cache

# Export cache location (add to ~/.bashrc for persistence)
export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/

# Run pipeline with caching
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --cores 4 --use-conda --printshellcmds
```

#### Command Options Explained

- `--directory workflow`: Set working directory to workflow/
- `--snakefile workflow/Snakefile`: Specify the Snakefile
- `--cores 4`: Use 4 CPU cores (adjust based on your system)
- `--use-conda`: Automatically create required conda environments
- `--printshellcmds`: Show commands being executed (useful for debugging)
- `--cache`: Use caching for intermediate files (optional)

#### Running Specific Steps

```bash
# Create database only (without reports)
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda \
  ../data/databases/phage_database.duckdb

# Generate validation report
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda \
  reports/database_validation.html

# Create optimized database
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda \
  ../data/databases/phage_database_optimized.duckdb

# Keep temporary files for debugging
snakemake --directory workflow --snakefile workflow/Snakefile \
  --notemp --cores 4 --use-conda
```

### 5. Verify Installation

After the pipeline completes, verify the outputs:

```bash
# Check database exists
ls -lh data/databases/

# Check sequence files
ls -lh data/sequences/

# Check reports
ls -lh workflow/reports/
```

### 6. Start Using PBI

#### In Python/Jupyter

```bash
# Start Jupyter Lab
jupyter lab

# Or specify a custom port
jupyter lab --port 8889
```

Create a new notebook and test your installation:

```python
import pbi
import duckdb

# Connect to database
conn = duckdb.connect('data/databases/phage_database_optimized.duckdb')

# Check database statistics
stats = conn.execute("""
    SELECT 
        'Phages' as Type, COUNT(*) as Count FROM fact_phages
    UNION ALL
    SELECT 'Proteins', COUNT(*) FROM dim_proteins
    UNION ALL
    SELECT 'tRNA/tmRNA', COUNT(*) FROM dim_trna_tmrna
""").df()

print("📊 Database Statistics:")
print(stats)

# Query some data
df = conn.execute("""
    SELECT Phage_ID, Length, GC_content, Host, Lifestyle
    FROM fact_phages 
    WHERE Length > 100000 
    LIMIT 10
""").df()

print("\n✅ Sample of large phages:")
print(df)

conn.close()
```

#### Command Line Usage

```python
# Connect to database in Python
python
>>> import duckdb
>>> conn = duckdb.connect('data/databases/phage_database_optimized.duckdb')
>>> conn.execute("SELECT COUNT(*) FROM fact_phages").fetchall()
>>> conn.close()
```

## Quick Reference

### Update Database

To refresh with new data:

```bash
cd workflow
snakemake --cores 4 --use-conda
```

### Check What Would Run

Dry-run to see what would be updated:

```bash
cd workflow
snakemake -n
```

### Generate Workflow Diagram

Visualize the pipeline:

```bash
cd workflow
snakemake --dag | dot -Tsvg > dag/workflow.svg
```

### Clean Temporary Files

Remove temporary files after execution:

```bash
snakemake --delete-temp-output
```

## Troubleshooting

### "No space left on device"

```bash
# Check disk space
df -h

# Clean Snakemake cache if needed
rm -rf workflow/.snakemake/
```

### "ModuleNotFoundError: No module named 'pbi'"

```bash
# Reinstall PBI package from project root
cd /path/to/PBI
conda activate pbi
pip install -e .
```

### Conda Environment Issues

```bash
# Remove and recreate all Snakemake environments
rm -rf workflow/.snakemake/conda/

# Next run will rebuild environments
snakemake --cores 4 --use-conda
```

### Out of Memory Errors

- Reduce number of cores: `--cores 2`
- Close other applications
- Consider using Docker with memory limits
- Ensure swap space is enabled

### Slow Execution

- First run is always slow (downloading data)
- Use more cores for subsequent runs: `--cores all`
- Consider using SSD for data storage
- Enable caching to avoid re-downloading

## What Gets Installed

**Data Storage Requirements:**

- **Conda packages**: `workflow/.snakemake/conda/` (~2 GB)
- **Raw data**: `data/raw/` (~40-50 GB compressed, temporary)
- **Processed data**: `data/processed/` (~50 GB)
- **Database**: `data/databases/` (~15 GB)
- **Sequences**: `data/sequences/` (~100 GB)
- **Total**: ~150-200 GB

## Next Steps

- Explore example notebooks in `notebooks/`
- Read the [Database Overview](../database/overview.md)
- Check out the [Command Reference](../reference/commands.md)
- View generated reports in `workflow/reports/`

## Advanced Configuration

### Custom Snakemake Config

Edit `workflow/config/config.yaml` to customize:

- Data source URLs
- Output paths
- Processing parameters
- Resource limits

### Running in Background

```bash
# Run pipeline in background with logs
nohup snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda --printshellcmds > pipeline.log 2>&1 &

# Check progress
tail -f pipeline.log
```

### Using Screen/Tmux

For long-running pipelines:

```bash
# Start screen session
screen -S pbi-pipeline

# Run pipeline
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda

# Detach: Ctrl+A, then D
# Reattach: screen -r pbi-pipeline
```

---

For Docker-based installation, see the [Docker Guide](docker-guide.md).

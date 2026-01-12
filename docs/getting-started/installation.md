
## 🚀 Installation Guide (To Be Tested)

Get started with PBI in under 10 minutes!

### Prerequisites

- **Linux**/macOS (Windows via WSL2)
- **Python 3.8+**
- **Pixi package manager** ([installation guide](https://pixi.sh/latest/))
- **Conda** (used via Snakemake's `--use-conda` option)
- **Internet connection** (for data downloads)
- **Disk space**: >50GB recommended
- **RAM**: >32GB recommended for a smooth non-swapping execution
- **Patience**: building the full database and reports from scratch takes 2-4 hours

### Step-by-Step Installation

#### 1. Install Pixi

Pixi is a fast, modern package manager that handles all dependencies automatically.

```bash
# Install Pixi (one-time setup)
curl -fsSL https://pixi.sh/install.sh | bash

# Restart your shell or run:
export PATH="$HOME/.pixi/bin:$PATH"

# Verify installation
pixi --version
```

#### 2. Clone the Repository

```bash
# Clone PBI repository

git clone <repository-url>
cd PBI

# Check repository structure
ls -la
# Should see: workflow/, src/, data/, notebooks/, README.md, etc.
```


#### 2.5 Install Anaconda

Install Anaconda. Make sure that the conda command is in your path

#### 3. Install PBI Package

**TODO**
> Check if `pixi install` is necessary before installing the package

You can install the package in a virtual environment with conda or venv by running the following command from within PBI/

```bash

# Install PBI 
(myenv) pip install -e .
```

Or use pixi :

```bash
# Install PBI as an editable Python package
pixi run pip install -e . --no-deps

# Verify installation
pixi run python -c "import pbi; print(f'✅ PBI v{pbi.__version__} installed successfully')"
```

#### 4. Build the Database (First-Time Setup)

**⚠️ CRITICAL: First-Time Execution Information**

The initial pipeline execution is **required to create the database** and will take significant time:
- **Duration**: 2-4 hours (depending on internet speed and CPU)
- **Download**: ~50 GB of data from PhageScope
- **Process**: Downloads, merges, validates data, and creates the queryable database
- **Result**: Until this completes, **the database will not be queryable**

**📋 First-Time Setup Procedure:**

```bash
# Step 1: [RECOMMENDED] Set up caching for intermediate files
# This allows resuming if the pipeline is interrupted
mkdir -p /mnt/snakemake-cache
export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/

# Step 2: [OPTIONAL] Make the cache environment variable persistent
# Add to your shell configuration file (~/.bashrc, ~/.zshrc, or ~/.bash_profile)
echo 'export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/' >> ~/.bashrc
source ~/.bashrc

# Step 3: Export the Pixi conda environment (required for Snakemake)
pixi shell-hook > /dev/null

# Step 4: Run the Snakemake pipeline
# ⚠️ Use ONLY 2-4 cores on first run to avoid I/O bottleneck crashes
pixi run snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --notemp --cores 4

# The pipeline will:
# 1. Download metadata from PhageScope (~2 GB)
# 2. Download FASTA files (~50 GB total)
# 3. Merge and process all data
# 4. Create DuckDB database (~15 GB)
# 5. Generate validation reports
# 6. Create optimized database (~12 GB)
# 7. Index sequence files

# Progress can be monitored in real-time as commands are printed (--printshellcmds)
```

**For subsequent runs** (after database is created):

```bash
# You can use more cores for updates/re-runs
pixi run snakemake --directory workflow --snakefile workflow/Snakefile --use-conda --cores all
```
<details>
<summary>Advanced: Running specific pipeline targets</summary>

### Running the Pipeline piece by piece

For development or troubleshooting, you can run specific parts of the pipeline:

```bash
# Create database only (without optimization)
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  ../data/databases/phage_database.duckdb

# Generate validation report only
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  reports/database_validation.html

# Create optimized database only
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  ../data/databases/phage_database_optimized.duckdb
```

</details>

**🔧 Command Options Explained:**

- `--directory workflow`: Working directory for the pipeline
- `--snakefile workflow/Snakefile`: Path to the Snakefile
- `--cache`: Use caching for intermediate files (requires SNAKEMAKE_OUTPUT_CACHE)
- `--use-conda`: Automatically create and use conda environments for each rule
- `--printshellcmds`: Display all shell commands as they execute (useful for monitoring)
- `--notemp`: Keep temporary files (useful for debugging; omit for production)
- `--cores 4`: Use 4 CPU cores (2-4 recommended for first run; increase later)

#### 5. Start Jupyter Lab

Run your notebook as you do usualy

```bash
# From project root directory
cd ..
pixi run jupyter lab

# Or specify a custom port:
# pixi run jupyter lab --port 8889
```

#### 6. Test Your Installation

Create a new notebook and run:

```python
import pbi

# Connect to database (instant with background FASTA loading)
retriever = pbi.quick_connect()

# Check database statistics
stats = retriever.get_stats()
print(f"📊 Database contains:")
print(f"   Phages: {stats['database']['phages']:,}")
print(f"   Proteins: {stats['database']['proteins']:,}")

# Query some phages
df = retriever.get_phage_sequences(
    "SELECT Phage_ID FROM fact_phages WHERE Length > 100000 LIMIT 10"
)
print(f"\n✅ Retrieved {len(df)} large phages")
```

### 🎯 Quick Command Reference

```bash
# Update database (re-run workflow for new data)
cd workflow && pixi run snakemake --cores 4

# Start Jupyter Lab
pixi run jupyter lab

# Run Python interactively
pixi run python

# Check what would be updated (dry-run)
cd workflow && pixi run snakemake -n

# Generate workflow diagram
cd workflow && pixi run snakemake --dag | dot -Tsvg > dag/workflow.svg
```

### 🐛 Troubleshooting

**Issue:** `pixi: command not found`
```bash
# Add Pixi to PATH permanently
echo 'export PATH="$HOME/.pixi/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**Issue:** Snakemake fails with "No space left on device"
```bash
# Check disk space (ensure >50GB free)
df -h

# Clean Snakemake cache if needed
rm -rf .snakemake/
```

**Issue:** Pipeline interrupted or crashes during first run
```bash
# If you set up caching, simply re-run the same command
# It will resume from where it stopped
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --notemp --cores 4
```

**Issue:** Import error: `ModuleNotFoundError: No module named 'pbi'`
```bash
# Reinstall PBI package from project root
cd /path/to/PBI
pixi run pip install -e .
```

**Issue:** Conda environment creation fails
```bash
# Ensure conda is in your PATH
which conda

# Install Anaconda/Miniconda if not present
# See: https://docs.conda.io/en/latest/miniconda.html
```

**Issue:** Cache directory permission denied
```bash
# Use a directory you have write access to
mkdir -p ~/snakemake-cache
export SNAKEMAKE_OUTPUT_CACHE=~/snakemake-cache/
```

### 📦 What Gets Installed

**TODO**
> update values 

- **Pixi environments**: `~/.pixi/` (~500 MB)
- **Conda packages**: `.snakemake/conda/` (~2 GB)
- **Raw data**: `data/raw/` (~40 GB compressed) - Temporary files
- **Processed data**: `data/processed/` (~50 GB)
- **Database**: `data/processed/databases/` (~15 GB)

### ⏭️ Next Steps

- Explore example notebooks in `notebooks/`
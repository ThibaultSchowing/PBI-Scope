
## 🚀 Installation Guide (To Be Tested)

Get started with PBI in under 10 minutes!

### Prerequisites

- **Linux**/macOS (Windows via WSL2)
- **Python 3.8+**
- **Conda** (used via Snakemake's `--use-conda` option)
- **Internet connection** (for data downloads)
- **Disk space**: >50GB recommended
- **RAM**: >32GB recommended for a smooth non-swapping execution
- **Patience**: building the full database and reports from scratch takes 2-4 hours

### Step-by-Step Installation

#### 1. Clone the Repository

```bash
# Clone PBI repository

git clone <repository-url>
cd PBI

# Check repository structure
ls -la
# Should see: workflow/, src/, data/, notebooks/, README.md, etc.
```


#### 2. Install Anaconda

Install Anaconda. Make sure that the conda command is in your path

#### 3. Install PBI Package

You can install the package in a virtual environment with conda or venv by running the following command from within PBI/

```bash

# Install PBI 
(myenv) pip install -e .

# Verify installation
python -c "import pbi; print(f'✅ PBI v{pbi.__version__} installed successfully')"
```

#### 4. Build the Database

**⚠️ Important:** The first run downloads ~50 GB of data and may take 1-4 hours depending on your connection.

```bash

# [OPTIONAL] You can use caching if you plan to modify or update the data
mkdir -p /mnt/snakemake-cache

# [OPTIONAL] You have to export this each time you restart or move this in you bashrc
export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/


# Run Snakemake pipeline (first run: use 2-4 cores due to I/O bottleneck), add --cache if you set up caching
snakemake --cores 4 --cache --use-conda --printshellcmds --directory workflow --snakefile workflow/Snakefile

# For subsequent runs, you can use more cores:
# snakemake --cores all --directory workflow --snakefile workflow/Snakefile

```
<details>
<summary>Pipeline details</summary>

### Running the Pipeline piece by piece

```bash

# Development (keep temp files with --notemp) - Full pipeline execution (all tables + validation)
snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --notemp --cores 4

# Create database only
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  ../data/databases/phage_database.duckdb

# Generate validation report
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  reports/database_validation.html

# Create optimized database
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  ../data/databases/phage_database_optimized.duckdb
```

</details>

**Command Breakdown:**

- `--cores 4`: Use 4 CPU cores (adjust based on your system)
- `--use-conda`: Automatically create required conda environments
- `--printshellcmds`: Show commands being executed (useful for debugging)
- `--cache` : Use caching for intermediary files
- `--directory` : Specify the workflow directory
- `--snakefile` : Specify the Snakefile

#### 5. Start Jupyter Lab

Run your notebook as you do usualy

```bash
# From project root directory
cd ..
jupyter lab

# Or specify a custom port:
# jupyter lab --port 8889
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
cd workflow && snakemake --cores 4

# Start Jupyter Lab
jupyter lab

# Run Python interactively
python

# Check what would be updated (dry-run)
cd workflow && snakemake -n

# Generate workflow diagram
cd workflow && snakemake --dag | dot -Tsvg > dag/workflow.svg
```

### 🐛 Troubleshooting

**Issue:** Snakemake fails with "No space left on device"
```bash
# Check disk space
df -h

# Clean Snakemake cache if needed
rm -rf .snakemake/
```

**Issue:** Import error: `ModuleNotFoundError: No module named 'pbi'`
```bash
# Reinstall PBI package from project root
cd /path/to/PBI
pip install -e .
```

### 📦 What Gets Installed

**TODO**
> update values 

- **Conda packages**: `.snakemake/conda/` (~2 GB)
- **Raw data**: `data/raw/` (~40 GB compressed) - Temporary files
- **Processed data**: `data/processed/` (~50 GB)
- **Database**: `data/processed/databases/` (~15 GB)

### ⏭️ Next Steps

- Explore example notebooks in `notebooks/`
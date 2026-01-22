# Local Development Setup

This guide explains how to run the PBI pipeline locally (without Docker).

## Prerequisites

- Conda/Miniconda installed
- At least 150 GB free disk space
- 16 GB RAM (32 GB recommended)

## Quick Start

### 1. Create Conda Environment

```bash
conda env create -f workflow/envs/base_environment.yaml
conda activate snakemake_base
```

### 2. Install PBI Package

```bash
pip install -e .
```

### 3. Run the Pipeline

**Option A: Using the helper script (recommended)**

```bash
./run_local.sh
```

To use a different number of cores:

```bash
PBI_CORES=8 ./run_local.sh
```

**Option B: Manual execution**

```bash
# Set environment variable
export PBI_DATA_DIR="data"

# Run Snakemake (adjust --cores as needed)
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda --printshellcmds --cache
```

## Data Directory Structure

The pipeline creates data in `./data/`:

```
data/
├── raw/                    # Downloaded archives (~50 GB)
├── intermediate/           # Processing intermediates
└── processed/              # Final outputs
    ├── databases/          # DuckDB database
    ├── sequences/          # FASTA files + indexes
    └── reports/            # HTML validation reports
```

## Running the API Locally

After the pipeline completes:

```bash
export DATA_PATH="data/processed"
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

Access at: http://localhost:8000/docs

## Differences from Docker

| Aspect | Docker | Local |
|--------|--------|-------|
| Data path | `/data` (absolute) | `data` (relative) |
| Environment | Isolated container | Your system |
| Dependencies | Auto-installed | Manual conda setup |
| Cleanup | `docker compose down -v` | `rm -rf data/` |

## Troubleshooting

### Permission denied errors

- **Docker:** Check volume permissions
- **Local:** Ensure you have write access to project directory

### Out of memory

- Reduce `--cores` parameter
- Close other applications
- Consider using Docker with resource limits

### Conda environment conflicts

```bash
conda env remove -n snakemake_base
conda env create -f workflow/envs/base_environment.yaml
```

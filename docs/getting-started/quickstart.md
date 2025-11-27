## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **Pixi package manager** ([installation guide](https://pixi.sh/latest/))
- **Conda** (used via Snakemake's `--use-conda` option)
- **Internet connection** (for data downloads)
- **Disk space**: >50GB recommended
- **RAM**: >32GB recommended for a smooth non-swapping execution

### Installation

```bash
git clone <repository-url>
cd PBI
pixi install
```

### Running the Pipeline

```bash

# Development (keep temp files with --notemp) - Full pipeline execution (all tables + validation)
pixi run snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --notemp --cores 4

# Create database only
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  ../data/databases/phage_database.duckdb

# Generate validation report
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  reports/database_validation.html

# Create optimized database
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores 4 \
  ../data/databases/phage_database_optimized.duckdb
```

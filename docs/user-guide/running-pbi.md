
## Running the Pipeline

**⚠️ IMPORTANT FOR FIRST-TIME USERS**

If this is your **first time** running the pipeline:
- **The database creation will take 2-4 hours** to download, merge, and validate all data
- The database **will not be queryable** until this initial process completes
- See the complete **[First-Time Setup Procedure](../getting-started/installation.md#4-build-the-database-first-time-setup)** in the installation guide

---

### Quick Reference for Experienced Users

Snakemake is launched from Pixi with `pixi run`. 

**Standard execution command:**

```bash
pixi run snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --notemp --cores 4
```

---

### Environment Setup

#### Cache Configuration (Recommended)

To use [caching](https://snakemake.readthedocs.io/en/stable/executing/caching.html) for intermediate files:

1. **Create the cache directory** (only needed once):
   ```bash
   mkdir -p /mnt/snakemake-cache
   ```

2. **Set the environment variable** (required each session, or add to your shell config):
   ```bash
   # For current session
   export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/
   
   # To make persistent, add to ~/.bashrc or ~/.zshrc:
   echo 'export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/' >> ~/.bashrc
   source ~/.bashrc
   ```

#### Conda Environment

The Conda environment is specified within each Snakemake rule (if needed):

```yaml
conda:
    "envs/pixi_base_env.yaml"
```

---

### Execution Commands

#### First Run (Database Creation)

**⚠️ Use only 2-4 cores** on first execution to avoid I/O bottleneck crashes:

```bash
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --notemp --cores 4
```

#### Subsequent Runs (Updates)

When re-running or updating:
- You can use more cores
- You can omit `--notemp` to remove temporary files

```bash
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --cache --use-conda --printshellcmds --cores all
```

#### Generating Workflow Diagram

```bash
# From root directory - path relative to bash location
pixi run snakemake --directory workflow --snakefile workflow/Snakefile \
  --dag | dot -Tsvg > workflow/dag/dag.svg
```

---

### Core Execution Settings

**For First-Time Execution:**
- Use **2-4 cores maximum**
- I/O operations on your drive will be the bottleneck
- Using more cores may crash the program during initial downloads

**For Subsequent Runs:**
- You can use more cores: `--cores 8` or `--cores all`
- The bottleneck shifts to CPU after data is downloaded

---

### Working Directory

Input, output, log, and benchmark files are considered relative to the working directory:
- Either the directory where you invoked Snakemake
- Or whatever was specified with `--directory`

**Note:** This is why we use `--directory workflow` in the commands above.

---

### Installing PBI Package

To install PBI as an editable package:

```bash
# From the root directory of PBI
pixi run pip install -e .
```

---

### Managing Temporary Files

By default, the `--notemp` flag keeps temporary files (useful for debugging).

To remove temporary files after a successful run:

```bash
pixi run snakemake --delete-temp-output
```

**Note:** Without `--notemp`, regenerating temporary files takes a long time if you modify scripts, which is why it's included in the recommended command during development.




## 🗄️ Using the Database

The pipeline generates a **DuckDB** database optimized for analytical queries.

### Python Integration


```python
import duckdb

# Connect to database
conn = duckdb.connect('data/databases/phage_database_optimized.duckdb')

# Simple query
df = conn.execute("""
    SELECT Source_DB, COUNT(*) as count 
    FROM fact_phages 
    GROUP BY Source_DB
""").df()

# Complex analytical query - phage characterization
results = conn.execute("""
    SELECT 
        f.Source_DB,
        f.Phage_ID,
        f.Length,
        f.GC_content,
        f.Host,
        f.Lifestyle,
        COUNT(DISTINCT p.Protein_ID) as protein_count,
        COUNT(DISTINCT t.terminator_type) as terminator_types,
        COUNT(DISTINCT a.Protein_ID) as anti_crispr_count,
        COUNT(DISTINCT v.Protein_ID) as virulent_factor_count,
        COUNT(DISTINCT tm.Protein_ID) as transmembrane_count,
        COUNT(DISTINCT tr.trna_tmrna_id) as trna_count
    FROM fact_phages f
    LEFT JOIN dim_proteins p ON f.Phage_ID = p.Phage_ID
    LEFT JOIN dim_terminators t ON f.Phage_ID = t.Phage_ID
    LEFT JOIN dim_anti_crispr a ON f.Phage_ID = a.Phage_ID
    LEFT JOIN dim_virulent_factors v ON f.Phage_ID = v.Phage_ID
    LEFT JOIN dim_transmembrane_proteins tm ON f.Phage_ID = tm.Phage_ID
    LEFT JOIN dim_trna_tmrna tr ON f.Phage_ID = tr.Phage_ID
    WHERE f.Length > 50000
    GROUP BY f.Source_DB, f.Phage_ID, f.Length, f.GC_content, f.Host, f.Lifestyle
    ORDER BY f.Length DESC
    LIMIT 100
""").fetchall()

# Query specific dimension tables
transmembrane_stats = conn.execute("""
    SELECT 
        predicted_tmhs_number,
        COUNT(*) as protein_count,
        AVG(protein_length) as avg_length
    FROM dim_transmembrane_proteins
    WHERE predicted_tmhs_number IS NOT NULL
    GROUP BY predicted_tmhs_number
    ORDER BY predicted_tmhs_number
""").df()

conn.close()
```
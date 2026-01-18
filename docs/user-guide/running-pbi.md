
## Running the pipeline

When executing for the first time **do not** use more than 2-4 cores as the I/O operations on your drive will be the bottleneck and might crash the program. 

Input, output, log, and benchmark files are considered to be relative to the working directory (**either the directory in which you have invoked Snakemake** or whatever was specified for --directory or the workdir: directive). -> from the workflow directory !


The Conda environment to use is specified within each rule (if needed) with 

```
    conda:
        "envs/base_env.yaml"
```

Cache: to use [caching](https://snakemake.readthedocs.io/en/stable/executing/caching.html), it is first needed to export snakemake cache with `export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/` (create the destination directory first). After every startup, or set the environment variable in the .bashrc file.


- **Current command:** `snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --notemp --cores 4 `
    - **DAG Option (path relative to bash location)**`--dag | dot -Tsvg > workflow/dag/dag.svg`

- **Install pbi**: to install pbi use the command `pip install -e .` in the root directory. 

To remove the temporary files after execution, use --delete-temp-output. Has to be done separately  (to be verified). In the mean time, the temp() option was removed from the intermediairy files as it takes too long to regenerage when modifying the script.:

- snakemake --delete-temp-output




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
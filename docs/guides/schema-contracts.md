# Schema Contracts Guide

This page explains PBI's **schema contract** system — what it is, how it works, and what to do when upstream data sources change.

---

## Overview

PBI downloads metadata CSV/TSV files from 14+ phage databases via [PhageScope](https://phagescope.deepomics.org/).
Each database may use slightly different column names, add new columns over time, or rename existing ones.

To keep the preprocessing and database-building steps resilient to these changes, every merger script uses a **schema contract**: a YAML file that declares exactly which columns are expected, which are optional, and how alternate names are mapped to canonical names.

```
workflow/schemas/
├── phage_metadata_merged.yaml
├── annotated_proteins_metadata_merged.yaml
├── crispr_array_metadata_merged.yaml
├── transcription_terminator_metadata_merged.yaml
├── anti_crispr_metadata_merged.yaml
├── virulent_factor_metadata_merged.yaml
├── transmembrane_protein_metadata_merged.yaml
├── trna_tmrna_metadata_merged.yaml
└── antimicrobial_resistance_gene_metadata_merged.yaml
```

Each merger script (`workflow/scripts/preprocessing/mergers/merge_*.py`) loads its contract and calls `normalize_df_schema()` on every input file before merging.

---

## How a Contract Works

A contract is a YAML file with four sections:

```yaml
required:
  - Phage_ID       # Must exist — pipeline fails fast if missing
  - Source_DB

optional:
  - Length         # Added as NA (or a default) when absent
  - GC_content
  - Host

aliases:
  Phage_id: Phage_ID       # Alternate name → canonical name
  GC%: GC_content

defaults:          # Optional: provide a fill value instead of NA
  Host: "unknown"
```

| Section | Meaning | What happens if absent |
|---------|---------|------------------------|
| `required` | Column must be present (after alias resolution) | `ValueError` raised — pipeline stops |
| `optional` | Column should exist but may be absent | Added with `pd.NA` or the value from `defaults` |
| `aliases` | Old or alternate column names → canonical name | Applied silently before validation |
| `defaults` | Default value for a specific optional column | Falls back to `pd.NA` if not set |

### Processing order

For every input file:

1. **Strip whitespace** from all column names.
2. **Apply aliases** — rename any alias column to its canonical form.  
   *Collision rule*: if both the alias and the canonical column exist, the canonical column wins and the alias column is dropped (logged as a collision).
3. **Check required columns** — raise `ValueError` with a clear message if any required column is still missing.
4. **Add missing optional columns** — filled with `pd.NA` or the configured default.
5. **Keep unknown columns** — new upstream columns that are not in the contract are **not dropped**; they are sorted and appended at the end.
6. **Reorder deterministically** — output column order is always `required + optional + sorted(unknown)`.
7. A structured **report** is returned containing: `aliases_applied`, `collisions`, `missing_optional`, `added_optional`, `unknown_columns`.

---

## All Schema Contracts at a Glance

### `phage_metadata_merged.yaml`

| Column | Status | Notes |
|--------|--------|-------|
| `Phage_ID` | **required** | Primary key |
| `Source_DB` | **required** | Source database name |
| `Length` | optional | Genome length in bp |
| `GC_content` | optional | Alias: `GC%` |
| `Taxonomy`, `Completeness`, `Host`, `Lifestyle`, `Cluster`, `Subcluster` | optional | Phage annotations |

Known aliases: `Phage_id`, `phage_id`, `Phage_Source`, `Phage_source`, `source_db`, `GC%`

---

### `annotated_proteins_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `Protein_ID`, `Source_DB` | **required** |
| `Protein_source`, `Function_prediction_source`, `Start`, `Stop`, `Strand`, `Product`, `Protein_classification` | optional |
| `Molecular_weight`, `Aromaticity`, `Instability_index`, `Isoelectric_point`, `Helix_fraction`, `Turn_fraction`, `Sheet_fraction`, `Reduced_coefficient`, `Oxidized_coefficient` | optional (biophysical properties) |

Known aliases: `Phage_id`, `Protein_id`, `source_db`

---

### `crispr_array_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `CRISPR_ID`, `Source_DB` | **required** |
| All other CRISPR statistics (positions, spacer counts, conservation, etc.) | optional |

Known aliases: `Phage_id`, `source_db`

---

### `transcription_terminator_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `Source_DB` | **required** |
| `Terminator`, `Start`, `Stop`, `Sense`, `Loc`, `Confidence` | optional |

Known aliases: `Phage_id`, `source_db`

---

### `anti_crispr_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `Protein_ID`, `Source_DB` | **required** |
| `Source` | optional |

Known aliases: `Phage_id`, `Protein_id`, `source_db`

---

### `virulent_factor_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `Protein_ID`, `Source_DB` | **required** |
| `Aligned_Protein_in_VFDB` | optional |

Known aliases: `Phage_id`, `Protein_id`, `source_db`

---

### `transmembrane_protein_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `Protein_ID`, `Source_DB` | **required** |
| `Length`, `PredictedTMHsNumber`, `ExpnumberofAAsinTMHs`, `Expnumberfirst60AAs`, `TotalprobofNin`, `POSSIBLENterm`, all segment start/end columns | optional |

Known aliases: `Phage_id`, `Protein_id`, `source_db`

---

### `trna_tmrna_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `Source_DB` | **required** |
| `t(m)RNA_ID`, `Source`, `t(m)RNA`, `Start`, `Stop`, `Strand`, `Length`, `Permuted`, `Sequence` | optional |

Known aliases: `Phage_id`, `source_db`

---

### `antimicrobial_resistance_gene_metadata_merged.yaml`

| Column | Status |
|--------|--------|
| `Phage_ID`, `Protein_ID`, `Source_DB` | **required** |
| `Aligned_Protein_in_CARD` | optional |

Known aliases: `Phage_id`, `Protein_id`, `source_db`

---

## Consistency Verification

All contracts have been verified against `workflow/scripts/database/create_duckdb.py`:
every column selected in SQL `CREATE TABLE ... AS SELECT ...` for each DuckDB table
is covered either as `required` or `optional` in the corresponding contract.

To re-verify at any time:

```bash
python - <<'PY'
import yaml
from pathlib import Path

# Mapping: contract file → columns DuckDB reads from the merged CSV
checks = {
    "phage_metadata_merged.yaml": [
        "Phage_ID", "Source_DB", "Length", "GC_content", "Taxonomy",
        "Completeness", "Host", "Lifestyle", "Cluster", "Subcluster"],
    "annotated_proteins_metadata_merged.yaml": [
        "Phage_ID", "Protein_ID", "Protein_source", "Function_prediction_source",
        "Start", "Stop", "Strand", "Product", "Protein_classification",
        "Molecular_weight", "Aromaticity", "Instability_index", "Isoelectric_point",
        "Helix_fraction", "Turn_fraction", "Sheet_fraction",
        "Reduced_coefficient", "Oxidized_coefficient", "Source_DB"],
    # ... add remaining tables as needed
}

schema_dir = Path("workflow/schemas")
for fname, used_cols in checks.items():
    with open(schema_dir / fname) as fh:
        c = yaml.safe_load(fh)
    covered = set(c.get("required", []) + c.get("optional", []))
    missing = set(used_cols) - covered
    if missing:
        print(f"❌ {fname}: uncovered columns → {missing}")
    else:
        print(f"✅ {fname}: all columns covered")
PY
```

---

## What to Do When Upstream Data Changes

### Scenario 1 — A column is renamed in the source CSV

**Example**: PhageScope renames `GC%` to `GC_content`.

**Action**:

1. Open the relevant contract, e.g. `workflow/schemas/phage_metadata_merged.yaml`.
2. Add the old name under `aliases:`:

```yaml
aliases:
  GC%: GC_content   # ← add this
```

3. Rebuild the database. The merger will silently rename the column and log it.

---

### Scenario 2 — New columns appear in the source CSV

**Example**: PhageScope adds `Is_Predicted` and `Prediction_Source` fields.

New columns that are **not** in the contract are **automatically preserved** in the merged CSV — you do not need to do anything for the data to flow through safely.

However, for each layer of the pipeline, explicit action is required to *use* the new columns:

#### 2a — To include the new column in the DuckDB table

1. Add it to the relevant contract as `optional:`:

```yaml
optional:
  - Is_Predicted       # ← new
  - Prediction_Source  # ← new
```

2. Edit `workflow/scripts/database/create_duckdb.py` and add the column to the `SELECT` for the corresponding table:

```sql
CREATE TABLE fact_phages AS
SELECT
    Phage_ID,
    ...
    Is_Predicted,        -- new
    Prediction_Source,   -- new
    Source_DB
FROM read_csv(...)
```

3. Rebuild the database.

> **Note**: `create_duckdb.py` uses explicit `SELECT` lists. Unknown columns in the merged CSV are not automatically ingested into DuckDB tables — you must add them to the SQL explicitly.

#### 2b — To expose the new column through the `pbi` Python package

The `pbi` package queries specific DuckDB table columns (e.g. `get_phage_metadata()` returns a fixed set of columns).

1. Edit `src/pbi/sequence_retrieval.py` and update the relevant query:

```python
query = """
SELECT
    Phage_ID,
    Source_DB,
    ...
    Is_Predicted,      -- new
    Prediction_Source, -- new
    ...
FROM fact_phages
"""
```

2. Update the method docstring to document the new return columns.
3. Bump the package version in `src/pbi/__init__.py` if the interface changes.

> **The `pbi` package does NOT automatically expose new database columns.** Explicit changes to `sequence_retrieval.py` are required.

---

### Scenario 3 — A previously optional column becomes required

1. Move it from `optional:` to `required:` in the contract.
2. The pipeline will now fail fast (with a clear error message) if any source file is missing the column, instead of silently filling it with `NA`.

---

### Scenario 4 — A required column is removed by the upstream source

1. Move it from `required:` to `optional:` in the contract.
2. Optionally add a `defaults:` entry if a fallback value is meaningful.
3. Update `create_duckdb.py` if the column is used in the SQL `SELECT` — either remove it or wrap it with `COALESCE(col, NULL)`.

---

## Summary: Change Procedure Checklist

| Change | Contract | `create_duckdb.py` | `pbi` package |
|--------|----------|-------------------|---------------|
| Column renamed | Add alias | No change needed | No change needed |
| New column — preserve only | No change | No change | No change |
| New column — add to DuckDB | Add to `optional:` | Add to `SELECT` | No change |
| New column — expose via `pbi` | Add to `optional:` | Add to `SELECT` | Add to query in `sequence_retrieval.py` |
| Optional → required | Move in contract | No change | No change |
| Required column removed | Move to `optional:` | Handle `NULL` in SQL | Handle `None` in Python |

---

## Schema Drift Report Tool

Use this CLI to check any source file against a contract *before* running the pipeline:

```bash
python workflow/scripts/preprocessing/report_schema_drift.py \
  --contract workflow/schemas/phage_metadata_merged.yaml \
  --input path/to/downloaded/phage_metadata.tsv \
  --dataset-name phage_metadata
```

**Output example:**

```
✅ Schema drift check passed
Missing optional before normalization: ['Host', 'Lifestyle']
Added optional columns: ['Host', 'Lifestyle']
Aliases applied: [{'from': 'GC%', 'to': 'GC_content'}]
Collisions: []
Unknown columns preserved: ['Is_Predicted', 'Prediction_Source']
```

Exit code is non-zero when required columns are missing, allowing use in CI checks:

```bash
python workflow/scripts/preprocessing/report_schema_drift.py \
  --contract workflow/schemas/phage_metadata_merged.yaml \
  --input new_data.tsv || echo "Schema check failed!"
```

---

## Where the Code Lives

| File | Purpose |
|------|---------|
| `workflow/schemas/*.yaml` | One contract per merged output |
| `workflow/scripts/preprocessing/mergers/schema_contracts.py` | `load_contract()` and `normalize_df_schema()` |
| `workflow/scripts/preprocessing/mergers/merge_*.py` | Each merger — calls `normalize_df_schema` on input and final merged DataFrame |
| `workflow/scripts/preprocessing/report_schema_drift.py` | CLI drift reporter |
| `workflow/scripts/database/create_duckdb.py` | Reads merged CSVs and builds DuckDB tables |
| `src/pbi/sequence_retrieval.py` | `pbi` package — queries DuckDB columns explicitly |

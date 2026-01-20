# CSV Column Consistency Fix

## Problem Description

The report generation was failing with CSV tokenization errors:

```
ERROR:root:Error during report generation: Error tokenizing data. C error: Expected 26 fields in line 32474, saw 27
ERROR:root:Error during report generation: Error tokenizing data. C error: Expected 10 fields in line 441639, saw 11
ERROR:root:Error during report generation: Error tokenizing data. C error: Expected 8 fields in line 3912548, saw 9
```

### Root Cause

The issue was caused by inconsistent column handling in merged CSV files:

1. The `rename_columns()` function in `utils.py` automatically adds a `Source_DB` column to DataFrames that don't have it
2. Not all merger scripts included `Source_DB` (or `Phage_source` where needed) in their `COLUMNS_LIST`
3. When DataFrames were merged, some rows had these columns while others didn't
4. This created CSV files where some rows had trailing empty commas (`,` at the end)
5. When pandas reads these files in chunks (as done in report generation), it can infer different numbers of columns for different chunks, causing tokenization errors

### Example of the Problem

From the problem statement, in `merged_crispr_array_metadata.csv`:

```csv
# Row with Source_DB column
TemPhD_cluster_9791,0,TemPhD_cluster_9791_1,35443,35537,94,Forward,Unknown,TGGACAATCGTTGGACATCCGTTGGACAA,Unknown,0,29,1,37.0,0.0,2,1.0,100.0,100.0,100.0,100.0,66.0,0.783783783783784,0,1,TemPhD,

# Row with Source_DB column populated
SAMEA1906422_b1_ct69_vs2,0,SAMEA1906422_b1_ct69_vs2_1,19441,19514,73,Forward,Unknown,TTTGCCTAAGCAAATTGCCTAAGCAAAA,Unknown,0,28,1,18.0,0.0,1,0.5,71.4285714285714,71.4285714285714,100.0,100.0,46.0,1.55555555555556,0,1,CHVD,CHVD
```

Notice the trailing comma in the first row - this indicates an empty `Source_DB` value. If a chunk starts with rows that don't have this pattern, pandas might infer 25 columns. If the next chunk has rows with the trailing comma, pandas expects 26 columns, causing the tokenization error.

## Solution

### 1. Updated All Merger Scripts

Added missing columns to `COLUMNS_LIST` in each merger script to match the database schema expectations:

- **phage_metadata**: Added `Source_DB`
- **crispr_array_metadata**: Added `Source_DB`
- **transcription_terminator_metadata**: Added `Source_DB`
- **transmembrane_protein_metadata**: Added `Source_DB`
- **anti_crispr_metadata**: Added `Phage_source` and `Source_DB`
- **virulent_factor_metadata**: Added `Phage_source` and `Source_DB`
- **trna_tmrna_metadata**: Added `Phage_source` and `Source_DB`
- **antimicrobial_resistance_gene_metadata**: Added `Source_DB`

### 2. Enhanced `validate_columns()` Function

Modified the function to:
- Create a copy of the DataFrame to avoid side effects
- Add missing columns with NaN values
- Reorder columns to match the expected order
- Return the modified DataFrame

```python
def validate_columns(df, expected_columns):
    """Validate that the DataFrame contains all expected columns.
    Adds missing columns with NaN values and reorders to match expected order.
    """
    # Create a copy to avoid modifying the original DataFrame
    df = df.copy()
    
    # Add missing columns with NaN values
    for col in missing_cols:
        df[col] = np.nan
        logging.info(f"Added missing column '{col}' with NaN values")
    
    # Reorder to match expected columns
    ordered_cols = [col for col in expected_columns if col in df.columns]
    return df[ordered_cols]
```

### 3. Enhanced `merge_dataframes_chunked()` Function

Modified the function to:
- Ensure all DataFrames have the same column order as the first one
- Use `validate_columns()` to add missing columns and reorder
- Keep only the columns that exist in the first DataFrame

```python
def merge_dataframes_chunked(dfs, output_file):
    # Ensure all dataframes have the same column order as the first one
    first_columns = list(dfs[0].columns)
    
    for i, df in enumerate(dfs):
        # Use validate_columns to ensure consistent column order
        validated_df = validate_columns(df, first_columns)
        # Keep only the columns from the first dataframe
        dfs[i] = validated_df[first_columns]
    
    # Write to CSV with consistent column structure
    # ...
```

### 4. Updated All Merger Scripts to Use Return Value

Changed all merger scripts from:
```python
if not utils.validate_columns(df, COLUMNS_LIST):
    logging.warning(f"File {infile} is missing expected columns. Skipping.")
    continue
```

To:
```python
# Validate and reorder columns to match expected schema
df = utils.validate_columns(df, COLUMNS_LIST)
```

## Testing

### Unit Tests

1. **test_column_consistency.py** - Tests for:
   - Column ordering consistency
   - Merging with inconsistent columns
   - CSV reading in chunks
   - Handling both Phage_source and Source_DB columns

2. **test_tokenization_fix_integration.py** - Integration tests for:
   - Exact CRISPR array metadata scenario from the problem statement
   - Report generation simulation with chunked reading

### Results

- ✅ All existing tests pass (test_csv_quoting.py, test_chunked_merge.py)
- ✅ All new unit tests pass
- ✅ All integration tests pass
- ✅ Code review completed and feedback addressed
- ✅ Security scan (CodeQL) completed - **0 vulnerabilities found**

## Impact

This fix ensures that:

1. **Consistent Column Structure**: All merged CSV files have the same columns in the same order
2. **No Missing Data**: Missing columns are properly filled with NaN values
3. **Chunk-Safe Reading**: CSV files can be read in chunks without tokenization errors
4. **Report Generation Works**: The report generation script can process all merged CSV files
5. **Database Compatibility**: All expected columns are present for database creation

## Files Modified

### Core Files (2)
- `workflow/scripts/preprocessing/mergers/utils.py`

### Merger Scripts (9)
- `workflow/scripts/preprocessing/mergers/merge_annotated_proteins_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_antimicrobial_resistance_gene_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_crispr_array_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_phage_anti_crispr_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_phage_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_phage_transmembrane_protein_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_phage_trna_tmrna_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_phage_virulent_factor_metadata.py`
- `workflow/scripts/preprocessing/mergers/merge_transcription_terminator_metadata.py`

### Test Files (2)
- `tests/test_column_consistency.py` (new)
- `tests/test_tokenization_fix_integration.py` (new)

## Migration Notes

For existing deployments:

1. **Existing Merged CSV Files**: Need to be regenerated with the new merger scripts to ensure column consistency
2. **Database**: Will work with both old and new CSV files due to `null_padding=true` in the database creation script
3. **Report Generation**: Will work correctly only after CSV files are regenerated

## Related Documentation

- See `CSV_PARSING_FIX_SUMMARY.md` for previous CSV parsing fixes
- See `CSV_TOKENIZATION_FIX.md` for the initial tokenization error fix
- See `OOM_FIX_SUMMARY.md` for the chunked merge implementation

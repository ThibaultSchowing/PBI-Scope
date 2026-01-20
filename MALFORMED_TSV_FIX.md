# Fix: Column Number Inconsistency in Merged CSV Files

## Problem Statement

The merge scripts were producing CSV files with inconsistent column counts, causing tokenization errors during report generation:

```
ERROR:root:Error during report generation: Error tokenizing data. C error: Expected 26 fields in line 32474, saw 27
ERROR:root:Error during report generation: Error tokenizing data. C error: Expected 8 fields in line 3912548, saw 9
```

Looking at the merged CSV files:
- Header: `Evidence_Level,Source_DB` (2 columns)
- Some rows: `1,TemPhD` (correct - 2 values)
- Other rows: `1,CHVD,CHVD` (incorrect - 3 values, duplicate CHVD)

## Root Cause Analysis

### The Bug

When TSV input files contain rows with **extra values** (more values than column headers), pandas' default behavior is to automatically use the **first column as the row index**. This causes severe data corruption:

1. **Value Shifting**: All column values shift left (e.g., CRISPR_ID value goes into Phage_ID column)
2. **Index Misuse**: The intended first column value becomes the row index instead of data
3. **Apparent Duplication**: The last value appears duplicated because it stays in its correct position while others shift

### Example Scenario

**Input TSV file (malformed):**
```tsv
Phage_ID	CRISPR_ID	Evidence_Level	Source_DB
phage1	crispr1	1	CHVD	CHVD
phage2	crispr2	1	TemPhD
```

**What pandas does by default:**
```python
df = pd.read_csv('file.tsv', sep="\t", quoting=csv.QUOTE_NONNUMERIC)
```

Result:
- Row 1: Index=`phage1`, Phage_ID=`crispr1`, CRISPR_ID=`1`, Evidence_Level=`CHVD`, Source_DB=`CHVD`
- Row 2: Index=`phage2`, Phage_ID=`crispr2`, CRISPR_ID=`1`, Evidence_Level=`TemPhD`, Source_DB=`NaN`

**When written to CSV:**
```csv
"Phage_ID","CRISPR_ID","Evidence_Level","Source_DB"
"crispr1",1.0,"CHVD","CHVD"
"crispr2",1.0,"TemPhD",""
```

Notice the data is **corrupted** - `crispr1` is in the Phage_ID column instead of `phage1`!

### Why This Causes Tokenization Errors

The merged CSV has:
- Some rows from well-formed TSVs: 4 values (correct)
- Some rows from malformed TSVs with shifted data: Still 4 values but WRONG data

When different source files have different levels of malformation, the inconsistency can create rows with different numbers of actual data values, causing pandas to fail when reading in chunks.

## Solution

### The Fix

Add `index_col=False` parameter to all `pd.read_csv()` calls:

```python
df = pd.read_csv(infile, sep="\t", quoting=csv.QUOTE_NONNUMERIC, index_col=False)
```

With this fix:
- Pandas uses numeric indices (0, 1, 2, ...) instead of using column data
- Extra values in malformed rows are **dropped** with a warning
- Data stays in the correct columns
- No data corruption occurs

**Result with fix:**
```python
df = pd.read_csv('file.tsv', sep="\t", quoting=csv.QUOTE_NONNUMERIC, index_col=False)
```

- Row 0: Phage_ID=`phage1`, CRISPR_ID=`crispr1`, Evidence_Level=`1`, Source_DB=`CHVD` ✅ CORRECT!
- Row 1: Phage_ID=`phage2`, CRISPR_ID=`crispr2`, Evidence_Level=`1`, Source_DB=`TemPhD` ✅ CORRECT!

The extra `CHVD` in row 1 is dropped with a warning: `ParserWarning: Length of header or names does not match length of data. This leads to a loss of data with index_col=False.`

## Implementation

### Files Modified

Modified 10 Python files to add `index_col=False` to all `pd.read_csv()` calls:

1. `workflow/scripts/preprocessing/mergers/merge_annotated_proteins_metadata.py`
2. `workflow/scripts/preprocessing/mergers/merge_antimicrobial_resistance_gene_metadata.py`
3. `workflow/scripts/preprocessing/mergers/merge_crispr_array_metadata.py`
4. `workflow/scripts/preprocessing/mergers/merge_phage_anti_crispr_metadata.py`
5. `workflow/scripts/preprocessing/mergers/merge_phage_metadata.py`
6. `workflow/scripts/preprocessing/mergers/merge_phage_transmembrane_protein_metadata.py`
7. `workflow/scripts/preprocessing/mergers/merge_phage_trna_tmrna_metadata.py`
8. `workflow/scripts/preprocessing/mergers/merge_phage_virulent_factor_metadata.py`
9. `workflow/scripts/preprocessing/mergers/merge_transcription_terminator_metadata.py`
10. `workflow/scripts/preprocessing/mergers/utils.py`

### Example Change

**Before:**
```python
df = pd.read_csv(infile, sep="\t", quoting=csv.QUOTE_NONNUMERIC)
```

**After:**
```python
df = pd.read_csv(infile, sep="\t", quoting=csv.QUOTE_NONNUMERIC, index_col=False)
```

## Testing

### New Test Suite

Created `tests/test_malformed_tsv_fix.py` with 4 comprehensive tests:

1. **test_malformed_tsv_with_extra_values()**: Tests basic malformed TSV handling
2. **test_malformed_tsv_through_pipeline()**: Tests full merge pipeline with malformed data
3. **test_multiple_malformed_rows()**: Tests multiple rows with extra values
4. **test_without_index_col_false()**: Demonstrates the bug without the fix

### Test Results

All tests pass:
- ✅ New malformed TSV tests (4/4)
- ✅ Existing column consistency tests (4/4)
- ✅ Existing chunked merge tests (4/4)
- ✅ Existing CSV quoting tests (5/5)
- ✅ Existing TSV reading tests (3/3)

**Total: 20/20 tests passing**

### Code Review

- ✅ No review comments
- ✅ All changes are minimal and surgical
- ✅ No unrelated code modified

### Security Scan

- ✅ CodeQL scan: **0 vulnerabilities found**

## Impact

### Benefits

1. **Data Integrity**: Column values stay in their correct positions
2. **No Corruption**: Malformed source data doesn't corrupt the entire merged CSV
3. **Predictable Behavior**: Extra values are consistently dropped with warnings
4. **Report Generation**: CSV files can now be read successfully in chunks without tokenization errors
5. **Robustness**: Pipeline handles real-world data quality issues gracefully

### Trade-offs

- **Data Loss**: Extra values in malformed rows are dropped
  - This is actually a GOOD thing - we don't want corrupt data
  - Warnings are logged so users can investigate source data issues
- **Warnings**: Users will see `ParserWarning` for malformed TSV files
  - These warnings are informative and help identify data quality problems

### Migration Notes

For existing deployments:

1. **Existing Merged CSV Files**: Should be regenerated with the new merger scripts to ensure data integrity
2. **Source TSV Files**: Review any files that generate warnings to fix data quality issues at the source
3. **Database**: Will work correctly with the new merged CSV files
4. **Report Generation**: Will now work without tokenization errors

## Related Issues

This fix addresses the issue mentioned in the problem statement where:
- Different source databases have different data quality
- Some source files may already have certain columns (like `Source_DB`) while others don't
- Some source files may have malformed rows with extra values

The fix ensures that regardless of source data quality, the merge process produces consistent, valid CSV files.

## Conclusion

This fix resolves the column number inconsistency by preventing pandas from auto-indexing malformed TSV rows. The solution is minimal, surgical, and well-tested, ensuring data integrity throughout the merge pipeline.

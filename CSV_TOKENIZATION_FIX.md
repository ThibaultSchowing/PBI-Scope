# CSV Tokenization Error Fix

## Problem Statement

The pipeline was failing during report generation with CSV tokenization errors:

```
ERROR:root:Error during report generation: Error tokenizing data. C error: Expected 26 fields in line 32474, saw 27
ERROR:root:Error during report generation: Error tokenizing data. C error: Expected 10 fields in line 441639, saw 11
```

These errors occurred when `generate_reports.py` tried to read the merged CSV files that were created by the merger scripts.

## Root Cause Analysis

The issue had two parts:

1. **Previous Fix (CSV_PARSING_FIX_SUMMARY.md)**: 
   - Added `quoting=csv.QUOTE_NONNUMERIC` to CSV **writing** in `utils.merge_dataframes_chunked()`
   - Added `quoting=csv.QUOTE_NONNUMERIC` to CSV **reading** in `generate_reports.py`

2. **Missing Fix** (this PR):
   - The merger scripts were **reading input TSV files** without `quoting=csv.QUOTE_NONNUMERIC`
   - This caused problems when TSV input files had quoted fields with commas
   - Example: `"Mycobacterium smegmatis, strain MC2 155"` in a TSV file

### Why This Matters

When TSV files contain quoted fields with commas (e.g., `"Host, species"`), pandas needs to know to respect the quotes. Without the `quoting` parameter:

```python
# WRONG: Treats comma inside quotes as delimiter
df = pd.read_csv(file, sep="\t")  
# Field "A, B" becomes 2 fields: "A" and "B"

# CORRECT: Respects quoted fields
df = pd.read_csv(file, sep="\t", quoting=csv.QUOTE_NONNUMERIC)
# Field "A, B" stays as one field
```

## Solution

Added `quoting=csv.QUOTE_NONNUMERIC` to **all** `pd.read_csv()` calls in the merger scripts:

### Files Modified

1. `merge_annotated_proteins_metadata.py`
2. `merge_antimicrobial_resistance_gene_metadata.py`
3. `merge_crispr_array_metadata.py`
4. `merge_phage_anti_crispr_metadata.py`
5. `merge_phage_metadata.py`
6. `merge_phage_transmembrane_protein_metadata.py`
7. `merge_phage_trna_tmrna_metadata.py`
8. `merge_phage_virulent_factor_metadata.py`
9. `merge_transcription_terminator_metadata.py`
10. `utils.py` (validation read)

### Changes Made

For each file:
```python
# Added import
import csv

# Changed read call
# FROM:
df = pd.read_csv(infile, sep="\t")

# TO:
df = pd.read_csv(infile, sep="\t", quoting=csv.QUOTE_NONNUMERIC)
```

## Testing

Created comprehensive test suite in `tests/test_tsv_reading.py`:

- ✅ Test reading TSV files with commas in quoted fields
- ✅ Test backward compatibility with unquoted TSV files
- ✅ Test reading TSV files with mixed numeric/string content
- ✅ All existing CSV quoting tests still pass

## Complete CSV Handling Pipeline

Now the entire pipeline uses consistent quoting:

```
Input TSV files (may have quotes)
    ↓
[FIXED] Read with quoting=csv.QUOTE_NONNUMERIC (merger scripts)
    ↓
Process data
    ↓
[ALREADY FIXED] Write with quoting=csv.QUOTE_NONNUMERIC (utils.py)
    ↓
Merged CSV files
    ↓
[ALREADY FIXED] Read with quoting=csv.QUOTE_NONNUMERIC (generate_reports.py)
    ↓
HTML Reports ✅
```

## Benefits

1. **Robustness**: Handles fields with commas, quotes, newlines, and other special characters
2. **Consistency**: All CSV/TSV operations use the same quoting strategy
3. **Data Integrity**: No data loss from misinterpreted delimiters
4. **Backward Compatible**: Works with both quoted and unquoted input files

## Verification

- ✅ All tests pass
- ✅ Code review: No issues
- ✅ Security scan: No vulnerabilities
- ✅ Minimal changes: Only added necessary quoting parameter

## Impact

This fix completes the CSV parsing improvements started in CSV_PARSING_FIX_SUMMARY.md by ensuring the **entire pipeline** (reading input TSVs, writing merged CSVs, reading merged CSVs) uses consistent quoting.

Users should no longer see "Expected X fields, saw Y" tokenization errors when running the pipeline.

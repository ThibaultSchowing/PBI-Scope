# Host Genome Resolution Improvements

## Overview

This document describes the improvements made to handle semicolon-separated Host fields in the phage metadata pipeline.

## Problem

The pipeline was failing to resolve host genomes for many phages because the "Host" field contained complex, semicolon-separated values like:

```
NA;GCA 900066335.1;UBA9502;Blautia...
```

Issues:
1. The entire field was treated as a species name (e.g., "NA;GCA 900066335.1;Lachnospira")
2. GCA accession numbers had spaces instead of underscores (e.g., "GCA 900066335.1" vs "GCA_900066335.1")
3. No fallback mechanism when primary identifier failed
4. "NA" values were not filtered out

This resulted in logs like:
```
2026-02-18 13:57:56,005 - WARNING - ⚠️  Could not resolve TaxID for 'NA;GCA 900066365.1;Lachnospira' (may be ambiguous)
2026-02-18 13:57:58,059 - WARNING - ⚠️  No assemblies found for species: NA;GCA 900066365.1;Lachnospira
```

## Solution

### 1. Enhanced AssemblyResolver

**Added new methods:**

- `parse_host_field(host_field: str)` - Parses semicolon-separated fields
  - Splits on semicolons
  - Fixes "GCA 900066335.1" → "GCA_900066335.1"
  - Filters out "NA" and empty values
  - Identifies type of each component
  - Returns identifiers in priority order

- `resolve_with_fallback(identifier: str)` - Tries multiple resolution strategies
  - Parses complex fields
  - Tries each component in priority order:
    1. Assembly accessions (GCF_/GCA_)
    2. BioSample accessions
    3. BioProject accessions
    4. TaxIDs
    5. Species names
  - Returns first successful resolution

**Updated methods:**

- `get_best_assembly()` - Now uses `resolve_with_fallback()` automatically

### 2. Updated All Download Scripts

**download_host_genomes_optimized.py:**
- Modified `extract_unique_hosts_from_csv()` to preserve raw Host values
- Removed extraction of just "Genus species" format

**download_host_genomes_robust.py:**
- Modified `extract_unique_hosts()` to preserve raw Host values

**download_host_genomes.py:**
- Added `extract_best_host_identifier()` function
- Added `search_assembly_by_accession()` method
- Added module-level regex constants to avoid duplication
- Updated `download_host_genome()` to handle assembly accessions directly

## Examples

### Before

```
Input: "NA;GCA 900066365.1;Lachnospira"
Processing: Treated as species name
Result: ❌ FAILED - "NA;GCA 900066365.1;Lachnospira" is not a valid species
```

### After

```
Input: "NA;GCA 900066365.1;Lachnospira"
Parsing:
  1. "GCA_900066365.1" (assembly_accession) - fixed space
  2. "Lachnospira" (species_name)
  (Filtered out: "NA")

Resolution strategy:
  1. Try "GCA_900066365.1" first → ✅ SUCCESS
  2. Fallback to "Lachnospira" if needed
```

## Testing

Created comprehensive test suite with 12 tests:

- `test_parse_simple_species_name` - Basic species names still work
- `test_parse_gca_with_space` - Fixes "GCA 900066335.1" → "GCA_900066335.1"
- `test_parse_gcf_with_space` - Fixes "GCF 000005845.2" → "GCF_000005845.2"
- `test_parse_semicolon_separated_with_na` - Handles NA values correctly
- `test_parse_complex_semicolon_separated` - Complex multi-component fields
- `test_parse_empty_field` - Handles null/empty fields
- `test_parse_only_na_values` - All NA fields return empty
- `test_priority_ordering` - Accessions prioritized over names
- `test_gca_embedded_in_text` - GCA fixed even when embedded
- Plus 3 API integration tests (require NCBI credentials)

All tests pass! ✅

## Impact

This change **maximizes the chances of finding a genome for each phage** by:

1. **Extracting GCA/GCF accessions** when present (most reliable)
2. **Fixing formatting issues** (space → underscore)
3. **Providing fallback options** (try species name if accession fails)
4. **Filtering noise** (NA values, empty strings)

## Code Quality

- ✅ All tests pass
- ✅ Code review completed, feedback addressed
- ✅ Security scan (CodeQL) - no issues found
- ✅ Consistent with existing code style
- ✅ Added comprehensive documentation

## Files Changed

1. `workflow/scripts/sequences/assembly_resolver.py` - Core parsing logic
2. `workflow/scripts/sequences/download_host_genomes_optimized.py` - Optimized downloader
3. `workflow/scripts/sequences/download_host_genomes_robust.py` - Robust downloader
4. `workflow/scripts/sequences/download_host_genomes.py` - Basic downloader
5. `tests/test_host_field_parsing.py` - New test suite
6. `tests/demo_host_parsing.py` - Demonstration script

## Usage

No changes to the pipeline interface are required. The improvements are transparent:

```python
# Works exactly as before, but now handles complex fields
resolver = AssemblyResolver(email='user@example.org')

# Automatically parses and prioritizes components
assembly = resolver.get_best_assembly("NA;GCA 900066365.1;Lachnospira")
# Returns: GCA_900066365.1 assembly metadata
```

## Demonstration

Run the demo script to see the parsing in action:

```bash
python tests/demo_host_parsing.py
```

This shows exactly how each problematic case from the logs is now handled.

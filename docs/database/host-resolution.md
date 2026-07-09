# Host Genome Resolution

## Overview

This page describes how PBI-Scope resolves phage host information to downloadable bacterial genome assemblies from NCBI RefSeq.

!!! warning "Host prediction bias"
    Most host assignments in PhageScope are **predicted by [DeepHost](https://academic.oup.com/bib/article/23/1/bbab385/6374063)**, not experimentally validated. This introduces a significant bias: if you build a host prediction model using this data, you are training on already-predicted labels rather than curated ground truth.

    We are in communication with the DeepHost authors to address this issue. See [Work in Progress](../index.md#work-in-progress) for details.

Host genome resolution is a critical step because phage metadata from PhageScope contains complex, varied host field formats. A single phage's "Host" field may contain multiple identifiers in different formats, separated by semicolons:

```
NA;GCA 900066335.1;UBA9502;Blautia obeum
```

The pipeline parses this into individual tokens, classifies each token, and resolves them to NCBI assembly accessions.


## Solution

### Stage 1 – Lossless parsing: `phage_host_candidates.csv`

The new standalone `parse_host_field(host_raw)` function splits the raw Host
field into individual tokens:

* Splits on semicolons.
* Normalises `GCA 900066335.1` → `GCA_900066335.1` (space → underscore).
* Drops empty, `NA`, `unknown*`, and `unidentified*` values.
* Classifies each token:
  * `assembly_accession` – matches `GCA_` / `GCF_` pattern.
  * `species_name` – two+ words, genus capitalized (binomial nomenclature).
  * `other` – single words, codes such as `UBA9502`, etc.
* Preserves `Token_Order` (1-based position in the original field).

The pipeline writes **one row per (Phage_ID, token)** to
`phage_host_candidates.csv`.  This is the lossless, auditable record of every
host candidate parsed from the metadata.

#### Example

| Phage_ID | Host_Raw                                  | Host_Token       | Token_Type         | Token_Order |
|----------|-------------------------------------------|------------------|--------------------|-------------|
| phage1   | NA;GCA 900066335.1;UBA9502;Blautia obeum  | GCA_900066335.1  | assembly_accession | 2           |
| phage1   | NA;GCA 900066335.1;UBA9502;Blautia obeum  | UBA9502          | other              | 3           |
| phage1   | NA;GCA 900066335.1;UBA9502;Blautia obeum  | Blautia obeum    | species_name       | 4           |

### Stage 2 – Resolution: `phage_host_assemblies.csv`

Each unique token is resolved independently via `resolve_host_token()`:

* `assembly_accession` → direct NCBI Assembly lookup (confidence 0.95).
* `species_name` → NCBI Taxonomy + Assembly search (confidence 0.70).
* `other` → attempted species search as fallback (confidence 0.30).

The pipeline writes **one row per (Phage_ID, Assembly_Accession)** to
`phage_host_assemblies.csv`.  This is the authoritative flat mapping used to
drive host genome downloads.

| Column             | Description                                                      |
|--------------------|------------------------------------------------------------------|
| Phage_ID           | Phage identifier                                                 |
| Host_Raw           | Original un-parsed Host field (traceability)                     |
| Host_Token         | Specific token that was resolved                                 |
| Token_Type         | `assembly_accession` / `species_name` / `other`                 |
| Token_Order        | 1-based position in Host_Raw                                    |
| Assembly_Accession | Resolved NCBI accession                                          |
| Resolution_Source  | `accession_in_host_field` / `species_to_taxid_to_assembly` / `fallback` |
| Resolution_Rank    | 1-based rank within results for this token                       |
| Confidence         | Float 0–1 derived from source + rank                            |
| Assembly_Level     | `Complete Genome`, `Chromosome`, `Scaffold`, or `Contig`         |
| RefSeq_Category    | `reference genome`, `representative genome`, or `na`            |
| Quality_Score      | Integer quality score                                            |
| Ambiguous          | `True` when multiple equally-plausible hits exist               |
| Ambiguity_Reason   | Human-readable reason when ambiguous                             |

### Stage 3 – Download unique assemblies

Host genome downloads are now driven by the **unique `Assembly_Accession` values
in `phage_host_assemblies.csv`**.  Each accession is downloaded exactly once,
even if linked to many phages (deduplication).

### Backward-compatible outputs

The following outputs remain unchanged (same columns):

* `host_metadata.csv` – per-assembly metadata (one row per unique assembly).
* `assembly_metadata.csv` – detailed assembly metadata.
* `phage_host_links.csv` – phage→assembly links (extended, one row per unique
  (Phage_ID, Assembly_Accession) pair).

## Snakemake caching (idempotency)

Snakemake's file-based dependency tracking ensures the `download_host_genomes`
rule is **not re-executed** when all output files already exist and are newer
than the input phage CSV.

The new outputs (`phage_host_candidates` and `phage_host_assemblies`) are
declared as rule outputs in `hosts.smk`, so Snakemake tracks them automatically.

Within a single run, the `skip_existing=True` parameter (default) prevents
re-downloading individual genome files that were already successfully retrieved.

Across reruns, host token resolution also uses a persistent cache file:

- `host_token_resolution_cache.json` (default path:
  `pipeline_logs/csv/host_token_resolution_cache.json`)

When `reuse_host_resolution_cache: true` (default in `workflow/config/config.yaml`),
previously resolved tokens are reused, so expensive taxonomy/assembly lookups are
not repeated unnecessarily.

To force a fresh token resolution pass, disable cache reuse for that run:

```bash
snakemake --cores 4 --use-conda \
  --forcerun download_host_genomes \
  --config reuse_host_resolution_cache=false
```

## Testing

New unit tests in `tests/test_multi_host_parsing.py`:

* `TestParseHostField` – 18 tests for the `parse_host_field()` function,
  including all examples from the problem statement.
* `TestGenerateCandidates` – 5 tests for `_generate_candidates()`.
* `TestBuildAssemblyLinks` – 7 tests for `_build_assembly_links()`, including
  multi-host, unresolved, and ambiguous cases.

All 31 tests pass without NCBI credentials.

## API

```python
from download_host_genomes_robust import parse_host_field, resolve_host_token, HostToken

# Parse a complex Host field into tokens
tokens = parse_host_field("NA;GCA 900066335.1;UBA9502;Blautia obeum")
# → [HostToken('GCA_900066335.1', 'assembly_accession', 2),
#    HostToken('UBA9502', 'other', 3),
#    HostToken('Blautia obeum', 'species_name', 4)]

# Resolve a token to assembly links (requires NCBI credentials)
from assembly_resolver import AssemblyResolver
resolver = AssemblyResolver(email='user@example.org')
links = resolve_host_token(tokens[0], resolver, phage_id='p1', host_raw='NA;GCA 900066335.1;...')
# → [ResolvedAssemblyLink(assembly_accession='GCA_900066335.1', confidence=0.95, ...)]
```

## Files Changed

1. `workflow/scripts/sequences/download_host_genomes_robust.py` – Added
   `HostToken`, `ResolvedAssemblyLink`, `parse_host_field()`,
   `resolve_host_token()`, helper methods `_generate_candidates()` and
   `_build_assembly_links()`, and replaced the single-host `process_all_hosts()`
   with a multi-host pipeline.
2. `workflow/rules/hosts.smk` – Added `phage_host_candidates` and
   `phage_host_assemblies` as rule outputs.
3. `workflow/config/config.yaml` – Added `phage_host_candidates_output` and
   `phage_host_assemblies_output` config keys.
4. `tests/test_multi_host_parsing.py` – New unit tests.

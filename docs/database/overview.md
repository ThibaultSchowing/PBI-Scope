# Database Overview

PBI stores metadata and sequence assets in complementary layers.

## Current Statistics

| Metric | Value |
|--------|-------|
| Phages in DB | 1,350,644 |
| Proteins in DB | 71,971,209 |
| Hosts in DB | 5,529 |
| Phage-Host Associations | 1,241,301 |
| Phage sequences | 1,327,915 |
| Protein sequences | 71,969,191 |
| Host sequences | 5,517 |

## Core structure

- **DuckDB**: phage-centric star schema for analytical metadata queries
- **Indexed FASTA files**: phage/protein sequences and host genomes
- **Link/mapping files**: host and private-source resolution paths

## Schema (DuckDB)

```text
                     dim_proteins -------------------+
                  dim_terminators -------------------+
                  dim_anti_crispr -------------------+
             dim_virulent_factors -------------------+
       dim_transmembrane_proteins -------------------+--> fact_phages
                   dim_trna_tmrna -------------------+
dim_antimicrobial_resistance_genes ------------------+
                  dim_crispr_array ------------------+
               dataset_provenance -------------------+
          pipeline_run_provenance -------------------+
```

Host data is **not** a DuckDB dimension table. Host sequences are stored as FASTA files and linked via mapping files.

## Host/private link files

- `phage_host_candidates.csv`
- `phage_host_assemblies.csv`
- `phage_host_links.csv`
- `host_metadata.csv`
- `host_fasta_mapping.json`
- `private_phage_mapping.json` (if private sources are enabled)
- `public_data_manifest.json/.csv`
- `pipeline_run_provenance.json/.csv`

## Data sources

- Public phage data via PhageScope
- Optional private source folders from `private_data/`
- Host assemblies from NCBI RefSeq

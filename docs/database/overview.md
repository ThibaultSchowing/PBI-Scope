# Database Overview

PBI stores metadata and sequence assets in complementary layers.

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
```

Host data is **not** a DuckDB dimension table. Host sequences are stored as FASTA files and linked via mapping files.

## Host/private link files

- `phage_host_candidates.csv`
- `phage_host_assemblies.csv`
- `phage_host_links.csv`
- `host_metadata.csv`
- `host_fasta_mapping.json`
- `private_phage_mapping.json` (if private sources are enabled)

## Data sources

- Public phage data via PhageScope
- Optional private source folders from `private_data/`
- Host assemblies from NCBI RefSeq

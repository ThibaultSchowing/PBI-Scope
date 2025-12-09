# Overview 

> ⚠️ **WORK IN PROGRESS** 🔄 : This pipeline and documentation are under active development. 

# 🧬 Phage Bacteria Interaction (PBI)

A comprehensive bioinformatics pipeline for integrating, processing, and analyzing phage and host genomic data from multiple public databases already gathered within [PhageScope](https://phagescope.deepomics.org/workspace/). This pipeline creates a unified, queryable database from diverse phage data sources including GenBank, RefSeq, and PhagesDB, all already unified within PhageScope. 

The broader goal is to integrate more sources and automatize these integration as much as possible, while allowing retrieval of the host (bacteria) sequence retrieval either by getting the reference sequence or ideally having a specific strain matching a specitic phage.  

**Disclaimer** : The project has been written with obvious help from Copilot Pro and Claude Sonnet 4.5. 


## 🎯 Project Goals

The PBI pipeline addresses key challenges in phage genomics research:

- **Data Integration**: Harmonizes phage data from multiple heterogeneous sources, done here by PhageScope
- **Standardization**: Creates consistent data schemas across different databases. PhageScope is already merging heterogenous sources. Here we plan to allow for custom sources addition, via PhageScope or not, 🔄 In Progress
- **Performance**: Builds optimized analytical databases for large-scale queries
- **Reproducibility**: Provides a fully automated, version-controlled pipeline
- **Accessibility**: Generates easy-to-use databases for downstream analysis
- **Quality Assurance**: Comprehensive validation and HTML reporting

## 📊 Current Implementation Status

### ✅ **Fully Integrated Tables** (Available in Database)

The following data types are fully integrated into the DuckDB star schema:

| Table | Source CSV | Status | Row Count (approx.) | Description |
|-------|-----------|--------|---------------------|-------------|
| **`fact_phages`** | `merged_phage_metadata.csv` | ✅ Complete | 873,718 | Core phage metadata (genome size, GC content, taxonomy, host, lifestyle) |
| **`dim_proteins`** | `merged_annotated_proteins_metadata.csv` | ✅ Complete | 43,088,582 | Protein annotations, functional predictions, physicochemical properties |
| **`dim_terminators`** | `merged_transcription_terminator_metadata.csv` | ✅ Complete | 6,462,417 | Transcription terminator predictions and confidence scores |
| **`dim_anti_crispr`** | `merged_phage_anti_crispr_metadata.csv` | ✅ Complete | 307,329 | Anti-CRISPR protein predictions and sources |
| **`dim_virulent_factors`** | `merged_phage_virulent_factor_metadata.csv` | ✅ Complete | 41,609 | Virulence factor predictions aligned to VFDB |
| **`dim_transmembrane_proteins`** | `merged_phage_transmembrane_protein_metadata.csv` | ✅ Complete | 4,020,770 | Transmembrane helix predictions (TMHMM) |
| **`dim_trna_tmrna`** | `merged_phage_trna_tmrna_metadata.csv` | ✅ Complete | 702,607 | tRNA and tmRNA predictions with sequences |
| CRISPR Arrays | `` | ✅ Complete | 56,652 |
| Antimicrobial Resistance Genes | `` | ✅ Complete | 2,602 |

### 🎯 **Database Schema Overview**

The pipeline implements a **9-table star schema** with `fact_phages` as the central fact table:

```
                     dim_proteins ──┐
                  dim_terminators ──┤
                                    ├──> fact_phages (central)
                  dim_anti_crispr ──┤
             dim_virulent_factors ──┤
       dim_transmembrane_proteins ──┤
dim_antimicrobial_resistance_genes ─┤ 
                  dim_crispr_array ─┤ 
                   dim_trna_tmrna ──┘
```

All dimension tables link to `fact_phages` via **`Phage_ID`** foreign key, enabling comprehensive multi-dimensional analysis.

## 📊 Pipeline Overview

```
Raw Data Sources → Download → Merge → Validate → Optimized Database
     ↓               ↓        ↓        ↓            ↓
  PhageScope      TSV Files  Clean    Quality    DuckDB Star
  14 databases    CSV merge  Unified  Checks     Schema (7 tables)
  GenBank/RefSeq  Standard   CSVs     Reports    Indexed & Optimized
```

### 🏗️ Architecture 

The pipeline implements a **star schema** database design optimized for analytical queries:

#### **Fact Table**
- **`fact_phages`**: Central table with core phage metadata
  - Genome characteristics (length, GC content)
  - Taxonomy and classification
  - Host information
  - Lifestyle (lytic/lysogenic)
  - Source database tracking


#### **Dimension Tables**

<details>
<summary>Table details</summary>

- **`dim_proteins`**: Detailed protein information
  - Functional annotations and classifications
  - Physicochemical properties (MW, pI, stability)
  - Secondary structure predictions
  - Multi-source predictions (Prokka, Pharokka, etc.)

- **`dim_terminators`**: Transcription termination sites
  - Terminator type and location
  - Confidence scores
  - Strand orientation

- **`dim_anti_crispr`**: Anti-CRISPR defense systems
  - Protein identification
  - Source and prediction method
  - Phage-host interactions

- **`dim_virulent_factors`**: Virulence determinants
  - VFDB alignment matches
  - Pathogenicity markers

- **`dim_transmembrane_proteins`**: Membrane protein predictions
  - TMH (transmembrane helix) counts and positions
  - Signal peptide predictions
  - Topology (inside/outside/TMH regions)

- **`dim_trna_tmrna`**: Transfer RNA and tmRNA features
  - tRNA type (amino acid specificity)
  - Genomic coordinates
  - Sequences and permutation status

</details>


## 📁 Project Structure

<details>
<summary>Table details</summary>

The project is separated into: 
- Workflow: Snakemake pipeline, downloading, processing and creating the DuckDB SQL database from the PhageScope data. 
- src: Python package. Functions and co. to interrogate the database created by the pipeline
- data: all the data (temporary, raw, processed)
- doc: this very documentation (mkdocs + Github actions)
- tests: test files (TODO) 
- notebooks: for data exploration. 


```
PBI/
├── workflow/
│   ├── Snakefile                           # Main pipeline orchestration
│   ├── rules/                              # Modular pipeline rules
│   │   ├── phagescope.smk                 # Data download & preprocessing
│   │   ├── database.smk                   # Database creation & validation
│   │   └── sequences.smk                  # FASTA indexing & optimization
│   ├── scripts/                           # Processing & analysis scripts
│   │   ├── database/
│   │   │   ├── create_duckdb.py          # Database schema creation (9 tables)
│   │   │   ├── validate_db.py            # Comprehensive quality validation
│   │   │   └── optimize_db.py            # Performance optimization
│   │   ├── preprocessing/
│   │   │   └── mergers/                  # Data integration scripts
│   │   │       ├── merge_phage_metadata.py
│   │   │       ├── merge_protein_metadata.py
│   │   │       ├── merge_terminator_metadata.py
│   │   │       ├── merge_anti_crispr_metadata.py
│   │   │       ├── merge_virulent_factor_metadata.py
│   │   │       ├── merge_transmembrane_metadata.py
│   │   │       ├── merge_trna_tmrna_metadata.py
│   │   │       ├── merge_crispr_array_metadata.py        # 🆕
│   │   │       └── merge_antimicrobial_resistance_gene_metadata.py  # 🆕
│   │   ├── sequences/
│   │   │   ├── index_fasta.py            # FASTA indexing with pyfaidx
│   │   │   └── export_sequences.py       # Sequence export utilities
│   │   └── utils/
│   │       └── common.py                 # Shared utilities & helpers
│   ├── config/
│   │   └── config.yaml                   # Pipeline configuration
│   ├── envs/                             # Conda/Pixi environments
│   │   ├── pixi_base_env.yaml           # Base environment
│   │   ├── duckdb_analysis.yaml         # Analysis environment
│   │   └── sequences.yaml               # Sequence processing environment
│   ├── notebooks/                        # Analysis & exploration notebooks
│   │   ├── expl_5_TestDB.ipynb          # Database exploration
│   │   ├── sequence_retrieval_demo.ipynb # Sequence API examples
│   │   └── metadata_analysis.ipynb      # Statistical analysis
│   ├── logs/                             # Snakemake execution logs
│   └── reports/                          # HTML validation reports
│       ├── database_validation_report.html
│       ├── phage_metadata_report.html
│       ├── annotated_proteins_metadata_report.html
│       ├── transcription_terminator_metadata_report.html
│       ├── phage_anti_crispr_metadata_report.html
│       ├── phage_virulent_factor_metadata_report.html
│       ├── phage_transmembrane_protein_metadata_report.html
│       ├── phage_trna_tmrna_metadata_report.html
│       ├── crispr_array_metadata_report.html                 # 🆕
│       └── antimicrobial_resistance_gene_metadata_report.html # 🆕
│
├── src/
│   └── pbi/                              # Python package
│       ├── __init__.py                   # Package initialization
│       ├── database.py                   # Database connection utilities
│       ├── sequence_retrieval.py         # FASTA retrieval API
│       └── utils.py                      # Helper functions
│
├── data/                                 # Generated data (gitignored)
│   ├── raw/                              # Downloaded from PhageScope
│   │   ├── phage_metadata/              # 14 source databases
│   │   ├── protein_metadata/
│   │   ├── terminator_metadata/
│   │   ├── anti_crispr_metadata/
│   │   ├── virulent_factor_metadata/
│   │   ├── transmembrane_metadata/
│   │   ├── trna_tmrna_metadata/
│   │   ├── crispr_array_metadata/       # 🆕
│   │   └── amr_gene_metadata/           # 🆕
│   ├── intermediate/                     # Processing intermediates
│   │   └── merged/                       # Integrated CSVs (9 files)
│   │       ├── phage_metadata.csv
│   │       ├── protein_metadata.csv
│   │       ├── terminator_metadata.csv
│   │       ├── anti_crispr_metadata.csv
│   │       ├── virulent_factor_metadata.csv
│   │       ├── transmembrane_metadata.csv
│   │       ├── trna_tmrna_metadata.csv
│   │       ├── crispr_array_metadata.csv                # 🆕
│   │       └── antimicrobial_resistance_gene_metadata.csv # 🆕
│   └── processed/
│       ├── databases/                    # Final databases
│       │   ├── phage_database.duckdb    # Raw database (~15 GB)
│       │   └── phage_database_optimized.duckdb # Optimized (~12 GB)
│       └── sequences/                    # FASTA files with indexes
│           ├── all_phages.fasta         # All phage genomes (~40 GB)
│           ├── all_phages.fasta.fai     # pyfaidx index
│           ├── all_proteins.fasta       # All protein sequences (~60 GB)
│           └── all_proteins.fasta.fai   # pyfaidx index
│
├── docs/                                 # Documentation
│   ├── index.md                         # Documentation home
│   ├── DESCRIPTION.md                   # This file
│   ├── api-reference.md                 # API documentation
│   ├── changelog.md                     # Version history
│   ├── getting-started/
│   │   ├── installation.md              # Setup guide
│   │   ├── quickstart.md                # Quick examples
│   │   └── overview.md                  # Project overview
│   ├── user-guide/
│   │   ├── data-preparation.md          # Pipeline execution
│   │   ├── running-pbi.md               # Advanced usage
│   │   └── analyzing-results.md         # Analysis workflows
│   ├── developer-guide/
│   │   └── code-structure.md            # Architecture details
│   └── img/                             # Documentation images
│
├── tests/                                # Unit tests (future)
│   ├── test_database.py
│   ├── test_sequences.py
│   └── test_retrieval.py
│
├── notebooks/                            # User-facing notebooks
│   ├── 01_database_exploration.ipynb
│   ├── 02_sequence_retrieval.ipynb
│   └── 03_metadata_analysis.ipynb
│
├── .gitignore                           # Git ignore rules
├── README.md                            # Project overview
├── LICENSE                              # License information
├── pyproject.toml                       # Python package metadata
├── pixi.toml                            # Pixi environment config
└── setup.py                             # Package installation script
```

</details>


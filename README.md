# PBI Scraper

Phages Bacteria Interaction data scraping.

WORK IN PROGRESS - DRAFT

Future documentation in [github pages](https://thibaultschowing.github.io/PBI/).

## Summary

This library reads and merge the data from PhageScope into a queryable SQL database, accessible from Python. The first objective is to be able to simplify the access to this data and in further steps, add others data such as bacterial genomes and more detailed interactions. 

Overall the Snakemake pipeline downloads and merges the metadata into a SQL database and merges the protein fasta and phage genome fasta into two big files and create the corresonding fasta.fai index files using pyfaidx. 


## 🚀 Quick Installation (To Be Tested)

Get started with PBI in under 10 minutes!

### Prerequisites

- Linux/macOS (Windows via WSL2)
- ~50 GB free disk space (for full database)
- 8+ GB RAM recommended
- Internet connection
- Patience for the first execution

### Step-by-Step Installation

#### 1. Install Pixi

Pixi is a fast, modern package manager that handles all dependencies automatically.

```bash
# Install Pixi (one-time setup)
curl -fsSL https://pixi.sh/install.sh | bash

# Restart your shell or run:
export PATH="$HOME/.pixi/bin:$PATH"

# Verify installation
pixi --version
```

#### 2. Clone the Repository

```bash
# Clone PBI repository
git clone https://github.com/yourusername/PBI.git
cd PBI

# Check repository structure
ls -la
# Should see: workflow/, src/, data/, notebooks/, README.md, etc.
```

#### 3. Install PBI Package

```bash
# Install PBI as an editable Python package
pixi run pip install -e .

# Verify installation
pixi run python -c "import pbi; print(f'✅ PBI v{pbi.__version__} installed successfully')"
```

#### 4. Build the Database

**⚠️ Important:** The first run downloads ~40 GB of data and may take 2-6 hours depending on your connection.

```bash

# [OPTIONAL] You can use caching if you plan to modify or update the data
mkdir -p /mnt/snakemake-cache

# [OPTIONAL] You have to export this each time you restart or move this in you bashrc
export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/

# Navigate to workflow directory
cd workflow

# Run Snakemake pipeline (first run: use 2-4 cores due to I/O bottleneck), add --cache if you set up caching
pixi run snakemake --cores 4 --use-conda --printshellcmds --directory workflow --snakefile workflow/Snakefile

# For subsequent runs, you can use more cores:
# pixi run snakemake --cores all --use-conda

```

**Command Breakdown:**
- `--cores 4`: Use 4 CPU cores (adjust based on your system)
- `--use-conda`: Automatically create required conda environments
- `--printshellcmds`: Show commands being executed (useful for debugging)
- `--cache` : Use caching for intermediary files
- `--directory` : Specify the workflow directory
- `--snakefile` : Specify the Snakefile

#### 5. Start Jupyter Lab

```bash
# From project root directory
cd ..
pixi run jupyter lab

# Or specify a custom port:
# pixi run jupyter lab --port 8889
```

#### 6. Test Your Installation

Create a new notebook and run:

```python
import pbi

# Connect to database (instant with background FASTA loading)
retriever = pbi.quick_connect()

# Check database statistics
stats = retriever.get_stats()
print(f"📊 Database contains:")
print(f"   Phages: {stats['database']['phages']:,}")
print(f"   Proteins: {stats['database']['proteins']:,}")

# Query some phages
df = retriever.get_phage_sequences(
    "SELECT Phage_ID FROM fact_phages WHERE Length > 100000 LIMIT 10"
)
print(f"\n✅ Retrieved {len(df)} large phages")
```

### 🎯 Quick Command Reference

```bash
# Update database (re-run workflow for new data)
cd workflow && pixi run snakemake --cores 4

# Start Jupyter Lab
pixi run jupyter lab

# Run Python interactively
pixi run python

# Check what would be updated (dry-run)
cd workflow && pixi run snakemake -n

# Generate workflow diagram
cd workflow && pixi run snakemake --dag | dot -Tsvg > dag/workflow.svg
```

### 🐛 Troubleshooting

**Issue:** `pixi: command not found`
```bash
# Add Pixi to PATH permanently
echo 'export PATH="$HOME/.pixi/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**Issue:** Snakemake fails with "No space left on device"
```bash
# Check disk space
df -h

# Clean Snakemake cache if needed
rm -rf .snakemake/
```

**Issue:** Import error: `ModuleNotFoundError: No module named 'pbi'`
```bash
# Reinstall PBI package from project root
cd /path/to/PBI
pixi run pip install -e .
```

### 📦 What Gets Installed

- **Pixi environments**: `~/.pixi/` (~500 MB)
- **Conda packages**: `.snakemake/conda/` (~2 GB)
- **Raw data**: `data/raw/` (~40 GB compressed) - Temporary files
- **Processed data**: `data/processed/` (~50 GB)
- **Database**: `data/processed/databases/` (~15 GB)

### ⏭️ Next Steps

- Explore example notebooks in `notebooks/`
- ~~Read [Usage Guide](docs/USAGE.md) for advanced queries~~
- ~~Check [API Documentation](docs/API.md) for all available functions~~


---





---
# TBR

- 1) [PhageScope](https://phagescope.deepomics.org/) Database
- 2) [VHRdb](https://hub.pages.pasteur.fr/viralhostrangedb/api.html)
- 3) [PhageDive]()

# Pixi and Snakemake

How to and how not to. 

## Download  Snakemake pipeline with Pixi

For details check Snakemake 9.8.0 documentation and Pixi documentation. 

For details on multi-environments with Pixi check [here](https://pixi.sh/latest/tutorials/multi_environment/#lets-get-started). 


- Don't forget to run  `pixi install --environment <envname>`



# Database 1 - PhageScope

**TODO:** 

- DONE ! Adapt current files for new workflow structure (everything moved within the workflow dir)
- DONE ! Add Pixi and Snakemake files to .gitignore
- show an extract of the .toml file
- Check clustering info used by PhageScope https://github.com/soedinglab/mmseqs2/wiki#clustering

Chosen for its large number of source database, [PhageScope](https://phagescope.deepomics.org/) contains phage and protein sequences alongside multiple metadata such as virulence factor, protein annotation, anti-crispr, transmembrane protein, tRNA - mRNA or transcription terminator. Phages metadata contain the **Host species** of the phage, necessary information for further work on prediction of these interactions. 



All the data from PhageScope come from a set of 13 databases: 

- RefSeq
- Genbank
- EMBL
- DDBJ
- PhagesDB
- GVD
- GPD
- MGV
- TemPhD
- CHVD
- IGVD
- IMGVR
- GOV2
- STV

![Image from phagescope.deepomics.org](https://phagescope.deepomics.org/png/databasevis.png)
![Image from phagescope.deepomics.org](https://phagescope.deepomics.org/png/analysisvis.png)
![Image from phagescope.deepomics.org](https://phagescope.deepomics.org/png/visualization.png)



## How to 

Snakemake is launched from Pixi with `pixi run`. 

When executing for the first time **do not** use more than 2-4 cores as the I/O operations on your drive will be the bottleneck and might crash the program. 

Input, output, log, and benchmark files are considered to be relative to the working directory (**either the directory in which you have invoked Snakemake** or whatever was specified for --directory or the workdir: directive). -> from the workflow directory !


The Pixi environment needs to be exported first with `pixi workspace export conda-environment -e base envs/pixi_base_enf.yaml`

The Conda environment to use is specified within each rule (if needed) with 

```
    conda:
        "envs/pixi_base_env.yaml"
```

Cache: to use [caching](https://snakemake.readthedocs.io/en/stable/executing/caching.html), it is first needed to export snakemake cache with `export SNAKEMAKE_OUTPUT_CACHE=/mnt/snakemake-cache/` (create the destination directory first). After every startup, or set the environment variable in the .bashrc file.


- **Current command:** `pixi run snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --notemp --cores 4 `
    - **DAG Option (path relative to bash location)**`--dag | dot -Tsvg > workflow/dag/dag.svg`

- **Install pbi**: to install pbi use the command `pixi run pip install -e .` in the root directory. 

To remove the temporary files after execution, use --delete-temp-output. Has to be done separately  (to be verified). In the mean time, the temp() option was removed from the intermediairy files as it takes too long to regenerage when modifying the script.:

- pixi run snakemake --delete-temp-output



```
--delete-temp-output


Remove all temporary files generated by the workflow. Use together with –dry-run to list files without actually deleting anything. Note that this will not recurse into subworkflows.
```

# Database 2 - viralhostrangedb

It contains interactions only but no sequences. The database webpage is not very userfriendly but a good documentation is written [here](https://hub.pages.pasteur.fr/viralhostrangedb/) gives info about the API. 

Data from [VHRdb](https://hub.pages.pasteur.fr/viralhostrangedb/api.html) consist of references to phages from different sources, joined to hosts of different souces. The interactions are described as being: no-data, 0: no infection, 1: intermediate and 2: infection. 

Exploration and preparatory code in expl_3 notebook. 

**CURRENT STATE**: the identifiers do not allow for an easy phage sequence retrieval, at least for now. More investigation on the different souces are needed but there are chances that every source has to be investigated separately in order to retrieve the sequences, if they are publicly available. 


Notes: 
- check phagedive for additionnal info on HER collection 


# Database 3 - PhageDive

It seems that [Phagedive](https://phagedive.dsmz.de/advsearch) contains similar information as VRHdb however improved with additional data such as culture environment, sequence (link), etc. It can be of interest in order to explore specific strains and see e.g. where are the HER collection sequences stored (accession number). 

# Database 4 - 




# Annexe

Here's a small list of temporary files from Phagescope, just so you can check ! Feel free to take a look at the DAG figures in the dag/ folder to visualize the phagescope files. Some of the temporary files logic might need to be redone (.extraction_done). 

## Phagescope Temporary files

```
Deleting data/intermediate_csv/phage_metadata/RefSeq_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/Genbank_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/EMBL_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/DDBJ_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/PhagesDB_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/GVD_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/GPD_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/MGV_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/TemPhD_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/CHVD_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/IGVD_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/IMGVR_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/GOV2_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_metadata/STV_Phage_Metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/RefSeq_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/Genbank_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/EMBL_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/DDBJ_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/PhagesDB_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/GVD_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/GPD_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/MGV_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/TemPhD_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/CHVD_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/IGVD_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/IMGVR_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/GOV2_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/annotated_proteins_metadata/STV_Annotated_Proteins_metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/RefSeq_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/Genbank_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/EMBL_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/DDBJ_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/PhagesDB_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/GVD_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/GPD_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/MGV_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/TemPhD_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/CHVD_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/IGVD_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/GOV2_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/transcription_terminator_metadata/STV_Phage_Transcription_Terminator_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/RefSeq_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/Genbank_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/EMBL_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/DDBJ_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/PhagesDB_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/GVD_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/GPD_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/MGV_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/TemPhD_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/CHVD_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/IGVD_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/IMGVR_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/GOV2_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_trna_tmrna_metadata/STV_Phage_tRNA_tmRNA_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/RefSeq_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/Genbank_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/EMBL_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/DDBJ_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/PhagesDB_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/GVD_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/GPD_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/MGV_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/CHVD_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/IGVD_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/IMGVR_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/GOV2_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_anti_crispr_metadata/STV_Phage_AntiCRISPR_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/RefSeq_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/Genbank_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/EMBL_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/DDBJ_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/GVD_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/GPD_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/MGV_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/TemPhD_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/CHVD_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/IGVD_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_virulent_factor_metadata/GOV2_Phage_Virulent_Factor_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/RefSeq_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/Genbank_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/EMBL_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/DDBJ_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/PhagesDB_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/GVD_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/GPD_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/MGV_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/TemPhD_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/CHVD_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/IGVD_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/GOV2_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/intermediate_csv/phage_transmembrane_protein_metadata/STV_Phage_Transmembrane_Protein_Metadata_URL.tsv
Deleting data/protein_fasta/Genbank/.extraction_done
Deleting data/protein_fasta_compressed/Genbank.tar.gz
Deleting data/protein_fasta/RefSeq/.extraction_done
Deleting data/protein_fasta_compressed/RefSeq.tar.gz
Deleting data/protein_fasta/DDBJ/.extraction_done
Deleting data/protein_fasta_compressed/DDBJ.tar.gz
Deleting data/protein_fasta/EMBL/.extraction_done
Deleting data/protein_fasta_compressed/EMBL.tar.gz
Deleting data/protein_fasta/PhagesDB/.extraction_done
Deleting data/protein_fasta_compressed/PhagesDB.tar.gz
Deleting data/protein_fasta/GPD/.extraction_done
Deleting data/protein_fasta_compressed/GPD.tar.gz
Deleting data/protein_fasta/GVD/.extraction_done
Deleting data/protein_fasta_compressed/GVD.tar.gz
Deleting data/protein_fasta/MGV/.extraction_done
Deleting data/protein_fasta_compressed/MGV.tar.gz
Deleting data/protein_fasta/TemPhD/.extraction_done
Deleting data/protein_fasta_compressed/TemPhD.tar.gz
Deleting data/protein_fasta/CHVD/.extraction_done
Deleting data/protein_fasta_compressed/CHVD.tar.gz
Deleting data/protein_fasta/IGVD/.extraction_done
Deleting data/protein_fasta_compressed/IGVD.tar.gz
Deleting data/protein_fasta/GOV2/.extraction_done
Deleting data/protein_fasta_compressed/GOV2.tar.gz
Deleting data/protein_fasta/STV/.extraction_done
Deleting data/protein_fasta_compressed/STV.tar.gz
Deleting data/phage_fasta/Genbank/.extraction_done
Deleting data/phage_fasta_compressed/Genbank.tar.gz
Deleting data/phage_fasta/RefSeq/.extraction_done
Deleting data/phage_fasta_compressed/RefSeq.tar.gz
Deleting data/phage_fasta/DDBJ/.extraction_done
Deleting data/phage_fasta_compressed/DDBJ.tar.gz
Deleting data/phage_fasta/EMBL/.extraction_done
Deleting data/phage_fasta_compressed/EMBL.tar.gz
Deleting data/phage_fasta/PhagesDB/.extraction_done
Deleting data/phage_fasta_compressed/PhagesDB.tar.gz
Deleting data/phage_fasta/GPD/.extraction_done
Deleting data/phage_fasta_compressed/GPD.tar.gz
Deleting data/phage_fasta/GVD/.extraction_done
Deleting data/phage_fasta_compressed/GVD.tar.gz
Deleting data/phage_fasta/MGV/.extraction_done
Deleting data/phage_fasta_compressed/MGV.tar.gz
Deleting data/phage_fasta/TemPhD/.extraction_done
Deleting data/phage_fasta_compressed/TemPhD.tar.gz
Deleting data/phage_fasta/CHVD/.extraction_done
Deleting data/phage_fasta_compressed/CHVD.tar.gz
Deleting data/phage_fasta/IGVD/.extraction_done
Deleting data/phage_fasta_compressed/IGVD.tar.gz
Deleting data/phage_fasta/IMGVR/.extraction_done
Deleting data/phage_fasta_compressed/IMGVR.tar.gz
Deleting data/phage_fasta/GOV2/.extraction_done
Deleting data/phage_fasta_compressed/GOV2.tar.gz
Deleting data/phage_fasta/STV/.extraction_done
Deleting data/phage_fasta_compressed/STV.tar.gz
```

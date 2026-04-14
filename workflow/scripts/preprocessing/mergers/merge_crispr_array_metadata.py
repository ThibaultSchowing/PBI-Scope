#!/usr/bin/env python

import sys
print(f"Using python from: {sys.executable}")
import pandas as pd
import numpy as np  
import os
import logging
import csv
from pathlib import Path
logging.basicConfig(level=logging.INFO)

sys.path.append('scripts')
import utils
from schema_contracts import load_contract, normalize_df_schema

# Snakemake inputs and outputs
inputs = snakemake.input
output = snakemake.output[0]

COLUMNS_LIST = [
    "Phage_ID", "Duplicated_Spacers", "CRISPR_ID", "CRISPR_Start", "CRISPR_End",
    "CRISPR_Length", "Potential_Orientation (AT%)", "CRISPRDirection", "Consensus_Repeat",
    "Repeat_ID (CRISPRdb)", "Nb_CRISPRs_with_same_Repeat (CRISPRdb)", "Repeat_Length", "Spacers_Nb",
    "Mean_size_Spacers", "Standard_Deviation_Spacers", "Nb_Repeats_matching_Consensus",
    "Ratio_Repeats_match/TotalRepeat", "Conservation_Repeats (% identity)", "EBcons_Repeats",
    "Conservation_Spacers (% identity)", "EBcons_Spacers", "Repeat_Length_plus_mean_size_Spacers",
    "Ratio_Repeat/mean_Spacers_Length", "CRISPR_found_in_DB (if sequence IDs are similar)",
    "Evidence_Level", "Source_DB"
]

NUMERICAL_COLUMNS = ["Duplicated_Spacers", "CRISPR_Start", "CRISPR_End", "CRISPR_Length", "Repeat_Length", "Spacers_Nb", "Mean_size_Spacers", "Standard_Deviation_Spacers", "Nb_Repeats_matching_Consensus", "Ratio_Repeats_match/TotalRepeat", "Conservation_Repeats (% identity)", "EBcons_Repeats", "Conservation_Spacers (% identity)", "EBcons_Spacers", "Repeat_Length_plus_mean_size_Spacers", "Ratio_Repeat/mean_Spacers_Length", "CRISPR_found_in_DB (if sequence IDs are similar)", "Evidence_Level"]

STRING_COLUMNS = ["Phage_ID", "CRISPR_ID", "Potential_Orientation (AT%)", "CRISPRDirection", "Consensus_Repeat", "Repeat_ID (CRISPRdb)", "Source_DB"]
CONTRACT = load_contract(Path(__file__).resolve().parents[3] / "schemas" / "crispr_array_metadata_merged.yaml")

# List of DataFrames
dfs = []

# For each input file (all databases - From PhageScope)
for infile in inputs:
    logging.info(f"Processing file: {infile}")

    # Check if file is empty or invalid
    if utils.is_file_empty_or_invalid(infile):
        logging.warning(f"File {infile} is empty or invalid. Skipping.")
        continue
    
    df = pd.read_csv(infile, sep="\t", quoting=csv.QUOTE_NONNUMERIC)

    logging.info(f"We have {len(df.columns)} columns in {infile}: {df.columns.tolist()}")
    print(f"We have {len(df.columns)} columns in {infile}: {df.columns.tolist()}")
    
    if "Source_DB" not in df.columns:
        source_name = os.path.basename(infile).split("_")[0]
        df["Source_DB"] = source_name

    df, _ = normalize_df_schema(df, CONTRACT, dataset_name="crispr_array_metadata", logger=logging.getLogger(__name__))

    # Ensure all expected columns are named correctly 
    #df = utils.rename_columns(df, infile)

    # Convert numerical columns to numeric types
    df = utils.convert_numerical_columns(df, NUMERICAL_COLUMNS)

    dfs.append(df)

if dfs:
    final_schema_df = pd.concat([df.head(0) for df in dfs], ignore_index=True, sort=False)
    final_schema_df, _ = normalize_df_schema(
        final_schema_df,
        CONTRACT,
        dataset_name="crispr_array_metadata_merged",
        logger=logging.getLogger(__name__),
    )
    final_columns = list(final_schema_df.columns)
    dfs = [df.reindex(columns=final_columns) for df in dfs]

# Crée le dossier output si besoin
os.makedirs(os.path.dirname(output), exist_ok=True)

# Use chunked merge to avoid OOM errors
total_rows = utils.merge_dataframes_chunked(dfs, output)

logging.info(f"Merged {len(inputs)} files into {output} with {total_rows} total rows")

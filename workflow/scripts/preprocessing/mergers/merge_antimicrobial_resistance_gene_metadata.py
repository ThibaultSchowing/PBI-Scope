#!.pixi/envs/default/bin/python

import sys
print(f"Using python from: {sys.executable}")
import pandas as pd
import numpy as np  
import os
import logging
logging.basicConfig(level=logging.INFO)

sys.path.append('scripts')
import utils

# Snakemake inputs and outputs
inputs = snakemake.input
output = snakemake.output[0]

COLUMNS_LIST = ["Protein_id", "Aligned_Protein_in_CARD", "Phage_id"	, "Phage_Source"]

NUMERICAL_COLUMNS = []

STRING_COLUMNS = ["Protein_id", "Aligned_Protein_in_CARD", "Phage_id"	, "Phage_Source"]

# List of DataFrames
dfs = []

# For each input file (all databases - From PhageScope)
for infile in inputs:
    logging.info(f"Processing file: {infile}")

    # Check if file is empty or invalid
    if utils.is_file_empty_or_invalid(infile):
        logging.warning(f"File {infile} is empty or invalid. Skipping.")
        continue
    
    df = pd.read_csv(infile, sep="\t")
    
    # Ensure all expected columns are named correctly 
    df = utils.rename_columns(df, infile)

    # Validate that the DataFrame contains all expected columns
    if not utils.validate_columns(df, COLUMNS_LIST):
        logging.warning(f"File {infile} is missing expected columns. Skipping.")
        

    # Convert numerical columns to numeric types
    df = utils.convert_numerical_columns(df, NUMERICAL_COLUMNS)

    dfs.append(df)

# concat all the dataframes into one
merged_df = pd.concat(dfs, ignore_index=True)

# Crée le dossier output si besoin
os.makedirs(os.path.dirname(output), exist_ok=True)

# Save
merged_df.to_csv(output, index=False)

print(f"[INFO] Merged {len(inputs)} files into {output} with shape {merged_df.shape}")

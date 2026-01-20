#!/usr/bin/env python

import sys
print(f"Using python from: {sys.executable}")
import pandas as pd
import numpy as np  
import os
import logging
import csv
logging.basicConfig(level=logging.INFO)

sys.path.append('scripts')
import utils

# Snakemake inputs and outputs
inputs = snakemake.input
output = snakemake.output[0]

COLUMNS_LIST = ["t(m)RNA_ID", "Source", "t(m)RNA", "Start", "Stop", "Strand", "Length", "Permuted", "Sequence", "Phage_ID", "Phage_Source", "Source_DB"]

NUMERICAL_COLUMNS = ["Start", "Stop", "Length"]

STRING_COLUMNS = ["t(m)RNA_ID", "Source", "t(m)RNA", "Strand", "Permuted", "Sequence", "Phage_ID", "Phage_Source", "Source_DB"]
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

    # Validate and reorder columns to match expected schema
    df = utils.validate_columns(df, COLUMNS_LIST)
    
    # Ensure all expected columns are named correctly
    df = utils.rename_columns(df, infile)

    # Convert numerical columns to numeric types
    df = utils.convert_numerical_columns(df, NUMERICAL_COLUMNS)

    dfs.append(df)

# Crée le dossier output si besoin
os.makedirs(os.path.dirname(output), exist_ok=True)

# Use chunked merge to avoid OOM errors
total_rows = utils.merge_dataframes_chunked(dfs, output)

print(f"[INFO] Merged {len(inputs)} files into {output} with {total_rows} total rows")


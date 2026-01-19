#!/usr/bin/env python

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

COLUMNS_LIST = ['Phage_ID', 'Protein_source', 'Function_prediction_source', 'Start',
       'Stop', 'Strand', 'Protein_ID', 'Product', 'Protein_classification',
       'Molecular_weight', 'Aromaticity', 'Instability_index',
       'Isoelectric_point', 'Helix_fraction', 'Turn_fraction',
       'Sheet_fraction', 'Reduced_coefficient', 'Oxidized_coefficient', 'Source_DB']

NUMERICAL_COLUMNS = ['Start', 'Stop', 'Molecular_weight', 'Aromaticity',
       'Instability_index', 'Isoelectric_point', 'Helix_fraction', 'Turn_fraction',
       'Sheet_fraction', 'Reduced_coefficient', 'Oxidized_coefficient']

STRING_COLUMNS = ['Phage_ID', 'Protein_source', 'Function_prediction_source',
       'Strand', 'Protein_ID', 'Product', 'Protein_classification',
       'Source_DB']

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
    # TODO: instead of skipping, we could add missing columns with NaN values
    if not utils.validate_columns(df, COLUMNS_LIST):
        logging.warning(f"File {infile} is missing expected columns. Skipping.")
        continue

    # Convert numerical columns to numeric types
    df = utils.convert_numerical_columns(df, NUMERICAL_COLUMNS)

    dfs.append(df)

# Create the output directory if needed
os.makedirs(os.path.dirname(output), exist_ok=True)

# Use chunked merge to avoid OOM errors
total_rows = utils.merge_dataframes_chunked(dfs, output)

print(f"[INFO] Merged {len(inputs)} files into {output} with {total_rows} total rows")

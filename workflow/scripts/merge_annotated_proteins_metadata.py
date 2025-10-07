#!.pixi/envs/default/bin/python

import sys
print(f"Using python from: {sys.executable}")
import pandas as pd
import numpy as np  
import os
import logging

logging.basicConfig(level=logging.INFO)

import utils

# Snakemake inputs and outputs
inputs = snakemake.input
output = snakemake.output[0]

COLUMNS_LIST = ['Phage_ID', 'Protein_source', 'Function_prediction_source', 'Start',
       'Stop', 'Strand', 'Protein_ID', 'Product', 'Protein_classification',
       'Molecular_weight', 'Aromaticity', 'Instability_index',
       'Isoelectric_point', 'Helix_fraction', 'Turn_fraction',
       'Sheet_fraction', 'Reduced_coefficient', 'Oxidized_coefficient',
       'Phage_source', 'Function_Prediction_source']

NUMERICAL_COLUMNS = ['Start', 'Stop', 'Molecular_weight', 'Aromaticity',
       'Instability_index', 'Isoelectric_point', 'Helix_fraction', 'Turn_fraction',
       'Sheet_fraction', 'Reduced_coefficient', 'Oxidized_coefficient']

STRING_COLUMNS = ['Phage_ID', 'Protein_source', 'Function_prediction_source',
       'Strand', 'Protein_ID', 'Product', 'Protein_classification',
       'Phage_source', 'Function_Prediction_source']

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
    

    # Rename column Phage_Source and Phage_id to Phage_source and Phage_ID if needed
    if 'Phage_Source' in df.columns:
        df = df.rename(columns={'Phage_Source': 'Phage_source'})
        logging.info(f"Renamed 'Phage_Source' to 'Phage_source' in {infile}")
    if 'Phage_id' in df.columns:
        df = df.rename(columns={'Phage_id': 'Phage_ID'})
        logging.info(f"Renamed 'Phage_id' to 'Phage_ID' in {infile}")
    
    # Add 'Phage_source' column if it doesn't exist
    if 'Phage_source' not in df.columns:
        source_name = os.path.basename(infile).split("_")[0]
        df['Phage_source'] = source_name
        logging.info(f"Added 'Phage_source' column to {infile} with value '{source_name}'")
    
    # Replace "-" with NA in numerical columns

    for i, col in enumerate(NUMERICAL_COLUMNS):
        logging.info(f"Processing numerical column: {col}")
        try:
            logging.info(f"Formating column {i} ({col}) to numeric in {infile}")
            
            # Replace "-" with NaN and convert to numeric
            df[col] = pd.to_numeric(df[col].replace("-", np.nan), errors='coerce')
            # Replace NaN with np.nan (just to be sure)
            df[col] = df[col].replace("NaN", np.nan)
            
        except Exception as e:
            logging.error(f"Error converting column {col} in {infile}: {str(e)}")
            # Continue processing other columns
            continue

    dfs.append(df)
    



# Concatène tous les DataFrames
merged_df = pd.concat(dfs, ignore_index=True)

# Crée le dossier output si besoin
os.makedirs(os.path.dirname(output), exist_ok=True)

# Sauvegarde
merged_df.to_csv(output, index=False)

print(f"[INFO] Merged {len(inputs)} files into {output} with shape {merged_df.shape}")

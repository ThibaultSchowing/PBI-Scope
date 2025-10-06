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

# Liste des DataFrames
dfs = []

for infile in inputs:
    print(f"Processing file: {infile}")

    if utils.is_file_empty_or_invalid(infile):
        print(f"[WARNING] File {infile} is empty or invalid. Skipping.")
        logging.warning(f"File {infile} is empty or invalid. Skipping.")
        continue
    
    df = pd.read_csv(infile, sep="\t")
    print(f"[INFO] Processing file: {infile} with shape {df.shape}")
    #print(f"Head of {infile}:\n{df.head()}")

    # Rename column Phage_Source and Phage_id to Phage_source and Phage_ID if needed
    if 'Phage_Source' in df.columns:
        df = df.rename(columns={'Phage_Source': 'Phage_source'})
    if 'Phage_id' in df.columns:
        df = df.rename(columns={'Phage_id': 'Phage_ID'})
    
    # Ajoute la colonne 'Phage_source' si elle n'existe pas
    if 'Phage_source' not in df.columns:
        source_name = os.path.basename(infile).split("_")[0]
        # Log info the source_name
        #logging.info(f"Processing {infile} with source name '{source_name}'")
        df['Phage_source'] = source_name
        logging.info(f"Added 'Phage_source' column to {infile} with value '{source_name}'")
    
    # Replace "-" with NA in columns 9 and 11 (causes problems with multi types)
    cols_to_numeric = [df.columns[9], df.columns[11]]

    for col in cols_to_numeric:
        df[col] = pd.to_numeric(df[col].replace("-", np.nan), errors='coerce')

    dfs.append(df)
    



# Concatène tous les DataFrames
merged_df = pd.concat(dfs, ignore_index=True)

# Crée le dossier output si besoin
os.makedirs(os.path.dirname(output), exist_ok=True)

# Sauvegarde
merged_df.to_csv(output, index=False)

print(f"[INFO] Merged {len(inputs)} files into {output} with shape {merged_df.shape}")

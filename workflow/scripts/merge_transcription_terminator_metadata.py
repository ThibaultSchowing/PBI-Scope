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

    # Rename column Phage_Source and Phage_id to Phage_source and Phage_ID if needed
    if 'Phage_Source' in df.columns:
        df = df.rename(columns={'Phage_Source': 'Phage_source'})
    if 'Phage_id' in df.columns:
        df = df.rename(columns={'Phage_id': 'Phage_ID'})

    
    # Ajoute la colonne 'Phage_source' si elle n'existe pas
    if 'Phage_source' not in df.columns:
        source_name = os.path.basename(infile).split("_")[0]
        print(f"Source name derived from file: {source_name}")
        # Log info the source_name
        logging.info(f"Processing {infile} with source name '{source_name}'")
        df['Phage_source'] = source_name
        logging.info(f"Added 'Phage_source' column to {infile} with value '{source_name}'")

    dfs.append(df)
    

# Concatène tous les DataFrames
logging.info(f"Merging {len(dfs)} DataFrames")
merged_df = pd.concat(dfs, ignore_index=True)
logging.info(f"Merged DataFrame shape: {merged_df.shape}")

# Crée le dossier output si besoin
logging.info(f"Creating output directory if it does not exist: {os.path.dirname(output)}")
os.makedirs(os.path.dirname(output), exist_ok=True)

# Sauvegarde
logging.info(f"Saving merged DataFrame to {output}")
merged_df.to_csv(output, index=False)

print(f"[INFO] Merged {len(inputs)} files into {output} with shape {merged_df.shape}")

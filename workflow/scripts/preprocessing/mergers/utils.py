#!.pixi/envs/default/bin/python

import pandas as pd
import numpy as np
import logging
import os


def is_file_empty_or_invalid(filepath):
    """Check if file is empty or has no data to parse"""
    try:
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return True
        
        # Try to read first few lines to check if it has valid data
        with open(filepath, 'r') as f:
            first_line = f.readline().strip()
            if not first_line:  # Empty first line
                return True
            
        # Try to read with pandas to see if it has columns
        df_test = pd.read_csv(filepath, sep="\t", nrows=0)
        return len(df_test.columns) == 0
        
    except Exception as e:
        logging.warning(f"File {filepath} appears to be invalid: {e}")
        return True

def validate_columns(df, expected_columns):
    '''Validate that the DataFrame contains all expected columns.'''
    missing_cols = [col for col in expected_columns if col not in df.columns]
    if missing_cols:
        logging.warning(f"Missing columns: {missing_cols}")
        return False
    return True

# TODO : create function that takes list of numerical colums and convert them to numeric with logging
def convert_numerical_columns(df, cols):
    '''Convert specified columns to numeric, coercing errors to NaN (np.nan).'''
    for col in cols:
        logging.info(f"Formating column {col} to numeric")
        try:
            df[col] = pd.to_numeric(df[col].replace("-", np.nan), errors='coerce')
            df[col] = df[col].replace("NaN", np.nan)
        except Exception as e:
            logging.warning(f"Failed to convert column {col} to numeric: {e}")
            continue

    return df

def rename_columns(df, infile):
    '''Rename columns in the DataFrame to ensure consistency.
    This function checks for common misnamings and corrects them.
    It also adds a 'Source_DB' column if it doesn't exist.
    
    '''

    # Rename column Phage_Source and Phage_id to Phage_source and Phage_ID if needed
    if 'Phage_Source' in df.columns:
        df = df.rename(columns={'Phage_Source': 'Phage_source'})
        logging.info(f"Renamed 'Phage_Source' to 'Phage_source' in {infile}")
    if 'Phage_id' in df.columns:
        df = df.rename(columns={'Phage_id': 'Phage_ID'})
        logging.info(f"Renamed 'Phage_id' to 'Phage_ID' in {infile}")
    if 'Protein_id' in df.columns:
        df = df.rename(columns={'Protein_id': 'Protein_ID'})
        logging.info(f"Renamed 'Protein_id' to 'Protein_ID' in {infile}")

    if 'Source_DB' not in df.columns:
        source_name = os.path.basename(infile).split("_")[0]
        df['Source_DB'] = source_name
        logging.info(f"Added 'Source_DB' column to {infile} with value '{source_name}'")

    return df
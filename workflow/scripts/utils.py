#!.pixi/envs/default/bin/python

import pandas as pd
import sys
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
    

# TODO : create function that takes list of numerical colums and convert them to numeric with logging
def convert_numerical_columns(df, cols):
    for col in cols:
        logging.info(f"Formating column {col} to numeric")
        df[col] = pd.to_numeric(df[col].replace("-", np.nan), errors='coerce')
        df[col] = df[col].replace("NaN", np.nan)
    return df
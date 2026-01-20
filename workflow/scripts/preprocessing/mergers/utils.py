#!/usr/bin/env python

import pandas as pd
import numpy as np
import logging
import os
import csv


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
        df_test = pd.read_csv(filepath, sep="\t", nrows=0, quoting=csv.QUOTE_NONNUMERIC)
        return len(df_test.columns) == 0
        
    except Exception as e:
        logging.warning(f"File {filepath} appears to be invalid: {e}")
        return True

def validate_columns(df, expected_columns):
    """Validate that the DataFrame contains all expected columns.
    Adds missing columns with NaN values and reorders to match expected order.
    
    Args:
        df: Input DataFrame
        expected_columns: List of expected column names in desired order
    
    Returns:
        Modified DataFrame with columns in the expected order
    """
    missing_cols = [col for col in expected_columns if col not in df.columns]
    
    # Add missing columns with NaN values
    for col in missing_cols:
        df[col] = np.nan
        logging.info(f"Added missing column '{col}' with NaN values")
    
    # Check for extra columns not in expected list
    extra_cols = [col for col in df.columns if col not in expected_columns]
    if extra_cols:
        logging.warning(f"Found extra columns not in expected list: {extra_cols}")
    
    # Reorder to match expected columns, keeping any extra columns at the end
    ordered_cols = [col for col in expected_columns if col in df.columns]
    ordered_cols.extend(extra_cols)
    
    # Return dataframe with reordered columns
    return df[ordered_cols]

# TODO : create function that takes list of numerical colums and convert them to numeric with logging
def convert_numerical_columns(df, cols):
    """Convert specified columns to numeric, coercing errors to NaN (np.nan)."""
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
    """Rename columns in the DataFrame to ensure consistency.
    This function checks for common misnamings and corrects them.
    It also adds a 'Source_DB' column if it doesn't exist.
    
    """

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


def merge_dataframes_chunked(dfs, output_file):
    """Merge multiple DataFrames by writing them in chunks to avoid OOM errors.
    
    This function writes DataFrames to CSV file one by one in append mode,
    which avoids loading all data into memory at once.
    
    Args:
        dfs: List of pandas DataFrames to merge
        output_file: Path to output CSV file
    
    Returns:
        Total number of rows written
    """
    if not dfs:
        logging.warning("No dataframes to merge")
        # Create empty file
        with open(output_file, 'w', encoding='utf-8'):
            pass
        return 0
    
    # Ensure all dataframes have the same column order as the first one
    # This prevents CSV tokenization errors when reading in chunks
    first_columns = list(dfs[0].columns)
    logging.info(f"Ensuring all dataframes have consistent column order: {first_columns}")
    
    for i, df in enumerate(dfs):
        # Use validate_columns to ensure consistent column order and add missing columns
        # Note: validate_columns keeps extra columns at the end, so we need to filter them
        validated_df = validate_columns(df, first_columns)
        
        # Keep only the columns from the first dataframe (remove any extras)
        dfs[i] = validated_df[first_columns]
    
    total_rows = 0
    
    # Write first dataframe with header
    first_df = dfs[0]
    logging.info(f"Writing first dataframe with {len(first_df)} rows and header")
    first_df.to_csv(output_file, index=False, mode='w', encoding='utf-8', quoting=csv.QUOTE_NONNUMERIC)
    total_rows += len(first_df)
    
    # Append remaining dataframes without header
    for i, df in enumerate(dfs[1:], start=2):
        logging.info(f"Appending dataframe {i}/{len(dfs)} with {len(df)} rows")
        df.to_csv(output_file, index=False, mode='a', header=False, encoding='utf-8', quoting=csv.QUOTE_NONNUMERIC)
        total_rows += len(df)
    
    logging.info(f"Total rows written: {total_rows}")
    return total_rows
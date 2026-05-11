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

provider_config = snakemake.config.get("public_data_provider", {})
PROVIDER_NAME = provider_config.get("name", "PhageScope")
PROVIDER_RELEASE = provider_config.get("release", "")
PROVIDER_SNAPSHOT_DATE = provider_config.get("snapshot_date", "")
PROVIDER_SCHEMA_PROFILE = provider_config.get("schema_profile", "")

COLUMNS_LIST = ["Phage_ID", "Length", "GC_content", "Taxonomy", "Completeness", 
                "Host", "Lifestyle", "Cluster", "Subcluster", "Source_DB",
                "Provider_Name", "Provider_Release", "Provider_Snapshot_Date",
                "Provider_Schema_Profile", "Input_Source_Key", "Input_File", "Input_Retrieved_At"]

NUMERICAL_COLUMNS = ["Length", "GC_content"]
STRING_COLUMNS = ["Phage_ID", "Taxonomy", "Completeness", "Host", "Lifestyle", "Cluster", "Subcluster", "Source_DB",
                  "Provider_Name", "Provider_Release", "Provider_Snapshot_Date", "Provider_Schema_Profile",
                  "Input_Source_Key", "Input_File", "Input_Retrieved_At"]
CONTRACT = load_contract(Path(__file__).resolve().parents[3] / "schemas" / "phage_metadata_merged.yaml")


def _load_retrieved_at_from_sidecar(tsv_path: str) -> str:
    sidecar_path = str(Path(tsv_path).with_suffix(".provenance.json"))
    if not os.path.exists(sidecar_path):
        return ""
    try:
        import json

        with open(sidecar_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle) or {}
        return str(payload.get("retrieved_at", "")).strip()
    except Exception as exc:
        logging.warning(f"Could not read sidecar {sidecar_path}: {exc}")
        return ""

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

    if "Source_DB" not in df.columns:
        source_name = os.path.basename(infile).split("_")[0]
        df["Source_DB"] = source_name

    source_key = Path(infile).stem
    df["Provider_Name"] = PROVIDER_NAME
    df["Provider_Release"] = PROVIDER_RELEASE
    df["Provider_Snapshot_Date"] = PROVIDER_SNAPSHOT_DATE
    df["Provider_Schema_Profile"] = PROVIDER_SCHEMA_PROFILE
    df["Input_Source_Key"] = source_key
    df["Input_File"] = os.path.basename(infile)
    df["Input_Retrieved_At"] = _load_retrieved_at_from_sidecar(infile)

    df, _ = normalize_df_schema(df, CONTRACT, dataset_name="phage_metadata", logger=logging.getLogger(__name__))
    
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
        dataset_name="phage_metadata_merged",
        logger=logging.getLogger(__name__),
    )
    final_columns = list(final_schema_df.columns)
    dfs = [df.reindex(columns=final_columns) for df in dfs]

# Crée le dossier output si besoin
os.makedirs(os.path.dirname(output), exist_ok=True)

# Use chunked merge to avoid OOM errors
total_rows = utils.merge_dataframes_chunked(dfs, output)

print(f"[INFO] Merged {len(inputs)} files into {output} with {total_rows} total rows")

#!/usr/bin/env python3
"""
Create a combined per-phage host status report

Joins four upstream CSVs into a single DataFrame-loadable report that
tracks each step of the host-genome pipeline for every (Phage, Host-token)
pair:

1. ``phage_host_candidates.csv``  – one row per (Phage_ID, parsed Host token)
2. ``phage_host_assemblies.csv``  – resolved assembly links
3. ``assembly_metadata.csv``      – download status per assembly
4. ``host_fasta_qc_log.csv``      – QC + index status per host FASTA

Output columns allow answering questions like:

* For all phages, how many have at least one host with a resolved assembly?
* Of those hosts, how many were downloaded successfully?
* Of the downloaded hosts, how many were indexed?
* Which hosts were rejected due to duplicate FASTA headers?

The output CSV has one row per ``(Phage_ID, Host_Token)`` pair.
"""

import logging
import os
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Shared logging helper
# ---------------------------------------------------------------------------


def _setup_logging(log_file: str, also_stderr: bool = True) -> None:
    """Route root-logger output to *log_file* and optionally stderr."""
    try:
        _common = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'common')
        if _common not in sys.path:
            sys.path.insert(0, _common)
        from logging_utils import setup_logging  # noqa: PLC0415
        setup_logging(log_file, also_stderr=also_stderr)
    except Exception:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.INFO)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        root.addHandler(fh)
        if also_stderr:
            sh = logging.StreamHandler(sys.stderr)
            sh.setFormatter(fmt)
            root.addHandler(sh)


def create_host_status_report(
    candidates_csv: str,
    assemblies_csv: str,
    assembly_metadata_csv: str,
    qc_log_csv: str,
    output_csv: str,
) -> pd.DataFrame:
    """Join the four upstream tables into a combined status report.

    Args:
        candidates_csv:         phage_host_candidates.csv
        assemblies_csv:         phage_host_assemblies.csv
        assembly_metadata_csv:  assembly_metadata.csv
        qc_log_csv:             host_fasta_qc_log.csv
        output_csv:             path for the output report CSV

    Returns:
        The merged DataFrame (also written to *output_csv*).
    """
    logging.info("📋 Loading upstream tables…")

    # -- Candidates: one row per (Phage_ID, token); includes unresolved phages --
    candidates = pd.read_csv(candidates_csv)
    logging.info(f"   candidates: {len(candidates)} rows")

    # -- Assembly links: resolved tokens only -----------------------------------
    assemblies = pd.read_csv(assemblies_csv) if Path(assemblies_csv).exists() else pd.DataFrame()
    logging.info(f"   assemblies: {len(assemblies)} rows")

    # -- Assembly metadata: download status per assembly -----------------------
    asm_meta = pd.read_csv(assembly_metadata_csv) if Path(assembly_metadata_csv).exists() else pd.DataFrame()
    logging.info(f"   assembly_metadata: {len(asm_meta)} rows")

    # -- QC log: index + FASTA quality per host FASTA --------------------------
    qc_log = pd.read_csv(qc_log_csv) if Path(qc_log_csv).exists() else pd.DataFrame()
    logging.info(f"   qc_log: {len(qc_log)} rows")

    # --------------------------------------------------------------------------
    # Merge 1: candidates ← assemblies  (left join on Phage_ID + Host_Token)
    # Rows in candidates with no resolved assembly get NaN in assembly columns.
    # --------------------------------------------------------------------------
    if not assemblies.empty:
        # Keep only the best-ranked assembly per (Phage_ID, Host_Token)
        best_assemblies = (
            assemblies
            .sort_values('Resolution_Rank')
            .drop_duplicates(subset=['Phage_ID', 'Host_Token'], keep='first')
        )
        merged = candidates.merge(
            best_assemblies[['Phage_ID', 'Host_Token',
                              'Assembly_Accession', 'Resolution_Source',
                              'Resolution_Rank', 'Confidence',
                              'Assembly_Level', 'RefSeq_Category',
                              'Quality_Score', 'Ambiguous', 'Ambiguity_Reason']],
            on=['Phage_ID', 'Host_Token'],
            how='left',
        )
    else:
        merged = candidates.copy()
        for col in ['Assembly_Accession', 'Resolution_Source', 'Resolution_Rank',
                    'Confidence', 'Assembly_Level', 'RefSeq_Category',
                    'Quality_Score', 'Ambiguous', 'Ambiguity_Reason']:
            merged[col] = pd.NA

    merged['Resolution_Status'] = merged['Assembly_Accession'].notna().map(
        {True: 'resolved', False: 'unresolved'}
    )

    # --------------------------------------------------------------------------
    # Merge 2: + assembly_metadata  (left join on Assembly_Accession)
    # --------------------------------------------------------------------------
    if not asm_meta.empty and 'Assembly_Accession' in asm_meta.columns:
        asm_meta_slim = asm_meta[
            ['Assembly_Accession', 'Download_Status', 'Download_Date',
             'Metadata_Only', 'Organism_Name', 'Strain']
        ].drop_duplicates('Assembly_Accession')

        merged = merged.merge(asm_meta_slim, on='Assembly_Accession', how='left')
    else:
        for col in ['Download_Status', 'Download_Date', 'Metadata_Only',
                    'Organism_Name', 'Strain']:
            merged[col] = pd.NA

    # --------------------------------------------------------------------------
    # Merge 3: + qc_log  (left join on host_id which is Assembly_Accession
    #           with dots replaced by underscores, matching create_host_fasta)
    # --------------------------------------------------------------------------
    if not qc_log.empty and 'host_id' in qc_log.columns:
        # host_id in qc_log matches Host_ID (Assembly_Accession with . → _)
        merged['_host_id_key'] = merged['Assembly_Accession'].str.replace('.', '_', regex=False)
        qc_slim = qc_log[[
            'host_id', 'total_sequences', 'header_qc_status', 'n_duplicate_headers',
            'duplicate_header_examples', 'seq_qc_status', 'n_identical_seq_groups',
            'identical_seq_group_examples', 'index_status', 'error_message',
        ]].drop_duplicates('host_id')

        merged = merged.merge(
            qc_slim.rename(columns={'host_id': '_host_id_key'}),
            on='_host_id_key',
            how='left',
        ).drop(columns=['_host_id_key'])
    else:
        for col in ['total_sequences', 'header_qc_status', 'n_duplicate_headers',
                    'duplicate_header_examples', 'seq_qc_status',
                    'n_identical_seq_groups', 'identical_seq_group_examples',
                    'index_status', 'error_message']:
            merged[col] = pd.NA

    # --------------------------------------------------------------------------
    # Write output
    # --------------------------------------------------------------------------
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_csv, index=False)

    # --------------------------------------------------------------------------
    # Log summary statistics
    # --------------------------------------------------------------------------
    n_phages = merged['Phage_ID'].nunique()
    n_with_host = merged.loc[merged['Resolution_Status'] == 'resolved', 'Phage_ID'].nunique()
    n_downloaded = merged.loc[merged['Download_Status'] == 'success', 'Assembly_Accession'].nunique()
    n_indexed = merged.loc[merged['index_status'].isin(['indexed', 'already_indexed']),
                            'Assembly_Accession'].nunique()
    n_rejected = merged.loc[merged['index_status'] == 'rejected_duplicate_headers',
                             'Assembly_Accession'].nunique()

    logging.info("=" * 60)
    logging.info("HOST STATUS REPORT SUMMARY")
    logging.info("=" * 60)
    logging.info(f"Total phages:                    {n_phages:>6}")
    logging.info(f"Phages with ≥1 resolved host:    {n_with_host:>6}")
    logging.info(f"Assemblies downloaded:           {n_downloaded:>6}")
    logging.info(f"Assemblies indexed:              {n_indexed:>6}")
    logging.info(f"Assemblies rejected (dup hdrs):  {n_rejected:>6}")
    logging.info(f"Output: {output_csv}")
    logging.info("=" * 60)

    return merged


if __name__ == "__main__":
    if 'snakemake' in dir():                               # noqa: F821
        _setup_logging(snakemake.log[0])                   # noqa: F821
        create_host_status_report(
            candidates_csv=snakemake.input.candidates,         # noqa: F821
            assemblies_csv=snakemake.input.assemblies,         # noqa: F821
            assembly_metadata_csv=snakemake.input.assembly_metadata,  # noqa: F821
            qc_log_csv=snakemake.input.qc_log,                # noqa: F821
            output_csv=snakemake.output.status_report,         # noqa: F821
        )
    else:
        import argparse
        parser = argparse.ArgumentParser(
            description='Create combined per-phage host status report'
        )
        parser.add_argument('--candidates',        required=True)
        parser.add_argument('--assemblies',        required=True)
        parser.add_argument('--assembly-metadata', required=True)
        parser.add_argument('--qc-log',            required=True)
        parser.add_argument('--output',            required=True)
        args = parser.parse_args()

        create_host_status_report(
            candidates_csv=args.candidates,
            assemblies_csv=args.assemblies,
            assembly_metadata_csv=args.assembly_metadata,
            qc_log_csv=args.qc_log,
            output_csv=args.output,
        )

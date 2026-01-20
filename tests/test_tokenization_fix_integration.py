#!/usr/bin/env python3
"""
Integration test simulating the exact scenario from the problem statement.
This test ensures that merged CSV files can be read in chunks without
tokenization errors like "Expected 26 fields in line X, saw 27".
"""

import os
import sys
import tempfile
import pandas as pd
import csv
from pathlib import Path

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "preprocessing" / "mergers"))
import utils


def test_crispr_array_scenario():
    """
    Test the exact scenario from the problem statement where CRISPR array metadata
    has inconsistent Source_DB column causing tokenization errors.
    
    From the problem statement:
    "some merged CSV's have sometimes the Source_DB column AND the manually added 
    (To be kept) Phage_source column but some rows have only the Source_DB column 
    with the last column being empty (but the comma is still present)."
    """
    print("🧪 Testing CRISPR array metadata scenario...")
    
    # Simulate CRISPR array data from TemPhD (has Source_DB in file)
    df_temphd = pd.DataFrame({
        'Phage_ID': ['TemPhD_cluster_9791'],
        'Duplicated_Spacers': [0],
        'CRISPR_ID': ['TemPhD_cluster_9791_1'],
        'CRISPR_Start': [35443],
        'CRISPR_End': [35537],
        'CRISPR_Length': [94],
        'Potential_Orientation (AT%)': ['Forward'],
        'CRISPRDirection': ['Unknown'],
        'Consensus_Repeat': ['TGGACAATCGTTGGACATCCGTTGGACAA'],
        'Repeat_ID (CRISPRdb)': ['Unknown'],
        'Nb_CRISPRs_with_same_Repeat (CRISPRdb)': [0],
        'Repeat_Length': [29],
        'Spacers_Nb': [1],
        'Mean_size_Spacers': [37.0],
        'Standard_Deviation_Spacers': [0.0],
        'Nb_Repeats_matching_Consensus': [2],
        'Ratio_Repeats_match/TotalRepeat': [1.0],
        'Conservation_Repeats (% identity)': [100.0],
        'EBcons_Repeats': [100.0],
        'Conservation_Spacers (% identity)': [100.0],
        'EBcons_Spacers': [100.0],
        'Repeat_Length_plus_mean_size_Spacers': [66.0],
        'Ratio_Repeat/mean_Spacers_Length': [0.783783783783784],
        'CRISPR_found_in_DB (if sequence IDs are similar)': [0],
        'Evidence_Level': [1]
        # Note: Source_DB will be added by rename_columns
    })
    
    # Simulate CRISPR array data from CHVD (already has Source_DB)
    df_chvd = pd.DataFrame({
        'Phage_ID': ['SAMEA1906422_b1_ct69_vs2', 'SAMEA1906424_a1_ct74408_vs1'],
        'Duplicated_Spacers': [0, 0],
        'CRISPR_ID': ['SAMEA1906422_b1_ct69_vs2_1', 'SAMEA1906424_a1_ct74408_vs1_1'],
        'CRISPR_Start': [19441, 49711],
        'CRISPR_End': [19514, 49787],
        'CRISPR_Length': [73, 76],
        'Potential_Orientation (AT%)': ['Forward', 'Unknown'],
        'CRISPRDirection': ['Unknown', 'Unknown'],
        'Consensus_Repeat': ['TTTGCCTAAGCAAATTGCCTAAGCAAAA', 'AGAGAAAGAAGAGAAAGCGGCTG'],
        'Repeat_ID (CRISPRdb)': ['Unknown', 'Unknown'],
        'Nb_CRISPRs_with_same_Repeat (CRISPRdb)': [0, 0],
        'Repeat_Length': [28, 23],
        'Spacers_Nb': [1, 1],
        'Mean_size_Spacers': [18.0, 31.0],
        'Standard_Deviation_Spacers': [0.0, 0.0],
        'Nb_Repeats_matching_Consensus': [1, 1],
        'Ratio_Repeats_match/TotalRepeat': [0.5, 0.5],
        'Conservation_Repeats (% identity)': [71.4285714285714, 91.304347826087],
        'EBcons_Repeats': [71.4285714285714, 91.304347826087],
        'Conservation_Spacers (% identity)': [100.0, 100.0],
        'EBcons_Spacers': [100.0, 100.0],
        'Repeat_Length_plus_mean_size_Spacers': [46.0, 54.0],
        'Ratio_Repeat/mean_Spacers_Length': [1.55555555555556, 0.741935483870968],
        'CRISPR_found_in_DB (if sequence IDs are similar)': [0, 0],
        'Evidence_Level': [1, 1],
        'Source_DB': ['CHVD', 'CHVD']  # Already has Source_DB
    })
    
    # Expected columns list from merge_crispr_array_metadata.py
    COLUMNS_LIST = [
        "Phage_ID", "Duplicated_Spacers", "CRISPR_ID", "CRISPR_Start", "CRISPR_End",
        "CRISPR_Length", "Potential_Orientation (AT%)", "CRISPRDirection", "Consensus_Repeat",
        "Repeat_ID (CRISPRdb)", "Nb_CRISPRs_with_same_Repeat (CRISPRdb)", "Repeat_Length", "Spacers_Nb",
        "Mean_size_Spacers", "Standard_Deviation_Spacers", "Nb_Repeats_matching_Consensus",
        "Ratio_Repeats_match/TotalRepeat", "Conservation_Repeats (% identity)", "EBcons_Repeats",
        "Conservation_Spacers (% identity)", "EBcons_Spacers", "Repeat_Length_plus_mean_size_Spacers",
        "Ratio_Repeat/mean_Spacers_Length", "CRISPR_found_in_DB (if sequence IDs are similar)",
        "Evidence_Level", "Source_DB"
    ]
    
    # Simulate the processing that happens in the merger script
    # Add Source_DB to df_temphd (simulating rename_columns)
    df_temphd['Source_DB'] = 'TemPhD'
    
    # Validate and reorder columns
    df_temphd_validated = utils.validate_columns(df_temphd, COLUMNS_LIST)
    df_chvd_validated = utils.validate_columns(df_chvd, COLUMNS_LIST)
    
    # Verify both have same column order
    assert list(df_temphd_validated.columns) == COLUMNS_LIST, \
        f"TemPhD columns not in expected order"
    assert list(df_chvd_validated.columns) == COLUMNS_LIST, \
        f"CHVD columns not in expected order"
    
    # Merge using chunked merge
    dfs = [df_temphd_validated, df_chvd_validated]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Write merged CSV
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        assert total_rows == 3, f"Expected 3 rows, got {total_rows}"
        
        # Verify CSV structure - all lines should have same number of commas
        with open(output_file, 'r') as f:
            lines = f.readlines()
        
        header_commas = lines[0].count(',')
        for i, line in enumerate(lines[1:], start=1):
            line_commas = line.count(',')
            assert line_commas == header_commas, \
                f"Line {i} has {line_commas} commas, expected {header_commas}. " \
                f"This would cause tokenization error!"
        
        # Now simulate report generation - reading in chunks
        # This is what was failing in the original issue
        chunk_size = 2
        chunks_read = 0
        total_rows_read = 0
        
        try:
            for chunk in pd.read_csv(output_file, chunksize=chunk_size, quoting=csv.QUOTE_NONNUMERIC):
                chunks_read += 1
                total_rows_read += len(chunk)
                # Verify chunk has correct number of columns
                assert len(chunk.columns) == len(COLUMNS_LIST), \
                    f"Chunk has {len(chunk.columns)} columns, expected {len(COLUMNS_LIST)}"
                assert list(chunk.columns) == COLUMNS_LIST, \
                    f"Chunk columns don't match expected order"
        except Exception as e:
            print(f"❌ ERROR reading CSV in chunks: {e}")
            print(f"This is the type of error mentioned in the problem statement!")
            raise
        
        assert total_rows_read == 3, f"Expected to read 3 rows, got {total_rows_read}"
        assert chunks_read == 2, f"Expected 2 chunks, got {chunks_read}"
        
        print("✅ CRISPR array metadata scenario test PASSED")
        print(f"   Successfully read {total_rows_read} rows in {chunks_read} chunks without tokenization errors")
        
    finally:
        os.unlink(output_file)


def test_report_generation_simulation():
    """
    Simulate the exact report generation scenario that was failing.
    This simulates the fast_sample_known_size function from generate_reports.py
    """
    print("🧪 Testing report generation simulation...")
    
    # Create a larger dataset similar to the problem
    import random
    
    rows = []
    for i in range(100):
        if i % 2 == 0:
            # Rows with Source_DB
            rows.append({
                'Phage_ID': f'Phage_{i}',
                'CRISPR_ID': f'CRISPR_{i}',
                'CRISPR_Start': random.randint(1000, 50000),
                'CRISPR_End': random.randint(1000, 50000),
                'Evidence_Level': random.randint(0, 1),
                'Source_DB': 'TemPhD' if i % 4 == 0 else 'CHVD'
            })
        else:
            # Rows without Source_DB initially
            rows.append({
                'Phage_ID': f'Phage_{i}',
                'CRISPR_ID': f'CRISPR_{i}',
                'CRISPR_Start': random.randint(1000, 50000),
                'CRISPR_End': random.randint(1000, 50000),
                'Evidence_Level': random.randint(0, 1)
            })
    
    df = pd.DataFrame(rows)
    
    COLUMNS_LIST = ['Phage_ID', 'CRISPR_ID', 'CRISPR_Start', 'CRISPR_End', 
                    'Evidence_Level', 'Source_DB']
    
    # Validate columns (adds missing Source_DB with NaN)
    df_validated = utils.validate_columns(df, COLUMNS_LIST)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Write CSV
        utils.merge_dataframes_chunked([df_validated], output_file)
        
        # Simulate report generation reading with different chunk sizes
        for chunksize in [10, 25, 50]:
            try:
                total_rows = 0
                for chunk in pd.read_csv(output_file, chunksize=chunksize, quoting=csv.QUOTE_NONNUMERIC):
                    total_rows += len(chunk)
                    # Verify structure
                    assert len(chunk.columns) == len(COLUMNS_LIST), \
                        f"Chunk (size={chunksize}) has wrong number of columns"
                
                assert total_rows == 100, \
                    f"Expected 100 rows with chunksize={chunksize}, got {total_rows}"
                    
            except Exception as e:
                print(f"❌ ERROR with chunksize={chunksize}: {e}")
                raise
        
        print("✅ Report generation simulation test PASSED")
        print(f"   Successfully read CSV with multiple chunk sizes (10, 25, 50)")
        
    finally:
        os.unlink(output_file)


if __name__ == "__main__":
    print("=" * 60)
    print("Integration Test: CSV Tokenization Fix")
    print("=" * 60)
    print()
    
    test_crispr_array_scenario()
    print()
    test_report_generation_simulation()
    
    print()
    print("=" * 60)
    print("✅ All integration tests PASSED!")
    print("=" * 60)
    print()
    print("This fix ensures that:")
    print("  1. All merged CSV files have consistent column ordering")
    print("  2. Missing columns (Source_DB, Phage_source) are added with NaN")
    print("  3. CSV files can be read in chunks without tokenization errors")
    print("  4. Report generation will not fail with 'Expected N fields, saw M'")

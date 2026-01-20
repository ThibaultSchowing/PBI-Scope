#!/usr/bin/env python3
"""
Test to ensure column consistency across merged CSV files.
This addresses the issue where some rows have trailing empty columns,
causing CSV tokenization errors during report generation.
"""

import os
import sys
import tempfile
import pandas as pd
import numpy as np
import csv
from pathlib import Path

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "preprocessing" / "mergers"))
import utils


def test_column_ordering_consistency():
    """Test that validate_columns ensures consistent column ordering."""
    print("🧪 Testing column ordering consistency...")
    
    # Simulate two dataframes with columns in different orders
    df1 = pd.DataFrame({
        'Phage_ID': ['A', 'B'],
        'Length': [100, 200],
        'GC_content': [0.5, 0.6],
        'Host': ['E. coli', 'S. aureus']
    })
    
    # This dataframe has columns in different order and missing Source_DB
    df2 = pd.DataFrame({
        'GC_content': [0.7, 0.8],
        'Phage_ID': ['C', 'D'],
        'Host': ['P. aeruginosa', 'K. pneumoniae'],
        'Length': [300, 400]
    })
    
    expected_columns = ['Phage_ID', 'Length', 'GC_content', 'Host', 'Source_DB']
    
    # Add Source_DB to first dataframe (simulating rename_columns behavior)
    df1['Source_DB'] = 'DB1'
    
    # Validate and reorder both dataframes
    df1_validated = utils.validate_columns(df1, expected_columns)
    df2_validated = utils.validate_columns(df2, expected_columns)
    
    # Check that both have the same column order
    assert list(df1_validated.columns) == expected_columns, \
        f"df1 columns not in expected order: {list(df1_validated.columns)}"
    assert list(df2_validated.columns) == expected_columns, \
        f"df2 columns not in expected order: {list(df2_validated.columns)}"
    
    # Check that Source_DB was added to df2 with NaN values
    assert 'Source_DB' in df2_validated.columns, "Source_DB not added to df2"
    assert pd.isna(df2_validated['Source_DB'].iloc[0]), "Source_DB should be NaN for df2"
    
    print("✅ Column ordering consistency test PASSED")


def test_merge_with_inconsistent_columns():
    """Test that merge_dataframes_chunked handles inconsistent columns correctly."""
    print("🧪 Testing merge with inconsistent columns...")
    
    # Create test dataframes with different column orders and missing columns
    df1 = pd.DataFrame({
        'Phage_ID': ['A', 'B'],
        'CRISPR_ID': ['C1', 'C2'],
        'CRISPR_Start': [100, 200],
        'Source_DB': ['TemPhD', 'TemPhD']
    })
    
    # df2 has columns in different order
    df2 = pd.DataFrame({
        'CRISPR_Start': [300, 400],
        'Phage_ID': ['C', 'D'],
        'CRISPR_ID': ['C3', 'C4'],
        'Source_DB': ['CHVD', 'CHVD']
    })
    
    # df3 is missing Source_DB
    df3 = pd.DataFrame({
        'Phage_ID': ['E'],
        'CRISPR_ID': ['C5'],
        'CRISPR_Start': [500]
    })
    
    dfs = [df1, df2, df3]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        
        # Verify the result
        assert total_rows == 5, f"Expected 5 rows, got {total_rows}"
        
        # Read back with QUOTE_NONNUMERIC
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 5, f"Expected 5 rows in file, got {len(result_df)}"
        
        # All rows should have the same number of columns
        with open(output_file, 'r') as f:
            lines = f.readlines()
        
        # Count commas in each line (should be consistent)
        header_commas = lines[0].count(',')
        for i, line in enumerate(lines[1:], start=1):
            line_commas = line.count(',')
            assert line_commas == header_commas, \
                f"Line {i} has {line_commas} commas, expected {header_commas}: {line.strip()}"
        
        # Check that all rows have all columns
        assert list(result_df.columns) == ['Phage_ID', 'CRISPR_ID', 'CRISPR_Start', 'Source_DB'], \
            f"Columns mismatch: {list(result_df.columns)}"
        
        # Check that df3's Source_DB is NaN
        assert pd.isna(result_df.iloc[4]['Source_DB']), \
            "Last row should have NaN for Source_DB"
        
        print("✅ Merge with inconsistent columns test PASSED")
    finally:
        os.unlink(output_file)


def test_csv_reading_in_chunks():
    """Test that CSV can be read in chunks without tokenization errors."""
    print("🧪 Testing CSV reading in chunks...")
    
    # Create a CSV with consistent columns
    df1 = pd.DataFrame({
        'Phage_ID': [f'Phage_{i}' for i in range(100)],
        'CRISPR_ID': [f'CRISPR_{i}' for i in range(100)],
        'CRISPR_Start': list(range(100, 200)),
        'Source_DB': ['TemPhD'] * 50 + ['CHVD'] * 50
    })
    
    df2 = pd.DataFrame({
        'Phage_ID': [f'Phage_{i}' for i in range(100, 150)],
        'CRISPR_ID': [f'CRISPR_{i}' for i in range(100, 150)],
        'CRISPR_Start': list(range(200, 250))
        # Missing Source_DB column
    })
    
    dfs = [df1, df2]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        assert total_rows == 150, f"Expected 150 rows, got {total_rows}"
        
        # Try reading in chunks with pandas (simulating report generation)
        chunk_size = 50
        total_rows_read = 0
        chunks = []
        
        for chunk in pd.read_csv(output_file, chunksize=chunk_size, quoting=csv.QUOTE_NONNUMERIC):
            chunks.append(chunk)
            total_rows_read += len(chunk)
            # Each chunk should have the same columns
            assert list(chunk.columns) == ['Phage_ID', 'CRISPR_ID', 'CRISPR_Start', 'Source_DB'], \
                f"Chunk has wrong columns: {list(chunk.columns)}"
        
        assert total_rows_read == 150, f"Expected to read 150 rows, got {total_rows_read}"
        
        # Verify all chunks read successfully
        assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"
        
        print("✅ CSV reading in chunks test PASSED")
    finally:
        os.unlink(output_file)


def test_phage_source_and_source_db_columns():
    """Test handling of both Phage_source and Source_DB columns."""
    print("🧪 Testing Phage_source and Source_DB columns...")
    
    # Simulate anti-crispr data with Phage_source and Source_DB
    df1 = pd.DataFrame({
        'Phage_ID': ['A', 'B'],
        'Protein_ID': ['P1', 'P2'],
        'Source': ['AcR1', 'AcR2'],
        'Phage_source': ['RefSeq', 'GenBank'],
        'Source_DB': ['TemPhD', 'TemPhD']
    })
    
    # df2 missing both Phage_source and Source_DB
    df2 = pd.DataFrame({
        'Phage_ID': ['C'],
        'Protein_ID': ['P3'],
        'Source': ['AcR3']
    })
    
    expected_columns = ['Phage_ID', 'Protein_ID', 'Source', 'Phage_source', 'Source_DB']
    
    # Validate both dataframes
    df1_validated = utils.validate_columns(df1, expected_columns)
    df2_validated = utils.validate_columns(df2, expected_columns)
    
    # Both should have all columns in the same order
    assert list(df1_validated.columns) == expected_columns
    assert list(df2_validated.columns) == expected_columns
    
    # df2 should have NaN for missing columns
    assert pd.isna(df2_validated['Phage_source'].iloc[0])
    assert pd.isna(df2_validated['Source_DB'].iloc[0])
    
    # Now merge them
    dfs = [df1_validated, df2_validated]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        assert total_rows == 3
        
        # Read back and verify
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 3
        assert list(result_df.columns) == expected_columns
        
        # Verify that values are preserved correctly
        assert result_df.iloc[0]['Phage_source'] == 'RefSeq'
        assert result_df.iloc[1]['Phage_source'] == 'GenBank'
        assert pd.isna(result_df.iloc[2]['Phage_source'])
        
        print("✅ Phage_source and Source_DB columns test PASSED")
    finally:
        os.unlink(output_file)


if __name__ == "__main__":
    print("=" * 60)
    print("Test Suite: Column Consistency")
    print("=" * 60)
    
    test_column_ordering_consistency()
    test_merge_with_inconsistent_columns()
    test_csv_reading_in_chunks()
    test_phage_source_and_source_db_columns()
    
    print("\n" + "=" * 60)
    print("✅ All column consistency tests PASSED!")
    print("=" * 60)

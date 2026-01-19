#!/usr/bin/env python3
"""
Test the chunked merge functionality to ensure it prevents OOM errors
and produces correct output.
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


def test_chunked_merge_basic():
    """Test basic chunked merge with small dataframes."""
    print("🧪 Testing basic chunked merge...")
    
    # Create test dataframes
    df1 = pd.DataFrame({
        'ID': ['A', 'B', 'C'],
        'Value': [1, 2, 3],
        'Name': ['Alice', 'Bob', 'Charlie']
    })
    
    df2 = pd.DataFrame({
        'ID': ['D', 'E'],
        'Value': [4, 5],
        'Name': ['David', 'Eve']
    })
    
    df3 = pd.DataFrame({
        'ID': ['F'],
        'Value': [6],
        'Name': ['Frank']
    })
    
    dfs = [df1, df2, df3]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        
        # Verify the result
        assert total_rows == 6, f"Expected 6 rows, got {total_rows}"
        
        # Read back and verify
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 6, f"Expected 6 rows in file, got {len(result_df)}"
        assert list(result_df.columns) == ['ID', 'Value', 'Name'], "Columns mismatch"
        assert list(result_df['ID']) == ['A', 'B', 'C', 'D', 'E', 'F'], "IDs mismatch"
        assert list(result_df['Value'].astype(int)) == [1, 2, 3, 4, 5, 6], "Values mismatch"
        
        print("✅ Basic chunked merge test PASSED")
    finally:
        os.unlink(output_file)


def test_chunked_merge_empty_list():
    """Test chunked merge with empty list of dataframes."""
    print("🧪 Testing chunked merge with empty list...")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge with empty list
        total_rows = utils.merge_dataframes_chunked([], output_file)
        
        # Verify the result
        assert total_rows == 0, f"Expected 0 rows, got {total_rows}"
        assert os.path.exists(output_file), "Output file should exist"
        assert os.path.getsize(output_file) == 0, "Output file should be empty"
        
        print("✅ Empty list chunked merge test PASSED")
    finally:
        os.unlink(output_file)


def test_chunked_merge_large_dataframes():
    """Test chunked merge with larger dataframes to simulate real use case."""
    print("🧪 Testing chunked merge with larger dataframes...")
    
    # Create larger test dataframes (1000 rows each)
    dfs = []
    for i in range(5):
        df = pd.DataFrame({
            'Phage_ID': [f'Phage_{i}_{j}' for j in range(1000)],
            'Length': np.random.randint(1000, 100000, 1000),
            'GC_content': np.random.uniform(0.3, 0.7, 1000),
            'Source_DB': [f'DB_{i}'] * 1000
        })
        dfs.append(df)
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        
        # Verify the result
        assert total_rows == 5000, f"Expected 5000 rows, got {total_rows}"
        
        # Read back and verify
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 5000, f"Expected 5000 rows in file, got {len(result_df)}"
        assert list(result_df.columns) == ['Phage_ID', 'Length', 'GC_content', 'Source_DB'], "Columns mismatch"
        
        # Verify each source DB has 1000 rows
        for i in range(5):
            count = len(result_df[result_df['Source_DB'] == f'DB_{i}'])
            assert count == 1000, f"Expected 1000 rows for DB_{i}, got {count}"
        
        print("✅ Large dataframes chunked merge test PASSED")
    finally:
        os.unlink(output_file)


def test_chunked_merge_maintains_column_order():
    """Test that chunked merge maintains the column order from first dataframe."""
    print("🧪 Testing column order preservation...")
    
    df1 = pd.DataFrame({
        'Col_A': [1, 2],
        'Col_B': [3, 4],
        'Col_C': [5, 6]
    })
    
    df2 = pd.DataFrame({
        'Col_A': [7],
        'Col_B': [8],
        'Col_C': [9]
    })
    
    dfs = [df1, df2]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge
        utils.merge_dataframes_chunked(dfs, output_file)
        
        # Read back and verify column order
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert list(result_df.columns) == ['Col_A', 'Col_B', 'Col_C'], "Column order not preserved"
        
        print("✅ Column order preservation test PASSED")
    finally:
        os.unlink(output_file)


if __name__ == "__main__":
    print("=" * 60)
    print("Test Suite: Chunked Merge Functionality")
    print("=" * 60)
    
    test_chunked_merge_basic()
    test_chunked_merge_empty_list()
    test_chunked_merge_large_dataframes()
    test_chunked_merge_maintains_column_order()
    
    print("\n" + "=" * 60)
    print("✅ All chunked merge tests PASSED!")
    print("=" * 60)

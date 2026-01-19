#!/usr/bin/env python3
"""
Test CSV quoting functionality to ensure proper handling of fields with commas,
quotes, and other special characters.
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


def test_csv_quoting_with_commas():
    """Test that fields with commas are properly quoted and can be read back."""
    print("🧪 Testing CSV quoting with commas...")
    
    # Create test dataframe with commas in string fields
    df1 = pd.DataFrame({
        'ID': ['A', 'B', 'C'],
        'Description': ['Simple text', 'Text with, comma', 'Multiple, commas, here'],
        'Value': [1, 2, 3]
    })
    
    df2 = pd.DataFrame({
        'ID': ['D', 'E'],
        'Description': ['Another, comma', 'Normal text'],
        'Value': [4, 5]
    })
    
    dfs = [df1, df2]
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge with quoting
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        
        # Verify the result
        assert total_rows == 5, f"Expected 5 rows, got {total_rows}"
        
        # Read back with same quoting setting
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 5, f"Expected 5 rows in file, got {len(result_df)}"
        
        # Verify that descriptions with commas are preserved
        expected_descriptions = [
            'Simple text', 
            'Text with, comma', 
            'Multiple, commas, here',
            'Another, comma',
            'Normal text'
        ]
        assert list(result_df['Description']) == expected_descriptions, \
            f"Descriptions mismatch: {list(result_df['Description'])} != {expected_descriptions}"
        
        print("✅ CSV quoting with commas test PASSED")
    finally:
        os.unlink(output_file)


def test_csv_quoting_with_quotes():
    """Test that fields with quotes are properly escaped."""
    print("🧪 Testing CSV quoting with quotes...")
    
    # Create test dataframe with quotes in string fields
    df = pd.DataFrame({
        'ID': ['A', 'B'],
        'Text': ['Normal text', 'Text with "quotes" inside'],
        'Value': [1, 2]
    })
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge with quoting
        utils.merge_dataframes_chunked([df], output_file)
        
        # Read back with same quoting setting
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 2, f"Expected 2 rows in file, got {len(result_df)}"
        
        # Verify that quotes are preserved
        assert result_df['Text'].iloc[1] == 'Text with "quotes" inside', \
            f"Quotes not preserved: {result_df['Text'].iloc[1]}"
        
        print("✅ CSV quoting with quotes test PASSED")
    finally:
        os.unlink(output_file)


def test_csv_quoting_with_newlines():
    """Test that fields with newlines are properly handled."""
    print("🧪 Testing CSV quoting with newlines...")
    
    # Create test dataframe with newlines in string fields
    df = pd.DataFrame({
        'ID': ['A', 'B'],
        'Text': ['Normal text', 'Text with\nnewline'],
        'Value': [1, 2]
    })
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge with quoting
        utils.merge_dataframes_chunked([df], output_file)
        
        # Read back with same quoting setting
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 2, f"Expected 2 rows in file, got {len(result_df)}"
        
        # Verify that newlines are preserved
        assert result_df['Text'].iloc[1] == 'Text with\nnewline', \
            f"Newlines not preserved: {result_df['Text'].iloc[1]}"
        
        print("✅ CSV quoting with newlines test PASSED")
    finally:
        os.unlink(output_file)


def test_csv_quoting_with_mixed_types():
    """Test that numeric values are not quoted while strings are."""
    print("🧪 Testing CSV quoting with mixed types...")
    
    # Create test dataframe with mixed types
    df = pd.DataFrame({
        'ID': ['A', 'B', 'C'],
        'Count': [100, 200, 300],
        'Percentage': [0.5, 0.75, 0.9],
        'Description': ['Item, one', 'Item two', 'Item, three']
    })
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Use chunked merge with quoting
        utils.merge_dataframes_chunked([df], output_file)
        
        # Read the raw CSV to check quoting
        with open(output_file, 'r') as f:
            lines = f.readlines()
        
        # Check that numeric values are NOT quoted (QUOTE_NONNUMERIC behavior)
        # First data line should have pattern: "A",100,0.5,"Item, one"
        assert '100' in lines[1] and not '"100"' in lines[1], \
            "Numeric values should not be quoted"
        assert '"Item, one"' in lines[1] or '"Item,' in lines[1], \
            "String values should be quoted"
        
        # Read back with same quoting setting
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 3, f"Expected 3 rows in file, got {len(result_df)}"
        
        # Verify all data
        assert list(result_df['ID']) == ['A', 'B', 'C'], "IDs mismatch"
        assert list(result_df['Count']) == [100, 200, 300], "Counts mismatch"
        
        print("✅ CSV quoting with mixed types test PASSED")
    finally:
        os.unlink(output_file)


def test_csv_read_write_compatibility():
    """Test that data written with QUOTE_NONNUMERIC can be read correctly."""
    print("🧪 Testing read/write compatibility...")
    
    # Create test dataframe similar to real phage metadata
    df = pd.DataFrame({
        'Phage_ID': ['NC_000866', 'NC_001895'],
        'Length': [48502, 172786],
        'GC_content': [0.35, 0.42],
        'Phage_source': ['RefSeq', 'GenBank'],
        'Description': ['Enterobacteria phage T7, complete genome', 
                       'Mycobacterium phage L5, complete sequence'],
        'Host': ['Escherichia coli', 'Mycobacterium smegmatis, strain MC2 155']
    })
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        output_file = f.name
    
    try:
        # Write with chunked merge (using QUOTE_NONNUMERIC)
        utils.merge_dataframes_chunked([df], output_file)
        
        # Read back with QUOTE_NONNUMERIC
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        
        # Verify dimensions
        assert df.shape == result_df.shape, f"Shape mismatch: {df.shape} != {result_df.shape}"
        
        # Verify string columns are preserved exactly
        assert list(result_df['Phage_ID']) == list(df['Phage_ID']), "Phage_ID mismatch"
        assert list(result_df['Phage_source']) == list(df['Phage_source']), "Phage_source mismatch"
        assert list(result_df['Description']) == list(df['Description']), "Description mismatch"
        assert list(result_df['Host']) == list(df['Host']), "Host mismatch"
        
        # Verify numeric values (may be read as float instead of int, but values should match)
        assert list(result_df['Length'].astype(int)) == list(df['Length']), "Length values mismatch"
        assert list(result_df['GC_content']) == list(df['GC_content']), "GC_content values mismatch"
        
        print("✅ Read/write compatibility test PASSED")
    finally:
        os.unlink(output_file)


if __name__ == "__main__":
    print("=" * 60)
    print("Test Suite: CSV Quoting Functionality")
    print("=" * 60)
    
    test_csv_quoting_with_commas()
    test_csv_quoting_with_quotes()
    test_csv_quoting_with_newlines()
    test_csv_quoting_with_mixed_types()
    test_csv_read_write_compatibility()
    
    print("\n" + "=" * 60)
    print("✅ All CSV quoting tests PASSED!")
    print("=" * 60)

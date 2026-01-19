#!/usr/bin/env python3
"""
Test TSV reading functionality with QUOTE_NONNUMERIC to ensure proper handling
of fields with commas and other special characters in tab-separated files.
"""

import os
import sys
import tempfile
import pandas as pd
import csv
from pathlib import Path

# Add the scripts directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "preprocessing" / "mergers"))


def test_tsv_reading_with_commas():
    """Test that TSV files with quoted fields containing commas can be read properly."""
    print("🧪 Testing TSV reading with commas in quoted fields...")
    
    # Create a test TSV file with quoted fields containing commas
    # This simulates the actual data format from PhageScope
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
        tsv_file = f.name
        writer = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_NONNUMERIC)
        # Write header
        writer.writerow(['Phage_ID', 'Host', 'Length', 'Description'])
        # Write data rows - some with commas in string fields
        writer.writerow(['NC_000866', 'Escherichia coli', 48502, 'Simple description'])
        writer.writerow(['NC_001895', 'Mycobacterium smegmatis, strain MC2 155', 172786, 'Complex host'])
        writer.writerow(['NC_002014', 'Staphylococcus aureus, subsp. aureus', 43442, 'Another, complex, entry'])
    
    try:
        # Read the TSV file with QUOTE_NONNUMERIC (as our fixed code does)
        df = pd.read_csv(tsv_file, sep="\t", quoting=csv.QUOTE_NONNUMERIC)
        
        # Verify we got 3 rows
        assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
        
        # Verify we got 4 columns
        assert len(df.columns) == 4, f"Expected 4 columns, got {len(df.columns)}"
        
        # Verify the host field with commas is properly preserved
        assert df.iloc[1]['Host'] == 'Mycobacterium smegmatis, strain MC2 155', \
            f"Host field not preserved correctly: {df.iloc[1]['Host']}"
        
        assert df.iloc[2]['Host'] == 'Staphylococcus aureus, subsp. aureus', \
            f"Host field not preserved correctly: {df.iloc[2]['Host']}"
        
        # Verify the description field with commas
        assert df.iloc[2]['Description'] == 'Another, complex, entry', \
            f"Description field not preserved correctly: {df.iloc[2]['Description']}"
        
        print("✅ TSV reading with commas test PASSED")
    finally:
        os.unlink(tsv_file)


def test_tsv_reading_unquoted_fallback():
    """Test that TSV files without quotes can still be read (backward compatibility)."""
    print("🧪 Testing TSV reading of unquoted files...")
    
    # Create a test TSV file without quotes (old format)
    # This should still work if fields don't contain special characters
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
        tsv_file = f.name
        f.write("Phage_ID\tHost\tLength\n")
        f.write("NC_000866\tEscherichia_coli\t48502\n")
        f.write("NC_001895\tMycobacterium_phage\t172786\n")
    
    try:
        # Read the TSV file with QUOTE_NONNUMERIC
        # This should work fine for unquoted files without special characters
        df = pd.read_csv(tsv_file, sep="\t", quoting=csv.QUOTE_NONNUMERIC)
        
        # Verify we got 2 rows
        assert len(df) == 2, f"Expected 2 rows, got {len(df)}"
        
        # Verify we got 3 columns
        assert len(df.columns) == 3, f"Expected 3 columns, got {len(df.columns)}"
        
        print("✅ TSV reading of unquoted files test PASSED")
    finally:
        os.unlink(tsv_file)


def test_tsv_reading_mixed_content():
    """Test TSV reading with a mix of numeric and string fields."""
    print("🧪 Testing TSV reading with mixed content...")
    
    # Create a test TSV file similar to CRISPR metadata
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
        tsv_file = f.name
        writer = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_NONNUMERIC)
        # Write header
        writer.writerow(['Phage_ID', 'CRISPR_ID', 'CRISPR_Start', 'CRISPR_End', 'Consensus_Repeat'])
        # Write data rows
        writer.writerow(['NC_000001', 'CRISPR_1', 1000, 2000, 'GTCGCCCCGCACGGGCGTGGGGCTGACCCC'])
        writer.writerow(['NC_000002', 'CRISPR_2', 3000, 4500, 'ATCG, with comma'])
    
    try:
        # Read the TSV file with QUOTE_NONNUMERIC
        df = pd.read_csv(tsv_file, sep="\t", quoting=csv.QUOTE_NONNUMERIC)
        
        # Verify we got 2 rows
        assert len(df) == 2, f"Expected 2 rows, got {len(df)}"
        
        # Verify numeric columns are properly typed
        assert df['CRISPR_Start'].dtype in ['int64', 'float64'], \
            f"CRISPR_Start should be numeric, got {df['CRISPR_Start'].dtype}"
        
        # Verify string with comma is preserved
        assert df.iloc[1]['Consensus_Repeat'] == 'ATCG, with comma', \
            f"Consensus_Repeat not preserved: {df.iloc[1]['Consensus_Repeat']}"
        
        print("✅ TSV reading with mixed content test PASSED")
    finally:
        os.unlink(tsv_file)


if __name__ == "__main__":
    print("=" * 60)
    print("Test Suite: TSV Reading Functionality")
    print("=" * 60)
    
    test_tsv_reading_with_commas()
    test_tsv_reading_unquoted_fallback()
    test_tsv_reading_mixed_content()
    
    print("\n" + "=" * 60)
    print("✅ All TSV reading tests PASSED!")
    print("=" * 60)

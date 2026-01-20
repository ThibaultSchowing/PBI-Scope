#!/usr/bin/env python3
"""
Test to ensure malformed TSV files with extra values are handled correctly.
This addresses the issue where pandas auto-indexes rows with mismatched column counts,
causing data corruption and CSV tokenization errors.
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


def test_malformed_tsv_with_extra_values():
    """Test that TSV files with extra values in some rows are handled correctly."""
    print("🧪 Testing malformed TSV with extra values...")
    
    # Create a TSV file where ONE ROW has an extra value
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', prefix='CHVD_') as f:
        malformed_file = f.name
        # Header: 4 columns
        f.write("Phage_ID\tCRISPR_ID\tEvidence_Level\tSource_DB\n")
        # Row 1: 5 values (EXTRA VALUE: duplicate CHVD)
        f.write("phage1\tcrispr1\t1\tCHVD\tCHVD\n")
        # Row 2: 4 values (correct)
        f.write("phage2\tcrispr2\t1\tCHVD\n")
    
    try:
        # Read with index_col=False (the fix)
        df = pd.read_csv(malformed_file, sep="\t", quoting=csv.QUOTE_NONNUMERIC, index_col=False)
        
        # Verify the data is read correctly
        assert len(df) == 2, f"Expected 2 rows, got {len(df)}"
        assert list(df.columns) == ['Phage_ID', 'CRISPR_ID', 'Evidence_Level', 'Source_DB'], \
            f"Columns mismatch: {list(df.columns)}"
        
        # Verify that the first column contains the actual Phage_ID values, not used as index
        assert df['Phage_ID'].iloc[0] == 'phage1', \
            f"Expected 'phage1', got '{df['Phage_ID'].iloc[0]}'"
        assert df['Phage_ID'].iloc[1] == 'phage2', \
            f"Expected 'phage2', got '{df['Phage_ID'].iloc[1]}'"
        
        # Verify that CRISPR_ID is correct (not shifted)
        assert df['CRISPR_ID'].iloc[0] == 'crispr1', \
            f"Expected 'crispr1', got '{df['CRISPR_ID'].iloc[0]}'"
        assert df['CRISPR_ID'].iloc[1] == 'crispr2', \
            f"Expected 'crispr2', got '{df['CRISPR_ID'].iloc[1]}'"
        
        # Verify that the extra value in row 1 was dropped (not causing duplicate)
        assert df['Source_DB'].iloc[0] == 'CHVD', \
            f"Expected 'CHVD', got '{df['Source_DB'].iloc[0]}'"
        assert df['Source_DB'].iloc[1] == 'CHVD', \
            f"Expected 'CHVD', got '{df['Source_DB'].iloc[1]}'"
        
        print("✅ Malformed TSV test PASSED")
    finally:
        os.unlink(malformed_file)


def test_malformed_tsv_through_pipeline():
    """Test that malformed TSV goes through the full merge pipeline correctly."""
    print("🧪 Testing malformed TSV through merge pipeline...")
    
    # Create malformed TSV
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', prefix='CHVD_') as f:
        file1 = f.name
        f.write("Phage_ID\tCRISPR_ID\tEvidence_Level\tSource_DB\n")
        f.write("phage1\tcrispr1\t1\tCHVD\tCHVD\n")  # Extra value
        f.write("phage2\tcrispr2\t1\tCHVD\n")
    
    # Create normal TSV
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', prefix='TemPhD_') as f:
        file2 = f.name
        f.write("Phage_ID\tCRISPR_ID\tEvidence_Level\n")
        f.write("phage3\tcrispr3\t1\n")
    
    try:
        expected_columns = ["Phage_ID", "CRISPR_ID", "Evidence_Level", "Source_DB"]
        dfs = []
        
        for infile in [file1, file2]:
            df = pd.read_csv(infile, sep="\t", quoting=csv.QUOTE_NONNUMERIC, index_col=False)
            df = utils.rename_columns(df, infile)
            df = utils.validate_columns(df, expected_columns)
            dfs.append(df)
        
        # Merge using the chunked merge function
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            output_file = f.name
        
        total_rows = utils.merge_dataframes_chunked(dfs, output_file)
        assert total_rows == 3, f"Expected 3 rows, got {total_rows}"
        
        # Read back the merged CSV
        result_df = pd.read_csv(output_file, quoting=csv.QUOTE_NONNUMERIC)
        assert len(result_df) == 3, f"Expected 3 rows in merged file, got {len(result_df)}"
        
        # Verify all rows have correct structure
        with open(output_file, 'r') as f:
            lines = f.readlines()
        
        header_commas = lines[0].count(',')
        for i, line in enumerate(lines[1:], start=1):
            line_commas = line.count(',')
            assert line_commas == header_commas, \
                f"Line {i} has {line_commas} commas, expected {header_commas}: {line.strip()}"
        
        # Verify data integrity: Phage_ID should be correct
        assert result_df['Phage_ID'].iloc[0] == 'phage1', "Row 1 Phage_ID corrupted"
        assert result_df['Phage_ID'].iloc[1] == 'phage2', "Row 2 Phage_ID corrupted"
        assert result_df['Phage_ID'].iloc[2] == 'phage3', "Row 3 Phage_ID corrupted"
        
        # Verify CRISPR_ID is not shifted
        assert result_df['CRISPR_ID'].iloc[0] == 'crispr1', "Row 1 CRISPR_ID corrupted"
        assert result_df['CRISPR_ID'].iloc[1] == 'crispr2', "Row 2 CRISPR_ID corrupted"
        assert result_df['CRISPR_ID'].iloc[2] == 'crispr3', "Row 3 CRISPR_ID corrupted"
        
        os.unlink(output_file)
        print("✅ Pipeline test PASSED")
    finally:
        os.unlink(file1)
        os.unlink(file2)


def test_multiple_malformed_rows():
    """Test TSV with multiple rows having ONE extra value each."""
    print("🧪 Testing multiple malformed rows...")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv', prefix='Test_') as f:
        test_file = f.name
        f.write("Phage_ID\tProtein_ID\tSource\tPhage_source\tSource_DB\n")
        f.write("phage1\tprot1\tsrc1\tRefSeq\tCHVD\tEXTRA\n")  # 6 values (1 extra)
        f.write("phage2\tprot2\tsrc2\tGenBank\tTemPhD\n")  # 5 values (correct)
        f.write("phage3\tprot3\tsrc3\tRefSeq\tINPHARED\tEXTRA2\n")  # 6 values (1 extra)
    
    try:
        df = pd.read_csv(test_file, sep="\t", quoting=csv.QUOTE_NONNUMERIC, index_col=False)
        
        # All rows should be read
        assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
        
        # Verify data is not corrupted
        assert df['Phage_ID'].iloc[0] == 'phage1', "Phage_ID corrupted in row 1"
        assert df['Phage_ID'].iloc[1] == 'phage2', "Phage_ID corrupted in row 2"
        assert df['Phage_ID'].iloc[2] == 'phage3', "Phage_ID corrupted in row 3"
        
        assert df['Protein_ID'].iloc[0] == 'prot1', "Protein_ID corrupted in row 1"
        assert df['Protein_ID'].iloc[1] == 'prot2', "Protein_ID corrupted in row 2"
        assert df['Protein_ID'].iloc[2] == 'prot3', "Protein_ID corrupted in row 3"
        
        print("✅ Multiple malformed rows test PASSED")
    finally:
        os.unlink(test_file)


def test_without_index_col_false():
    """Demonstrate the bug when index_col=False is NOT used."""
    print("🧪 Demonstrating bug without index_col=False...")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
        test_file = f.name
        f.write("Phage_ID\tCRISPR_ID\tEvidence_Level\tSource_DB\n")
        f.write("phage1\tcrispr1\t1\tCHVD\tEXTRA\n")  # Extra value
    
    try:
        # Read WITHOUT index_col=False (the old buggy way)
        df_buggy = pd.read_csv(test_file, sep="\t", quoting=csv.QUOTE_NONNUMERIC)
        
        # This shows the bug: phage1 becomes the index instead of a column value
        print(f"  WITHOUT fix - Index: {list(df_buggy.index)}")
        print(f"  WITHOUT fix - Phage_ID column: {df_buggy['Phage_ID'].iloc[0]}")
        print(f"  WITHOUT fix - Data is CORRUPTED (values shifted)")
        
        # Read WITH index_col=False (the fix)
        df_fixed = pd.read_csv(test_file, sep="\t", quoting=csv.QUOTE_NONNUMERIC, index_col=False)
        
        print(f"  WITH fix - Index: {list(df_fixed.index)}")
        print(f"  WITH fix - Phage_ID column: {df_fixed['Phage_ID'].iloc[0]}")
        print(f"  WITH fix - Data is CORRECT")
        
        # Verify the fix works
        assert df_fixed['Phage_ID'].iloc[0] == 'phage1', "Fix didn't work!"
        
        print("✅ Bug demonstration PASSED")
    finally:
        os.unlink(test_file)


if __name__ == "__main__":
    print("=" * 60)
    print("Test Suite: Malformed TSV Handling")
    print("=" * 60)
    
    test_malformed_tsv_with_extra_values()
    test_malformed_tsv_through_pipeline()
    test_multiple_malformed_rows()
    test_without_index_col_false()
    
    print("\n" + "=" * 60)
    print("✅ All malformed TSV tests PASSED!")
    print("=" * 60)

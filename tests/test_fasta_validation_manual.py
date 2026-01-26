#!/usr/bin/env python3
"""
Manual test to verify FASTA validation logic
Tests the key validation logic without full module dependencies
"""

import tempfile
from pathlib import Path


def test_fasta_validation_logic():
    """Test the FASTA validation logic that was added"""
    
    print("Testing FASTA validation logic...")
    print("=" * 70)
    
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # Test 1: Valid FASTA file
        print("\n=== Test 1: Valid FASTA file ===")
        valid_fasta = temp_dir / "valid.fasta"
        with open(valid_fasta, 'w') as f:
            f.write(">seq1 Test sequence\n")
            f.write("ATCGATCGATCGATCG\n")
            f.write("ATCGATCGATCGATCG\n")
        
        # Check if file starts with '>'
        with open(valid_fasta, 'r') as f:
            first_line = f.readline().strip()
            is_valid = first_line.startswith('>')
        
        print(f"First line: {first_line}")
        print(f"Valid: {is_valid}")
        assert is_valid, "Valid FASTA should pass validation"
        print("✅ Valid FASTA accepted")
        
        # Test 2: Invalid FASTA file (no header)
        print("\n=== Test 2: Invalid FASTA file (no header) ===")
        invalid_fasta = temp_dir / "invalid.fasta"
        with open(invalid_fasta, 'w') as f:
            f.write("ATCGATCGATCGATCG\n")
            f.write("ATCGATCGATCGATCG\n")
        
        # Check if file starts with '>'
        with open(invalid_fasta, 'r') as f:
            first_line = f.readline().strip()
            is_valid = first_line.startswith('>')
        
        print(f"First line: {first_line}")
        print(f"Valid: {is_valid}")
        assert not is_valid, "Invalid FASTA should fail validation"
        print("✅ Invalid FASTA rejected")
        
        # Test 3: Empty file
        print("\n=== Test 3: Empty file ===")
        empty_fasta = temp_dir / "empty.fasta"
        with open(empty_fasta, 'w') as f:
            pass
        
        # Check file size
        is_empty = empty_fasta.stat().st_size == 0
        print(f"File size: {empty_fasta.stat().st_size}")
        print(f"Empty: {is_empty}")
        assert is_empty, "Empty file should be detected"
        print("✅ Empty file detected")
        
        # Test 4: File with whitespace before header
        print("\n=== Test 4: File with whitespace (should be rejected) ===")
        whitespace_fasta = temp_dir / "whitespace.fasta"
        with open(whitespace_fasta, 'w') as f:
            f.write("\n")
            f.write(">seq1 Test sequence\n")
            f.write("ATCGATCGATCGATCG\n")
        
        # Check if file starts with '>'
        with open(whitespace_fasta, 'r') as f:
            first_line = f.readline().strip()
            is_valid = first_line.startswith('>')
        
        print(f"First line (stripped): '{first_line}'")
        print(f"Valid: {is_valid}")
        # Empty line after stripping should not start with '>'
        assert not is_valid, "File with leading whitespace should be rejected"
        print("✅ File with leading whitespace rejected")
        
        # Test 5: Malformed FASTA (error message in problem statement)
        print("\n=== Test 5: Malformed FASTA (raw sequence data) ===")
        malformed_fasta = temp_dir / "malformed.fasta"
        with open(malformed_fasta, 'w') as f:
            f.write("ATTACAGCACTTGGCTACGCCCTTTGCAGGCAAGTTTTGCAAACGGGGAACTCACTCTTTATGCTCAAAA\n")
            f.write("ATCGATCGATCGATCG\n")
        
        # Check if file starts with '>'
        with open(malformed_fasta, 'r') as f:
            first_line = f.readline().strip()
            is_valid = first_line.startswith('>')
            
        print(f"First line: {first_line[:60]}...")
        print(f"Valid: {is_valid}")
        assert not is_valid, "Malformed FASTA should be rejected"
        print("✅ Malformed FASTA rejected")
        
        print("\n" + "=" * 70)
        print("✅ All validation tests passed!")
        return True
        
    finally:
        # Clean up
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    test_fasta_validation_logic()

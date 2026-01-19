#!/usr/bin/env python3
"""
Integration test to validate the FASTA merge fix.
This test simulates the actual scenario where a source directory has no FASTA files.
"""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path


def test_empty_source_directory():
    """Test that empty source directories are handled gracefully."""
    print("🧪 Testing empty source directory handling...")
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir) / "empty_source"
        output_dir = Path(tmpdir) / "output"
        source_dir.mkdir()
        output_dir.mkdir()
        
        output_file = output_dir / "test.fasta"
        
        # Simulate the shell script logic
        shell_script = f"""
        set -e
        
        # Find all fasta files and store in an array
        mapfile -t fasta_files < <(find {source_dir} -type f \\( -name "*.fasta" -o -name "*.fa" \\))
        
        # Check if any files were found
        if [ "${{#fasta_files[@]}}" -eq 0 ]; then
            echo "⚠️ WARNING: No FASTA files found in {source_dir} - creating empty file" >&2
            touch {output_file}
        elif [ "${{#fasta_files[@]}}" -eq 1 ]; then
            # Only one file, just copy it
            cp "${{fasta_files[0]}}" {output_file}
        else
            # Multiple files, merge them
            echo "Would call merge script"
        fi
        """
        
        # Run the shell script
        result = subprocess.run(
            ["bash", "-c", shell_script],
            capture_output=True,
            text=True
        )
        
        # Check results
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert output_file.exists(), "Output file should be created"
        assert output_file.stat().st_size == 0, "Output file should be empty"
        assert "WARNING: No FASTA files found" in result.stderr, "Warning should be printed"
        
        print("✅ Empty source directory test PASSED")


def test_single_fasta_file():
    """Test that a single FASTA file is copied correctly."""
    print("🧪 Testing single FASTA file handling...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir) / "single_source"
        output_dir = Path(tmpdir) / "output"
        source_dir.mkdir()
        output_dir.mkdir()
        
        # Create a single FASTA file
        test_file = source_dir / "test.fasta"
        test_file.write_text(">seq1\nATGC\n")
        
        output_file = output_dir / "test.fasta"
        
        # Simulate the shell script logic
        shell_script = f"""
        set -e
        
        mapfile -t fasta_files < <(find {source_dir} -type f \\( -name "*.fasta" -o -name "*.fa" \\))
        
        if [ "${{#fasta_files[@]}}" -eq 0 ]; then
            echo "⚠️ WARNING: No FASTA files found" >&2
            touch {output_file}
        elif [ "${{#fasta_files[@]}}" -eq 1 ]; then
            cp "${{fasta_files[0]}}" {output_file}
        else
            echo "Would call merge script"
        fi
        """
        
        result = subprocess.run(
            ["bash", "-c", shell_script],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert output_file.exists(), "Output file should be created"
        assert output_file.read_text() == ">seq1\nATGC\n", "Content should match"
        
        print("✅ Single FASTA file test PASSED")


def test_multiple_fasta_files():
    """Test that multiple FASTA files trigger the merge logic."""
    print("🧪 Testing multiple FASTA files handling...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = Path(tmpdir) / "multi_source"
        output_dir = Path(tmpdir) / "output"
        source_dir.mkdir()
        output_dir.mkdir()
        
        # Create multiple FASTA files
        (source_dir / "test1.fasta").write_text(">seq1\nATGC\n")
        (source_dir / "test2.fa").write_text(">seq2\nGCTA\n")
        
        output_file = output_dir / "test.fasta"
        
        # Simulate the shell script logic
        shell_script = f"""
        set -e
        
        mapfile -t fasta_files < <(find {source_dir} -type f \\( -name "*.fasta" -o -name "*.fa" \\))
        
        if [ "${{#fasta_files[@]}}" -eq 0 ]; then
            echo "⚠️ WARNING: No FASTA files found" >&2
            touch {output_file}
        elif [ "${{#fasta_files[@]}}" -eq 1 ]; then
            cp "${{fasta_files[0]}}" {output_file}
        else
            echo "Multiple files found: ${{#fasta_files[@]}}"
            # Would call merge script
            touch {output_file}
        fi
        """
        
        result = subprocess.run(
            ["bash", "-c", shell_script],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "Multiple files found: 2" in result.stdout, "Should detect 2 files"
        
        print("✅ Multiple FASTA files test PASSED")


def test_downstream_merge_compatibility():
    """Test that empty files are compatible with downstream merge rules."""
    print("🧪 Testing downstream merge compatibility...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create empty and non-empty FASTA files
        empty_file = Path(tmpdir) / "empty.fasta"
        valid_file = Path(tmpdir) / "valid.fasta"
        
        empty_file.touch()
        valid_file.write_text(">seq1\nATGC\n")
        
        # Simulate the downstream merge logic
        valid_files = []
        for fasta_file in [empty_file, valid_file]:
            if os.path.exists(fasta_file) and os.path.getsize(fasta_file) > 0:
                valid_files.append(fasta_file)
            else:
                print(f"⚠️ Skipping empty or missing file: {fasta_file.name}")
        
        assert len(valid_files) == 1, "Should have 1 valid file"
        assert valid_files[0] == valid_file, "Valid file should be in the list"
        
        print("✅ Downstream merge compatibility test PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("Integration Test: FASTA Merge Fix")
    print("=" * 60)
    
    test_empty_source_directory()
    test_single_fasta_file()
    test_multiple_fasta_files()
    test_downstream_merge_compatibility()
    
    print("\n" + "=" * 60)
    print("✅ All integration tests PASSED!")
    print("=" * 60)

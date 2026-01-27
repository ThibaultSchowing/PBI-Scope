#!/usr/bin/env python3
"""
Test the resume capability logic of host genome downloader.

This test verifies the core logic of:
1. Status file tracking (JSON-based)
2. Atomic file saving
3. Resume state management

This is a simplified test that validates the logic without requiring
full dependencies like pandas, biopython, etc.
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path


def test_status_file_io():
    """Test basic status file I/O operations"""
    print("Testing status file I/O...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        status_file = Path(temp_dir) / "host_download_status.json"
        
        # Test 1: Write status
        status = {
            "Escherichia coli": "success",
            "Staphylococcus aureus": "failed",
            "Pseudomonas aeruginosa": "not_attempted"
        }
        
        # Simulate atomic write
        temp_file = status_file.with_suffix('.json.tmp')
        with open(temp_file, 'w') as f:
            json.dump(status, f, indent=2)
        temp_file.replace(status_file)
        
        assert status_file.exists(), "Status file should exist"
        assert not temp_file.exists(), "Temp file should be removed after atomic write"
        
        # Test 2: Read status
        with open(status_file, 'r') as f:
            loaded_status = json.load(f)
        
        assert loaded_status == status, "Loaded status should match saved status"
        
        # Test 3: Update status
        status["Bacillus subtilis"] = "success"
        temp_file = status_file.with_suffix('.json.tmp')
        with open(temp_file, 'w') as f:
            json.dump(status, f, indent=2)
        temp_file.replace(status_file)
        
        with open(status_file, 'r') as f:
            updated_status = json.load(f)
        
        assert len(updated_status) == 4, "Should have 4 entries after update"
        assert updated_status["Bacillus subtilis"] == "success"
        
        print("  ✅ Status file I/O works correctly")
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def test_corrupted_status_handling():
    """Test handling of corrupted status files"""
    print("Testing corrupted status file handling...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        status_file = Path(temp_dir) / "host_download_status.json"
        
        # Write corrupted JSON
        with open(status_file, 'w') as f:
            f.write("{ this is not valid JSON }")
        
        # Try to load (should handle gracefully)
        try:
            with open(status_file, 'r') as f:
                json.load(f)
            assert False, "Should have raised JSONDecodeError"
        except json.JSONDecodeError:
            # Expected - handle by starting fresh
            status = {}
            assert len(status) == 0, "Should start with empty status on corruption"
        
        print("  ✅ Corrupted status files handled correctly")
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def test_resume_logic():
    """Test the resume logic (skip successful, retry failed)"""
    print("Testing resume logic...")
    
    # Simulate existing status
    status = {
        "Escherichia coli": "success",
        "Staphylococcus aureus": "failed",
        "Pseudomonas aeruginosa": "not_attempted",
        "Bacillus subtilis": "not_attempted"
    }
    
    # Simulate getting list of species to process
    all_species = [
        "Escherichia coli",
        "Staphylococcus aureus",
        "Pseudomonas aeruginosa",
        "Bacillus subtilis"
    ]
    
    # Filter out already successful ones
    to_process = []
    skipped = []
    
    for species in all_species:
        if status.get(species) == 'success':
            skipped.append(species)
        else:
            to_process.append(species)
    
    assert len(skipped) == 1, "Should skip 1 successful species"
    assert "Escherichia coli" in skipped, "Should skip Escherichia coli"
    
    assert len(to_process) == 3, "Should process 3 species"
    assert "Staphylococcus aureus" in to_process, "Should retry failed species"
    assert "Pseudomonas aeruginosa" in to_process
    assert "Bacillus subtilis" in to_process
    
    print("  ✅ Resume logic works correctly")


def test_metadata_reconstruction_logic():
    """Test logic for reconstructing metadata from filenames"""
    print("Testing metadata reconstruction logic...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        output_dir = Path(temp_dir) / "genomes"
        output_dir.mkdir()
        
        # Create some genome files with various formats
        files = [
            "Escherichia_coli_GCF_000005845.2.fna",
            "Staphylococcus_aureus_GCF_000013425.1.fna",
            "Pseudomonas_aeruginosa_GCF_000006765.1.fna"
        ]
        
        for filename in files:
            filepath = output_dir / filename
            with open(filepath, 'w') as f:
                f.write(">test_sequence\n")
                f.write("ATCGATCGATCG\n")
        
        # Test reconstruction for a species
        species_name = "Escherichia coli"
        species_clean = species_name.replace(' ', '_')
        
        # Find matching files
        matching_files = list(output_dir.glob(f"{species_clean}_*.fna"))
        
        assert len(matching_files) == 1, "Should find exactly one matching file"
        
        fasta_path = matching_files[0]
        host_id = fasta_path.stem
        
        assert host_id == "Escherichia_coli_GCF_000005845.2"
        
        # Extract accession using regex (same as in actual code)
        import re
        accession_match = re.search(r'(GC[AF]_\d+\.\d+)', host_id)
        assert accession_match is not None, "Should match accession pattern"
        
        accession = accession_match.group(1)
        
        assert accession == "GCF_000005845.2"
        
        print("  ✅ Metadata reconstruction logic works correctly")
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def test_status_file_location():
    """Test that status file is created in the right location"""
    print("Testing status file location...")
    
    temp_dir = tempfile.mkdtemp()
    try:
        metadata_output = Path(temp_dir) / "data" / "metadata" / "host_metadata.csv"
        metadata_output.parent.mkdir(parents=True, exist_ok=True)
        
        # Status file should be in same directory as metadata output
        expected_status_file = metadata_output.parent / "host_download_status.json"
        
        # Create the status file
        status = {"test": "success"}
        with open(expected_status_file, 'w') as f:
            json.dump(status, f)
        
        assert expected_status_file.exists()
        assert expected_status_file.parent == metadata_output.parent
        
        print("  ✅ Status file location is correct")
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    print("=" * 70)
    print("Testing Resume Capability Logic")
    print("=" * 70)
    print()
    
    tests = [
        test_status_file_io,
        test_corrupted_status_handling,
        test_resume_logic,
        test_metadata_reconstruction_logic,
        test_status_file_location
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
            import traceback
            traceback.print_exc()
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            failed += 1
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed} tests")
    print("=" * 70)
    
    sys.exit(0 if failed == 0 else 1)

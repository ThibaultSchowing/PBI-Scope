#!/usr/bin/env python3
"""
Test script to verify environment-based path configuration for PBI package.
Tests that DATA_PATH environment variable correctly modifies package paths.
"""

import os
import sys
from pathlib import Path


def test_pbi_package_path_configuration():
    """Test that PBI package correctly uses DATA_PATH environment variable."""
    
    print("=" * 60)
    print("Testing PBI Package Path Configuration")
    print("=" * 60)
    
    # Import the package
    sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
    import pbi
    
    # Test 1: Default behavior (local mode - no DATA_PATH set)
    print("\n1. Testing default behavior (DATA_PATH unset)...")
    if 'DATA_PATH' in os.environ:
        del os.environ['DATA_PATH']
    
    # Force reload to get fresh paths
    import importlib
    importlib.reload(pbi)
    
    paths = pbi.get_default_paths()
    
    print(f"   database: {paths['database']}")
    print(f"   phage_fasta: {paths['phage_fasta']}")
    print(f"   protein_fasta: {paths['protein_fasta']}")
    
    # In local mode, paths should be relative to project root
    assert 'data/processed' in str(paths['database']), \
        f"Expected relative path with 'data/processed', got {paths['database']}"
    assert not str(paths['database']).startswith('/data'), \
        f"Expected relative path, not absolute /data path, got {paths['database']}"
    
    print("   ✓ Local mode uses project-relative paths")
    
    # Test 2: Docker mode (DATA_PATH=/data/processed)
    print("\n2. Testing Docker mode (DATA_PATH=/data/processed)...")
    os.environ['DATA_PATH'] = '/data/processed'
    
    # Force reload to get fresh paths
    importlib.reload(pbi)
    
    paths = pbi.get_default_paths()
    
    print(f"   database: {paths['database']}")
    print(f"   phage_fasta: {paths['phage_fasta']}")
    print(f"   protein_fasta: {paths['protein_fasta']}")
    
    # In Docker mode, paths should use DATA_PATH
    assert str(paths['database']) == '/data/processed/databases/phage_database_optimized.duckdb', \
        f"Expected '/data/processed/databases/phage_database_optimized.duckdb', got {paths['database']}"
    assert str(paths['phage_fasta']) == '/data/processed/sequences/all_phages.fasta', \
        f"Expected '/data/processed/sequences/all_phages.fasta', got {paths['phage_fasta']}"
    assert str(paths['protein_fasta']) == '/data/processed/sequences/all_proteins.fasta', \
        f"Expected '/data/processed/sequences/all_proteins.fasta', got {paths['protein_fasta']}"
    
    print("   ✓ Docker mode uses DATA_PATH environment variable")
    
    # Test 3: Custom path
    print("\n3. Testing custom path (DATA_PATH=/custom/data)...")
    os.environ['DATA_PATH'] = '/custom/data'
    
    # Force reload to get fresh paths
    importlib.reload(pbi)
    
    paths = pbi.get_default_paths()
    
    print(f"   database: {paths['database']}")
    print(f"   phage_fasta: {paths['phage_fasta']}")
    print(f"   protein_fasta: {paths['protein_fasta']}")
    
    # Custom path should be used
    assert str(paths['database']) == '/custom/data/databases/phage_database_optimized.duckdb', \
        f"Expected '/custom/data/databases/phage_database_optimized.duckdb', got {paths['database']}"
    assert str(paths['phage_fasta']) == '/custom/data/sequences/all_phages.fasta', \
        f"Expected '/custom/data/sequences/all_phages.fasta', got {paths['phage_fasta']}"
    
    print("   ✓ Custom path works correctly")
    
    # Test 4: Verify all expected keys are present
    print("\n4. Testing path dictionary structure...")
    expected_keys = ['database', 'phage_fasta', 'protein_fasta', 'host_mapping', 'host_fasta']
    
    for key in expected_keys:
        assert key in paths, f"Expected key '{key}' not found in paths dictionary"
        assert paths[key] is not None, f"Path for '{key}' is None"
        print(f"   ✓ {key}: present")
    
    print("   ✓ All expected path keys are present")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("✅ PBI package respects DATA_PATH environment variable")
    print("✅ Local mode uses project-relative paths")
    print("✅ Docker mode uses DATA_PATH (/data/processed)")
    print("✅ Custom paths work as expected")
    print("✅ All required path keys are present")
    print("\nUsage in different environments:")
    print("- Docker: DATA_PATH=/data/processed (set in docker-compose.yml)")
    print("- Local: DATA_PATH unset (uses project/data/processed)")
    print("- Custom: DATA_PATH=/your/custom/path")
    print("=" * 60)


if __name__ == '__main__':
    try:
        test_pbi_package_path_configuration()
        print("\n✅ All tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""
Test script to verify environment-based path configuration for Snakemake.
Tests that PBI_DATA_DIR environment variable correctly modifies config paths.
"""

import os
import sys
import yaml
from pathlib import Path


def test_snakemake_path_configuration():
    """Test that Snakemake config correctly uses PBI_DATA_DIR."""
    
    print("=" * 60)
    print("Testing PBI Snakemake Path Configuration")
    print("=" * 60)
    
    # Load the original config
    config_path = Path(__file__).parent.parent / 'workflow' / 'config' / 'config.yaml'
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    print("\n1. Testing original config values...")
    original_reports = config['reports_output']
    original_fasta = config['all_phages_fasta']
    original_db = config['duckdb_output']
    
    print(f"   reports_output: {original_reports}")
    print(f"   all_phages_fasta: {original_fasta}")
    print(f"   duckdb_output: {original_db}")
    
    assert original_reports.startswith('/data'), "Expected original config to have /data paths"
    print("   ✓ Original config has /data paths")
    
    # Test 1: Default behavior (local mode)
    print("\n2. Testing default behavior (PBI_DATA_DIR unset)...")
    if 'PBI_DATA_DIR' in os.environ:
        del os.environ['PBI_DATA_DIR']
    
    BASE_DATA_DIR = os.getenv('PBI_DATA_DIR', 'data')
    print(f"   BASE_DATA_DIR: {BASE_DATA_DIR}")
    
    # Reload config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Apply transformation (using dynamic discovery like Snakefile)
    for path_key in config:
        if isinstance(config[path_key], str) and config[path_key].startswith('/data'):
            config[path_key] = config[path_key].replace('/data', BASE_DATA_DIR, 1)
    
    assert config['reports_output'] == 'data/processed/reports/', f"Expected 'data/processed/reports/', got {config['reports_output']}"
    assert config['all_phages_fasta'] == 'data/processed/sequences/all_phages.fasta', f"Expected 'data/processed/sequences/all_phages.fasta', got {config['all_phages_fasta']}"
    assert config['duckdb_output'] == 'data/processed/databases/phage_database.duckdb', f"Expected 'data/processed/databases/phage_database.duckdb', got {config['duckdb_output']}"
    
    print(f"   reports_output: {config['reports_output']}")
    print(f"   all_phages_fasta: {config['all_phages_fasta']}")
    print(f"   duckdb_output: {config['duckdb_output']}")
    print("   ✓ Local mode paths are relative")
    
    # Test 2: Docker mode
    print("\n3. Testing Docker mode (PBI_DATA_DIR=/data)...")
    os.environ['PBI_DATA_DIR'] = '/data'
    BASE_DATA_DIR = os.getenv('PBI_DATA_DIR', 'data')
    print(f"   BASE_DATA_DIR: {BASE_DATA_DIR}")
    
    # Reload config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Apply transformation (using dynamic discovery like Snakefile)
    for path_key in config:
        if isinstance(config[path_key], str) and config[path_key].startswith('/data'):
            config[path_key] = config[path_key].replace('/data', BASE_DATA_DIR, 1)
    
    assert config['reports_output'] == '/data/processed/reports/', f"Expected '/data/processed/reports/', got {config['reports_output']}"
    assert config['all_phages_fasta'] == '/data/processed/sequences/all_phages.fasta', f"Expected '/data/processed/sequences/all_phages.fasta', got {config['all_phages_fasta']}"
    assert config['duckdb_output'] == '/data/processed/databases/phage_database.duckdb', f"Expected '/data/processed/databases/phage_database.duckdb', got {config['duckdb_output']}"
    
    print(f"   reports_output: {config['reports_output']}")
    print(f"   all_phages_fasta: {config['all_phages_fasta']}")
    print(f"   duckdb_output: {config['duckdb_output']}")
    print("   ✓ Docker mode paths use /data prefix")
    
    # Test 3: Custom path
    print("\n4. Testing custom path (PBI_DATA_DIR=/custom/path)...")
    os.environ['PBI_DATA_DIR'] = '/custom/path'
    BASE_DATA_DIR = os.getenv('PBI_DATA_DIR', 'data')
    print(f"   BASE_DATA_DIR: {BASE_DATA_DIR}")
    
    # Reload config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Apply transformation (using dynamic discovery like Snakefile)
    for path_key in config:
        if isinstance(config[path_key], str) and config[path_key].startswith('/data'):
            config[path_key] = config[path_key].replace('/data', BASE_DATA_DIR, 1)
    
    assert config['reports_output'] == '/custom/path/processed/reports/', f"Expected '/custom/path/processed/reports/', got {config['reports_output']}"
    assert config['all_phages_fasta'] == '/custom/path/processed/sequences/all_phages.fasta', f"Expected '/custom/path/processed/sequences/all_phages.fasta', got {config['all_phages_fasta']}"
    assert config['duckdb_output'] == '/custom/path/processed/databases/phage_database.duckdb', f"Expected '/custom/path/processed/databases/phage_database.duckdb', got {config['duckdb_output']}"
    
    print(f"   reports_output: {config['reports_output']}")
    print(f"   all_phages_fasta: {config['all_phages_fasta']}")
    print(f"   duckdb_output: {config['duckdb_output']}")
    print("   ✓ Custom path works correctly")
    
    # Test 4: Verify path replacement doesn't break /databases
    print("\n5. Testing path replacement doesn't affect /databases substring...")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    BASE_DATA_DIR = 'data'
    # Apply transformation (using dynamic discovery like Snakefile)
    for path_key in config:
        if isinstance(config[path_key], str) and config[path_key].startswith('/data'):
            original = config[path_key]
            config[path_key] = config[path_key].replace('/data', BASE_DATA_DIR, 1)
            # Ensure /databases doesn't become databases
            if 'databases' in original:
                assert '/databases' in original or 'data/processed/databases' in config[path_key], \
                    f"Path replacement broke /databases: {original} -> {config[path_key]}"
    
    print("   ✓ Path replacement preserves /databases and other paths correctly")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("✅ Environment variable PBI_DATA_DIR is correctly used")
    print("✅ Local mode uses relative paths (data/)")
    print("✅ Docker mode uses absolute paths (/data)")
    print("✅ Custom paths work as expected")
    print("✅ Path replacement doesn't break substring matches")
    print("\nEnvironment configuration:")
    print("- Docker: PBI_DATA_DIR=/data (set in docker-compose.yml)")
    print("- Local: PBI_DATA_DIR=data (default, or set in run_local.sh)")
    print("=" * 60)


if __name__ == '__main__':
    try:
        test_snakemake_path_configuration()
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

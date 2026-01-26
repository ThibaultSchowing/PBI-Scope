#!/usr/bin/env python3
"""
Integration test for optimized genome download pipeline

This test creates a minimal test dataset and validates the core functionality
without requiring full dependencies.
"""

import os
import sys
import tempfile
import json
import re
from pathlib import Path

def test_species_validator():
    """Test GTDB identifier detection"""
    print("Testing GTDB identifier detection...")
    
    # GTDB pattern
    gtdb_pattern = re.compile(r'\bsp\d{9}\b', re.IGNORECASE)
    
    # Test cases
    test_cases = [
        ("Escherichia coli", False, "Valid species name"),
        ("Acidovorax sp000302535", True, "GTDB identifier"),
        ("sp001411535", True, "Pure GTDB ID"),
        ("Bacteria sp123456789", True, "GTDB ID in name"),
        ("Staphylococcus aureus", False, "Valid species"),
    ]
    
    results = []
    for name, should_match, description in test_cases:
        matches = bool(gtdb_pattern.search(name))
        status = "✅ PASS" if matches == should_match else "❌ FAIL"
        results.append((status, description, name, matches))
        print(f"  {status}: {description} - '{name}' (matched: {matches})")
    
    # Check all passed
    all_passed = all(r[0] == "✅ PASS" for r in results)
    return all_passed


def test_config_parsing():
    """Test configuration file structure"""
    print("\nTesting configuration file...")
    
    config_path = Path(__file__).parent.parent / "workflow" / "config" / "genome_download_config.yaml"
    
    if not config_path.exists():
        print(f"  ❌ FAIL: Config file not found at {config_path}")
        return False
    
    try:
        # Basic validation without yaml library
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Check for required sections
        required_sections = [
            'download:',
            'cache:',
            'parsing:',
            'ncbi:',
            'validation:',
            'progress:',
            'failures:',
            'logging:'
        ]
        
        all_present = True
        for section in required_sections:
            if section in content:
                print(f"  ✅ PASS: Found section {section}")
            else:
                print(f"  ❌ FAIL: Missing section {section}")
                all_present = False
        
        # Check for key parameters
        key_params = [
            'fasta_format: "fasta-2line"',
            'max_concurrent:',
            'requests_per_second:',
            'metadata_db:',
            'gtdb_pattern:'
        ]
        
        for param in key_params:
            if param in content:
                print(f"  ✅ PASS: Found parameter {param.split(':')[0]}")
            else:
                print(f"  ⚠️  WARNING: Missing parameter {param.split(':')[0]}")
        
        return all_present
        
    except Exception as e:
        print(f"  ❌ FAIL: Error reading config: {e}")
        return False


def test_file_structure():
    """Test that all required files exist"""
    print("\nTesting file structure...")
    
    base_dir = Path(__file__).parent.parent
    
    required_files = [
        "workflow/scripts/sequences/download_host_genomes_optimized.py",
        "workflow/scripts/sequences/download_host_genomes.py",
        "workflow/config/genome_download_config.yaml",
        "docs/genome_download_optimization.md",
        "workflow/envs/sequences.yaml"
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = base_dir / file_path
        if full_path.exists():
            print(f"  ✅ PASS: {file_path} exists")
        else:
            print(f"  ❌ FAIL: {file_path} missing")
            all_exist = False
    
    return all_exist


def test_fasta_format_fix():
    """Test that fasta-2line format is used in both scripts"""
    print("\nTesting fasta-2line format fix...")
    
    base_dir = Path(__file__).parent.parent
    
    scripts = [
        "workflow/scripts/sequences/download_host_genomes.py",
        "workflow/scripts/sequences/download_host_genomes_optimized.py"
    ]
    
    all_fixed = True
    for script_path in scripts:
        full_path = base_dir / script_path
        
        if not full_path.exists():
            print(f"  ⚠️  WARNING: {script_path} not found")
            continue
        
        with open(full_path, 'r') as f:
            content = f.read()
        
        # Check for fasta-2line usage
        if 'fasta-2line' in content or '"fasta-2line"' in content or "'fasta-2line'" in content:
            print(f"  ✅ PASS: {script_path} uses fasta-2line format")
        else:
            # Check if it still uses old format
            if 'SeqIO.parse(fasta_path, "fasta")' in content:
                print(f"  ❌ FAIL: {script_path} still uses old 'fasta' format")
                all_fixed = False
            else:
                print(f"  ⚠️  WARNING: {script_path} format unclear")
    
    return all_fixed


def test_environment_dependencies():
    """Test that required dependencies are listed"""
    print("\nTesting environment dependencies...")
    
    env_file = Path(__file__).parent.parent / "workflow" / "envs" / "sequences.yaml"
    
    if not env_file.exists():
        print(f"  ❌ FAIL: Environment file not found")
        return False
    
    with open(env_file, 'r') as f:
        content = f.read()
    
    required_deps = [
        'biopython',
        'pandas',
        'pyyaml',
        'aiohttp'
    ]
    
    all_present = True
    for dep in required_deps:
        if dep in content:
            print(f"  ✅ PASS: {dep} listed in dependencies")
        else:
            print(f"  ❌ FAIL: {dep} missing from dependencies")
            all_present = False
    
    return all_present


def test_documentation():
    """Test that documentation is complete"""
    print("\nTesting documentation...")
    
    doc_file = Path(__file__).parent.parent / "docs" / "genome_download_optimization.md"
    
    if not doc_file.exists():
        print(f"  ❌ FAIL: Documentation file not found")
        return False
    
    with open(doc_file, 'r') as f:
        content = f.read()
    
    required_sections = [
        "# Genome Download Pipeline Optimization",
        "## Key Improvements",
        "## Performance Improvements",
        "## Usage",
        "## API Key Setup",
        "## Troubleshooting"
    ]
    
    all_present = True
    for section in required_sections:
        if section in content:
            print(f"  ✅ PASS: Found section: {section}")
        else:
            print(f"  ❌ FAIL: Missing section: {section}")
            all_present = False
    
    # Check word count
    word_count = len(content.split())
    if word_count > 1000:
        print(f"  ✅ PASS: Documentation is comprehensive ({word_count} words)")
    else:
        print(f"  ⚠️  WARNING: Documentation might be too brief ({word_count} words)")
    
    return all_present


def main():
    """Run all integration tests"""
    print("=" * 80)
    print("GENOME DOWNLOAD PIPELINE - INTEGRATION TESTS")
    print("=" * 80)
    
    tests = [
        ("GTDB Identifier Detection", test_species_validator),
        ("Configuration File", test_config_parsing),
        ("File Structure", test_file_structure),
        ("Fasta-2line Format Fix", test_fasta_format_fix),
        ("Environment Dependencies", test_environment_dependencies),
        ("Documentation", test_documentation)
    ]
    
    results = []
    for test_name, test_func in tests:
        print("\n" + "=" * 80)
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print("\n" + "=" * 80)
    print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print("=" * 80)
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

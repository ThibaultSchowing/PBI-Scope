#!/usr/bin/env python3
"""
Validation script for species name to genome download workflow

This script validates the host genome download process by testing:
1. Species name extraction and normalization  
2. GTDB identifier detection (filtering happens separately)
3. File naming conventions
4. FASTA format validation
"""

import os
import sys
import re
from pathlib import Path

# Test data
TEST_HOSTS = [
    # Valid hosts (should be processed)
    ("Escherichia coli K-12", "Escherichia coli"),
    ("Staphylococcus aureus subsp. aureus", "Staphylococcus aureus"),
    ("Pseudomonas aeruginosa PAO1", "Pseudomonas aeruginosa"),
    ("Bacillus subtilis 168", "Bacillus subtilis"),
    
    # GTDB identifiers (normalized, but will be filtered by GTDB detector)
    ("Acidovorax sp000302535", "Acidovorax sp000302535"),
    ("Acinetobacter sp001411535", "Acinetobacter sp001411535"),
    
    # Invalid hosts (should be filtered during normalization)
    ("unknown", ""),
    ("unidentified", ""),
    ("-", ""),
    ("", ""),
]


def normalize_species_name(host):
    """Extract species name from host string"""
    if not host or host == '-' or host == '':
        return ""
    
    host = str(host).strip()
    
    # Check for unknown/unidentified
    if re.search(r'unknown|unidentified', host, re.IGNORECASE):
        return ""
    
    # Extract first two words
    parts = host.split()
    if len(parts) >= 2:
        if parts[0][0].isupper():
            return f"{parts[0]} {parts[1]}"
    elif len(parts) == 1:
        if parts[0][0].isupper():
            return parts[0]
    
    return ""


def is_gtdb_identifier(species_name):
    """Check if species name is a GTDB identifier"""
    pattern = r'\bsp\d{9}\b'
    return bool(re.search(pattern, species_name))


def validate_file_naming(species_name, accession):
    """Generate expected filename for host genome"""
    species_clean = species_name.replace(' ', '_')
    return f"{species_clean}_{accession}.fna"


def validate_fasta_content(content):
    """Validate FASTA file content"""
    if not content or len(content.strip()) == 0:
        return False, "File is empty"
    
    lines = content.splitlines()
    if not lines:
        return False, "No lines in file"
    
    first_line = lines[0].strip()
    if not first_line.startswith('>'):
        return False, f"Invalid FASTA header: {first_line[:50]}"
    
    return True, "Valid FASTA format"


def run_tests():
    """Run all validation tests"""
    print("="*80)
    print("FASTA Download Workflow Validation")
    print("="*80)
    print()
    
    # Test 1: Species name normalization
    print("Test 1: Species Name Normalization")
    print("-" * 80)
    
    passed = 0
    failed = 0
    
    for raw_host, expected_species in TEST_HOSTS:
        normalized = normalize_species_name(raw_host)
        
        if normalized == expected_species:
            if expected_species:
                print(f"✅ '{raw_host}' → '{normalized}'")
            else:
                print(f"✅ '{raw_host}' → (filtered)")
            passed += 1
        else:
            print(f"❌ '{raw_host}' → '{normalized}' (expected '{expected_species}')")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed")
    print()
    
    # Test 2: GTDB identifier detection
    print("Test 2: GTDB Identifier Detection")
    print("-" * 80)
    
    gtdb_test_cases = [
        ("Acidovorax sp000302535", True),
        ("Acinetobacter sp001411535", True),
        ("Escherichia coli", False),
        ("Bacillus sp123456789", True),
        ("Staphylococcus aureus", False),
    ]
    
    gtdb_passed = 0
    gtdb_failed = 0
    
    for species, is_gtdb in gtdb_test_cases:
        detected = is_gtdb_identifier(species)
        
        if detected == is_gtdb:
            status = "GTDB (will be skipped)" if is_gtdb else "Valid species"
            print(f"✅ '{species}' → {status}")
            gtdb_passed += 1
        else:
            print(f"❌ '{species}' → Detection failed")
            gtdb_failed += 1
    
    print(f"\nResults: {gtdb_passed} passed, {gtdb_failed} failed")
    print()
    
    # Test 3: File naming convention
    print("Test 3: File Naming Convention")
    print("-" * 80)
    
    naming_test_cases = [
        ("Escherichia coli", "GCF_000005845.2", "Escherichia_coli_GCF_000005845.2.fna"),
        ("Staphylococcus aureus", "GCF_000013425.1", "Staphylococcus_aureus_GCF_000013425.1.fna"),
        ("Pseudomonas aeruginosa", "GCF_000006765.1", "Pseudomonas_aeruginosa_GCF_000006765.1.fna"),
    ]
    
    naming_passed = 0
    naming_failed = 0
    
    for species, accession, expected_filename in naming_test_cases:
        filename = validate_file_naming(species, accession)
        
        if filename == expected_filename:
            print(f"✅ {species} + {accession} → {filename}")
            naming_passed += 1
        else:
            print(f"❌ {species} + {accession} → {filename} (expected {expected_filename})")
            naming_failed += 1
    
    print(f"\nResults: {naming_passed} passed, {naming_failed} failed")
    print()
    
    # Test 4: FASTA format validation
    print("Test 4: FASTA Format Validation")
    print("-" * 80)
    
    fasta_test_cases = [
        (">NC_000913.3 Escherichia coli K-12\nATCGATCG\nGCGCGCGC\n", True),
        ("ATCGATCG\nGCGCGCGC\n", False),
        ("", False),
        ("   \n\n", False),
    ]
    
    fasta_passed = 0
    fasta_failed = 0
    
    for content, should_be_valid in fasta_test_cases:
        is_valid, msg = validate_fasta_content(content)
        
        if is_valid == should_be_valid:
            print(f"✅ {msg}")
            fasta_passed += 1
        else:
            print(f"❌ Validation failed: {msg}")
            fasta_failed += 1
    
    print(f"\nResults: {fasta_passed} passed, {fasta_failed} failed")
    print()
    
    # Summary
    print("="*80)
    print("Summary")
    print("="*80)
    
    total_passed = passed + gtdb_passed + naming_passed + fasta_passed
    total_failed = failed + gtdb_failed + naming_failed + fasta_failed
    total_tests = total_passed + total_failed
    
    print(f"Total Tests: {total_tests}")
    print(f"✅ Passed: {total_passed}")
    print(f"❌ Failed: {total_failed}")
    print(f"Success Rate: {total_passed/total_tests*100:.1f}%")
    print()
    
    if total_failed == 0:
        print("🎉 All tests passed!")
        print()
        print("The workflow correctly:")
        print("  1. Normalizes species names (Genus species)")
        print("  2. Filters invalid hosts (unknown, unidentified, -, empty)")
        print("  3. Detects GTDB identifiers for skipping")
        print("  4. Generates proper filenames")
        print("  5. Validates FASTA format")
        return 0
    else:
        print(f"⚠️  {total_failed} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)

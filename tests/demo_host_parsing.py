#!/usr/bin/env python3
"""
Demonstration script showing improved host field parsing

This script demonstrates how the improved parsing handles the problematic
cases mentioned in the issue.
"""

import sys
from pathlib import Path

# Add workflow scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"))

from assembly_resolver import AssemblyResolver, IdentifierType


def demonstrate_parsing():
    """Demonstrate the parsing improvements"""
    
    print("=" * 80)
    print("Host Field Parsing Demonstration")
    print("=" * 80)
    print()
    
    # Initialize resolver
    resolver = AssemblyResolver(email='demo@example.org')
    
    # Examples from the problem statement
    test_cases = [
        "NA;GCA 900066365.1;Lachnospira",
        "NA;GCA 900066365.1;Roseburia",
        "NA;GCA 900066365.1;Ruminococcus",
        "NA;GCA 900066545.1;Dorea",
        "NA;GCA 900066545.1;GCA",
        "NA;GCA 900066745.1;Coprococcus",
        "NA;GCA 900066745.1;Lachnospira",
        "NA;GCA 900066335.1;UBA9502;Blautia",
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}: '{test_case}'")
        print("-" * 80)
        
        # Parse the field
        parsed = resolver.parse_host_field(test_case)
        
        print(f"✅ Parsed into {len(parsed)} identifiers:")
        for j, (identifier, id_type) in enumerate(parsed, 1):
            print(f"   {j}. '{identifier}' (type: {id_type.value})")
        
        if parsed:
            print(f"\n🎯 Resolution strategy:")
            print(f"   Will try '{parsed[0][0]}' first ({parsed[0][1].value})")
            if len(parsed) > 1:
                print(f"   Fallback options: {len(parsed) - 1}")
                for j, (identifier, id_type) in enumerate(parsed[1:], 2):
                    print(f"      {j}. '{identifier}' ({id_type.value})")
        
        print()
    
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print()
    print("Before: All fields treated as species names like:")
    print("  'NA;GCA 900066365.1;Lachnospira' → FAILED (not a valid species name)")
    print()
    print("After: Fields are parsed and prioritized:")
    print("  1. Extract GCA accession: 'GCA_900066365.1' (fixed space)")
    print("  2. Extract species name: 'Lachnospira'")
    print("  3. Try GCA accession first → SUCCESS")
    print("  4. If failed, fallback to species name")
    print()
    print("🎉 This maximizes chances of finding a genome for each phage!")
    print()


if __name__ == '__main__':
    demonstrate_parsing()

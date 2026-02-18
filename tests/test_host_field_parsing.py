#!/usr/bin/env python3
"""
Test host field parsing functionality

This test suite validates the new host field parsing that handles
semicolon-separated values and GCA accessions with spaces.
"""

import os
import sys
import unittest
from pathlib import Path

# Add workflow scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"))

from assembly_resolver import (
    AssemblyResolver,
    IdentifierType
)


class TestHostFieldParsing(unittest.TestCase):
    """Test cases for host field parsing"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        cls.ncbi_email = os.environ.get('NCBI_EMAIL', 'pbi-test@example.org')
        cls.ncbi_api_key = os.environ.get('NCBI_API_KEY', None)
        
        # Initialize resolver
        cls.resolver = AssemblyResolver(
            email=cls.ncbi_email,
            api_key=cls.ncbi_api_key
        )
    
    def test_parse_simple_species_name(self):
        """Test parsing a simple species name"""
        result = self.resolver.parse_host_field("Escherichia coli")
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "Escherichia coli")
        self.assertEqual(result[0][1], IdentifierType.SPECIES_NAME)
    
    def test_parse_gca_with_space(self):
        """Test parsing GCA accession with space instead of underscore"""
        result = self.resolver.parse_host_field("GCA 900066335.1")
        
        self.assertEqual(len(result), 1)
        # Should be converted to GCA_900066335.1
        self.assertEqual(result[0][0], "GCA_900066335.1")
        self.assertEqual(result[0][1], IdentifierType.ASSEMBLY_ACCESSION)
    
    def test_parse_gcf_with_space(self):
        """Test parsing GCF accession with space instead of underscore"""
        result = self.resolver.parse_host_field("GCF 000005845.2")
        
        self.assertEqual(len(result), 1)
        # Should be converted to GCF_000005845.2
        self.assertEqual(result[0][0], "GCF_000005845.2")
        self.assertEqual(result[0][1], IdentifierType.ASSEMBLY_ACCESSION)
    
    def test_parse_semicolon_separated_with_na(self):
        """Test parsing semicolon-separated field with NA values"""
        # Example from the problem statement
        result = self.resolver.parse_host_field("NA;GCA 900066365.1;Lachnospira")
        
        # Should have 2 results (NA filtered out)
        self.assertEqual(len(result), 2)
        
        # First should be the assembly accession (highest priority)
        self.assertEqual(result[0][0], "GCA_900066365.1")
        self.assertEqual(result[0][1], IdentifierType.ASSEMBLY_ACCESSION)
        
        # Second should be the species name
        self.assertEqual(result[1][0], "Lachnospira")
        self.assertEqual(result[1][1], IdentifierType.SPECIES_NAME)
    
    def test_parse_complex_semicolon_separated(self):
        """Test parsing complex semicolon-separated field"""
        result = self.resolver.parse_host_field("NA;GCA 900066335.1;UBA9502;Blautia")
        
        # Should filter out NA and UBA9502 (unknown type)
        # Should have GCA accession and Blautia
        self.assertGreaterEqual(len(result), 1)
        
        # First should be the assembly accession
        self.assertEqual(result[0][0], "GCA_900066335.1")
        self.assertEqual(result[0][1], IdentifierType.ASSEMBLY_ACCESSION)
    
    def test_parse_empty_field(self):
        """Test parsing empty or null fields"""
        self.assertEqual(self.resolver.parse_host_field(""), [])
        self.assertEqual(self.resolver.parse_host_field(None), [])
        self.assertEqual(self.resolver.parse_host_field("NA"), [])
        self.assertEqual(self.resolver.parse_host_field("-"), [])
    
    def test_parse_only_na_values(self):
        """Test parsing field with only NA values"""
        result = self.resolver.parse_host_field("NA;NA;NA")
        self.assertEqual(result, [])
    
    def test_priority_ordering(self):
        """Test that identifiers are returned in priority order"""
        # Create a field with various identifier types
        # Assembly accession should come first
        result = self.resolver.parse_host_field("Escherichia coli;GCA 000005845.2;SAMN02604091")
        
        self.assertGreaterEqual(len(result), 2)
        
        # Assembly accession should be first (highest priority)
        self.assertEqual(result[0][1], IdentifierType.ASSEMBLY_ACCESSION)
        
        # BioSample should be second
        if len(result) > 1:
            self.assertEqual(result[1][1], IdentifierType.BIOSAMPLE)
    
    def test_gca_embedded_in_text(self):
        """Test that GCA with space is fixed even when embedded in text"""
        result = self.resolver.parse_host_field("Some text GCA 900066365.1 more text")
        
        # The whole string should be processed and the GCA fixed
        # Since the whole string doesn't match any pattern exactly, 
        # it will be treated as species name, but the GCA should still be normalized
        self.assertEqual(len(result), 1)
        # The normalized field should have GCA_ instead of "GCA "
        self.assertIn("GCA_900066365.1", result[0][0])
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_resolve_with_fallback_simple(self):
        """Test resolve_with_fallback with a simple species name"""
        assemblies = self.resolver.resolve_with_fallback(
            "Escherichia coli",
            max_results=1
        )
        
        self.assertGreater(len(assemblies), 0)
        self.assertIn("Escherichia", assemblies[0].organism_name)
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_resolve_with_fallback_gca_with_space(self):
        """Test resolve_with_fallback with GCA accession that has a space"""
        # Use E. coli K12 GCF (well-known reference)
        assemblies = self.resolver.resolve_with_fallback(
            "GCF 000005845.2",  # Space instead of underscore
            max_results=1
        )
        
        self.assertEqual(len(assemblies), 1)
        self.assertEqual(assemblies[0].assembly_accession, "GCF_000005845.2")
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_resolve_with_fallback_complex_field(self):
        """Test resolve_with_fallback with complex semicolon-separated field"""
        # This should try the GCF first (highest priority) and succeed
        assemblies = self.resolver.resolve_with_fallback(
            "NA;GCF 000005845.2;SomeUnknown;Escherichia coli",
            max_results=1
        )
        
        self.assertEqual(len(assemblies), 1)
        # Should resolve to the GCF accession
        self.assertEqual(assemblies[0].assembly_accession, "GCF_000005845.2")


def main():
    """Run tests"""
    if not os.environ.get('NCBI_EMAIL'):
        print("=" * 70)
        print("⚠️  NCBI_EMAIL not set - skipping API tests")
        print("   To run full tests, set NCBI_EMAIL environment variable")
        print("=" * 70)
    
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()

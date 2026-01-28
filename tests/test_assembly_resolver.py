#!/usr/bin/env python3
"""
Test the AssemblyResolver class for robust genome retrieval

This test suite validates the assembly resolver functionality:
- Identifier type detection
- Assembly resolution from various identifier types
- Quality-based ranking
- Ambiguity handling
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add workflow scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"))

from assembly_resolver import (
    AssemblyResolver,
    IdentifierType,
    AssemblyMetadata,
    AssemblyLevel,
    RefSeqCategory
)


class TestAssemblyResolver(unittest.TestCase):
    """Test cases for AssemblyResolver"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        # Use environment variables or clearly marked test email
        cls.ncbi_email = os.environ.get('NCBI_EMAIL', 'pbi-test@example.org')
        cls.ncbi_api_key = os.environ.get('NCBI_API_KEY', None)
        
        # Initialize resolver
        cls.resolver = AssemblyResolver(
            email=cls.ncbi_email,
            api_key=cls.ncbi_api_key
        )
    
    def test_identifier_type_detection(self):
        """Test detection of different identifier types"""
        # Assembly accessions
        self.assertEqual(
            self.resolver.identify_type("GCF_000005845.2"),
            IdentifierType.ASSEMBLY_ACCESSION
        )
        self.assertEqual(
            self.resolver.identify_type("GCA_000001405.29"),
            IdentifierType.ASSEMBLY_ACCESSION
        )
        
        # BioSample
        self.assertEqual(
            self.resolver.identify_type("SAMN02604091"),
            IdentifierType.BIOSAMPLE
        )
        
        # BioProject
        self.assertEqual(
            self.resolver.identify_type("PRJNA224116"),
            IdentifierType.BIOPROJECT
        )
        
        # TaxID
        self.assertEqual(
            self.resolver.identify_type("562"),
            IdentifierType.TAXID
        )
        
        # Species name
        self.assertEqual(
            self.resolver.identify_type("Escherichia coli"),
            IdentifierType.SPECIES_NAME
        )
        self.assertEqual(
            self.resolver.identify_type("Staphylococcus"),
            IdentifierType.SPECIES_NAME
        )
    
    def test_assembly_metadata_quality_score(self):
        """Test quality score calculation"""
        # Reference genome, complete
        metadata1 = AssemblyMetadata(
            assembly_accession="GCF_000005845.2",
            assembly_name="ASM584v2",
            organism_name="Escherichia coli str. K-12 substr. MG1655",
            assembly_level="Complete Genome",
            refseq_category="reference genome",
            is_latest=True
        )
        
        # Representative genome, chromosome
        metadata2 = AssemblyMetadata(
            assembly_accession="GCF_000006945.2",
            assembly_name="ASM694v2",
            organism_name="Salmonella enterica",
            assembly_level="Chromosome",
            refseq_category="representative genome",
            is_latest=True
        )
        
        # Contig level, no refseq category
        metadata3 = AssemblyMetadata(
            assembly_accession="GCA_000001405.1",
            assembly_name="Test",
            organism_name="Test organism",
            assembly_level="Contig",
            refseq_category="na",
            is_latest=False
        )
        
        # Reference complete should score highest
        self.assertGreater(metadata1.get_quality_score(), metadata2.get_quality_score())
        self.assertGreater(metadata2.get_quality_score(), metadata3.get_quality_score())
    
    def test_assembly_is_refseq(self):
        """Test RefSeq vs GenBank detection"""
        refseq = AssemblyMetadata(
            assembly_accession="GCF_000005845.2",
            assembly_name="ASM584v2",
            organism_name="E. coli"
        )
        
        genbank = AssemblyMetadata(
            assembly_accession="GCA_000005845.1",
            assembly_name="ASM584v1",
            organism_name="E. coli"
        )
        
        self.assertTrue(refseq.is_refseq())
        self.assertFalse(refseq.is_genbank())
        
        self.assertFalse(genbank.is_refseq())
        self.assertTrue(genbank.is_genbank())
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_resolve_assembly_accession(self):
        """Test resolution of assembly accession"""
        # E. coli K12 reference genome
        assemblies = self.resolver.resolve("GCF_000005845.2")
        
        self.assertEqual(len(assemblies), 1)
        self.assertEqual(assemblies[0].assembly_accession, "GCF_000005845.2")
        self.assertTrue(assemblies[0].is_refseq())
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_resolve_species_name(self):
        """Test resolution of species name"""
        # Well-known species should resolve
        assemblies = self.resolver.resolve(
            "Escherichia coli",
            max_results=5
        )
        
        self.assertGreater(len(assemblies), 0)
        
        # First result should be highest quality (likely K12 reference)
        best = assemblies[0]
        self.assertTrue(best.is_refseq())
        self.assertIn("Escherichia", best.organism_name)
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_get_best_assembly(self):
        """Test convenience method for getting best assembly"""
        assembly = self.resolver.get_best_assembly(
            "Bacillus subtilis",
            prefer_refseq=True
        )
        
        if assembly:  # May not find anything
            self.assertTrue(assembly.is_refseq())
            self.assertIn("Bacillus", assembly.organism_name)
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_ambiguity_handling(self):
        """Test that ambiguous species names are handled"""
        # This test just ensures no exceptions are raised
        # Actual ambiguity is logged, not raised
        try:
            assemblies = self.resolver.resolve(
                "Streptococcus",  # Genus only - highly ambiguous
                max_results=3
            )
            # Should either return results or empty list, not crash
            self.assertIsInstance(assemblies, list)
        except Exception as e:
            self.fail(f"Ambiguous name handling failed: {e}")
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_invalid_identifier(self):
        """Test handling of invalid identifiers"""
        assemblies = self.resolver.resolve("INVALID_ID_12345")
        self.assertEqual(len(assemblies), 0)


class TestAssemblyLevelEnum(unittest.TestCase):
    """Test AssemblyLevel enum"""
    
    def test_priority_ordering(self):
        """Test that priority values are correctly ordered"""
        self.assertGreater(
            AssemblyLevel.COMPLETE_GENOME.priority,
            AssemblyLevel.CHROMOSOME.priority
        )
        self.assertGreater(
            AssemblyLevel.CHROMOSOME.priority,
            AssemblyLevel.SCAFFOLD.priority
        )
        self.assertGreater(
            AssemblyLevel.SCAFFOLD.priority,
            AssemblyLevel.CONTIG.priority
        )


class TestRefSeqCategoryEnum(unittest.TestCase):
    """Test RefSeqCategory enum"""
    
    def test_priority_ordering(self):
        """Test that priority values are correctly ordered"""
        self.assertGreater(
            RefSeqCategory.REFERENCE.priority,
            RefSeqCategory.REPRESENTATIVE.priority
        )
        self.assertGreater(
            RefSeqCategory.REPRESENTATIVE.priority,
            RefSeqCategory.NA.priority
        )


def main():
    """Run tests"""
    # Check if we should skip API tests
    if not os.environ.get('NCBI_EMAIL'):
        print("=" * 70)
        print("⚠️  NCBI_EMAIL not set - skipping API tests")
        print("   To run full tests, set NCBI_EMAIL environment variable")
        print("=" * 70)
    
    unittest.main(verbosity=2)


if __name__ == '__main__':
    main()

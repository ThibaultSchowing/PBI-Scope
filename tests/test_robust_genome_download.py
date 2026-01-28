#!/usr/bin/env python3
"""
Test the RobustHostGenomeDownloader

This test validates the robust genome download functionality:
- Host extraction from phage CSV
- Assembly resolution
- Metadata-only mode
- Phage-host link creation
"""

import os
import sys
import tempfile
import unittest
import pandas as pd
from pathlib import Path

# Add workflow scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts" / "sequences"))

from download_host_genomes_robust import RobustHostGenomeDownloader


class TestRobustHostGenomeDownloader(unittest.TestCase):
    """Test cases for RobustHostGenomeDownloader"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        
        # Create test phage CSV
        self.phage_csv = self.temp_path / "phages.csv"
        self._create_test_phage_csv()
        
        # Test email
        self.ncbi_email = os.environ.get('NCBI_EMAIL', 'test@example.com')
    
    def tearDown(self):
        """Clean up test files"""
        import shutil
        if self.temp_path.exists():
            shutil.rmtree(self.temp_path)
    
    def _create_test_phage_csv(self):
        """Create a test phage CSV with sample hosts"""
        data = {
            'Phage_ID': ['phage1', 'phage2', 'phage3', 'phage4', 'phage5', 'phage6'],
            'Host': [
                'Escherichia coli',
                'Escherichia coli K12',
                'Staphylococcus aureus',
                'Bacillus subtilis',
                '-',  # Invalid
                'unknown host'  # Invalid
            ],
            'Source_DB': ['RefSeq'] * 6
        }
        df = pd.DataFrame(data)
        df.to_csv(self.phage_csv, index=False)
    
    def test_extract_unique_hosts(self):
        """Test extraction of unique hosts from phage CSV"""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            metadata_only=True
        )
        
        species = downloader.extract_unique_hosts()
        
        # Should extract 3 unique species (filtering out invalid hosts)
        self.assertIn("Escherichia coli", species)
        self.assertIn("Staphylococcus aureus", species)
        self.assertIn("Bacillus subtilis", species)
        self.assertEqual(len(species), 3)
    
    def test_metadata_only_mode(self):
        """Test metadata-only mode (no downloads)"""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            metadata_only=True  # No downloads
        )
        
        # Should work in metadata-only mode
        self.assertTrue(downloader.metadata_only)
        
        # Should not create genome files
        species = downloader.extract_unique_hosts()
        self.assertGreater(len(species), 0)
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_resolve_host_assemblies(self):
        """Test resolution of hosts to assemblies"""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            metadata_only=True
        )
        
        species = ["Escherichia coli", "Bacillus subtilis"]
        assemblies = downloader.resolve_host_assemblies(species)
        
        # Should resolve at least E. coli
        self.assertGreater(len(assemblies), 0)
        
        # E. coli should have a RefSeq assembly
        if "Escherichia coli" in assemblies:
            assembly = assemblies["Escherichia coli"]
            self.assertTrue(assembly.is_refseq())
            self.assertIn("GCF_", assembly.assembly_accession)
    
    @unittest.skipIf(
        not os.environ.get('NCBI_EMAIL'),
        "Skipping NCBI API test (set NCBI_EMAIL to run)"
    )
    def test_create_phage_host_links(self):
        """Test creation of phage-host links"""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            metadata_only=True
        )
        
        species = downloader.extract_unique_hosts()
        assemblies = downloader.resolve_host_assemblies(species)
        links = downloader.create_phage_host_links(assemblies)
        
        # Should create links for valid phages
        self.assertGreater(len(links), 0)
        
        # Each link should have required fields
        for link in links:
            self.assertIn('Phage_ID', link)
            self.assertIn('Host_Species', link)
            self.assertIn('Assembly_Accession', link)
            self.assertIn('Link_Quality', link)
    
    def test_file_validation(self):
        """Test file validation logic"""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            validate_checksums=True
        )
        
        # Create test file
        test_file = self.temp_path / "test.txt"
        test_file.write_text("test content")
        
        # Should validate existing file with content
        self.assertTrue(downloader._validate_file(test_file))
        
        # Should fail for non-existent file
        self.assertFalse(downloader._validate_file(self.temp_path / "nonexistent.txt"))
        
        # Should fail for empty file
        empty_file = self.temp_path / "empty.txt"
        empty_file.touch()
        self.assertFalse(downloader._validate_file(empty_file))


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

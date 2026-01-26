#!/usr/bin/env python3
"""
Unit tests for FASTA validation in genome download methods
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'workflow' / 'scripts' / 'sequences'))

from download_host_genomes import HostGenomeDownloader
from download_host_genomes_optimized import HostGenomeDownloaderOptimized


class TestFASTAValidationBasic(unittest.TestCase):
    """Test FASTA validation in download_host_genomes.py"""
    
    def setUp(self):
        """Create temporary directory and downloader instance"""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_csv = Path(self.temp_dir) / "phage.csv"
        
        # Create minimal CSV for downloader initialization
        with open(self.temp_csv, 'w') as f:
            f.write("Host\n")
            f.write("Escherichia coli\n")
        
        self.downloader = HostGenomeDownloader(
            phage_csv_path=str(self.temp_csv),
            output_dir=str(self.temp_dir),
            metadata_output=str(Path(self.temp_dir) / "metadata.csv"),
            ncbi_email="test@example.com"
        )
    
    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @patch('download_host_genomes.Entrez.esearch')
    @patch('download_host_genomes.Entrez.efetch')
    @patch('download_host_genomes.Entrez.read')
    def test_valid_fasta_accepted(self, mock_read, mock_efetch, mock_esearch):
        """Test that valid FASTA format is accepted"""
        # Mock esearch response
        mock_esearch_handle = MagicMock()
        mock_esearch.return_value = mock_esearch_handle
        mock_read.return_value = {'IdList': ['12345']}
        
        # Mock efetch response with valid FASTA
        mock_efetch_handle = MagicMock()
        valid_fasta = ">seq1 Test sequence\nATCGATCGATCG\nATCGATCGATCG\n"
        mock_efetch_handle.read.return_value = valid_fasta
        mock_efetch.return_value = mock_efetch_handle
        
        # Test download
        output_path = Path(self.temp_dir) / "test_valid.fna"
        result = self.downloader.download_genome_entrez("GCF_000005845.2", output_path)
        
        # Verify
        self.assertTrue(result, "Valid FASTA should be accepted")
        self.assertTrue(output_path.exists(), "File should be created")
        
        # Verify file content
        with open(output_path, 'r') as f:
            content = f.read()
            self.assertTrue(content.startswith('>'), "File should start with >")
    
    @patch('download_host_genomes.Entrez.esearch')
    @patch('download_host_genomes.Entrez.efetch')
    @patch('download_host_genomes.Entrez.read')
    def test_invalid_fasta_rejected(self, mock_read, mock_efetch, mock_esearch):
        """Test that invalid FASTA format (missing >) is rejected"""
        # Mock esearch response
        mock_esearch_handle = MagicMock()
        mock_esearch.return_value = mock_esearch_handle
        mock_read.return_value = {'IdList': ['12345']}
        
        # Mock efetch response with invalid FASTA (no header)
        mock_efetch_handle = MagicMock()
        invalid_fasta = "ATCGATCGATCG\nATCGATCGATCG\n"
        mock_efetch_handle.read.return_value = invalid_fasta
        mock_efetch.return_value = mock_efetch_handle
        
        # Test download
        output_path = Path(self.temp_dir) / "test_invalid.fna"
        result = self.downloader.download_genome_entrez("GCF_000005845.2", output_path)
        
        # Verify - should reject invalid format
        self.assertFalse(result, "Invalid FASTA should be rejected")
    
    @patch('download_host_genomes.Entrez.esearch')
    @patch('download_host_genomes.Entrez.efetch')
    @patch('download_host_genomes.Entrez.read')
    def test_empty_file_rejected(self, mock_read, mock_efetch, mock_esearch):
        """Test that empty files are rejected"""
        # Mock esearch response
        mock_esearch_handle = MagicMock()
        mock_esearch.return_value = mock_esearch_handle
        mock_read.return_value = {'IdList': ['12345']}
        
        # Mock efetch response with empty content
        mock_efetch_handle = MagicMock()
        mock_efetch_handle.read.return_value = ""
        mock_efetch.return_value = mock_efetch_handle
        
        # Test download
        output_path = Path(self.temp_dir) / "test_empty.fna"
        result = self.downloader.download_genome_entrez("GCF_000005845.2", output_path)
        
        # Verify - should reject empty file
        self.assertFalse(result, "Empty file should be rejected")
    
    @patch('download_host_genomes.Entrez.esearch')
    @patch('download_host_genomes.Entrez.read')
    def test_no_id_list_rejected(self, mock_read, mock_esearch):
        """Test that missing IdList is handled"""
        # Mock esearch response with no results
        mock_esearch_handle = MagicMock()
        mock_esearch.return_value = mock_esearch_handle
        mock_read.return_value = {'IdList': []}
        
        # Test download
        output_path = Path(self.temp_dir) / "test_noid.fna"
        result = self.downloader.download_genome_entrez("GCF_000000000.0", output_path)
        
        # Verify - should return False
        self.assertFalse(result, "No IdList should return False")


class TestFASTAValidationOptimized(unittest.TestCase):
    """Test FASTA validation in download_host_genomes_optimized.py"""
    
    def setUp(self):
        """Create temporary directory and downloader instance"""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir) / "genomes"
        self.metadata_db = Path(self.temp_dir) / "metadata.db"
        
        self.downloader = HostGenomeDownloaderOptimized(
            cache_dir=str(self.cache_dir),
            metadata_db=str(self.metadata_db),
            ncbi_email="test@example.com"
        )
    
    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    @patch('download_host_genomes_optimized.Entrez.esearch')
    @patch('download_host_genomes_optimized.Entrez.efetch')
    @patch('download_host_genomes_optimized.Entrez.read')
    def test_valid_fasta_accepted(self, mock_read, mock_efetch, mock_esearch):
        """Test that valid FASTA format is accepted"""
        # Mock esearch response
        mock_esearch_handle = MagicMock()
        mock_esearch.return_value = mock_esearch_handle
        mock_read.return_value = {'IdList': ['12345']}
        
        # Mock efetch response with valid FASTA
        mock_efetch_handle = MagicMock()
        valid_fasta = ">seq1 Test sequence\nATCGATCGATCG\nATCGATCGATCG\n"
        mock_efetch_handle.read.return_value = valid_fasta
        mock_efetch.return_value = mock_efetch_handle
        
        # Test download
        output_path = Path(self.temp_dir) / "test_valid.fna"
        result = self.downloader.download_genome_entrez("GCF_000005845.2", output_path)
        
        # Verify
        self.assertTrue(result, "Valid FASTA should be accepted")
        self.assertTrue(output_path.exists(), "File should be created")
        
        # Verify file content
        with open(output_path, 'r') as f:
            content = f.read()
            self.assertTrue(content.startswith('>'), "File should start with >")
    
    @patch('download_host_genomes_optimized.Entrez.esearch')
    @patch('download_host_genomes_optimized.Entrez.efetch')
    @patch('download_host_genomes_optimized.Entrez.read')
    def test_invalid_fasta_rejected(self, mock_read, mock_efetch, mock_esearch):
        """Test that invalid FASTA format (missing >) is rejected"""
        # Mock esearch response
        mock_esearch_handle = MagicMock()
        mock_esearch.return_value = mock_esearch_handle
        mock_read.return_value = {'IdList': ['12345']}
        
        # Mock efetch response with invalid FASTA (no header)
        mock_efetch_handle = MagicMock()
        invalid_fasta = "ATCGATCGATCG\nATCGATCGATCG\n"
        mock_efetch_handle.read.return_value = invalid_fasta
        mock_efetch.return_value = mock_efetch_handle
        
        # Test download
        output_path = Path(self.temp_dir) / "test_invalid.fna"
        result = self.downloader.download_genome_entrez("GCF_000005845.2", output_path)
        
        # Verify - should reject invalid format
        self.assertFalse(result, "Invalid FASTA should be rejected")


if __name__ == '__main__':
    unittest.main(verbosity=2)

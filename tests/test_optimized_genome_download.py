#!/usr/bin/env python3
"""
Unit tests for optimized genome download components
"""

import os
import sys
import tempfile
import sqlite3
import time
from pathlib import Path
import unittest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'workflow' / 'scripts' / 'sequences'))

from download_host_genomes_optimized import (
    SpeciesValidator, 
    CacheManager, 
    RateLimiter,
    ProgressTracker
)


class TestSpeciesValidator(unittest.TestCase):
    """Test species name validation"""
    
    def setUp(self):
        self.validator = SpeciesValidator()
    
    def test_valid_species_names(self):
        """Test that valid species names pass validation"""
        valid_names = [
            "Escherichia coli",
            "Staphylococcus aureus",
            "Pseudomonas aeruginosa",
            "Bacillus",
            "Mycobacterium tuberculosis"
        ]
        
        for name in valid_names:
            is_valid, reason = self.validator.is_valid_species_name(name)
            self.assertTrue(is_valid, f"{name} should be valid but got: {reason}")
    
    def test_gtdb_identifiers_rejected(self):
        """Test that GTDB identifiers are rejected"""
        gtdb_names = [
            "Acidovorax sp000302535",
            "sp001411535",
            "Bacteria sp123456789",
            "Unknown sp000000001"
        ]
        
        for name in gtdb_names:
            is_valid, reason = self.validator.is_valid_species_name(name)
            self.assertFalse(is_valid, f"{name} should be invalid")
            self.assertIn("GTDB", reason)
    
    def test_invalid_format_rejected(self):
        """Test that invalid formats are rejected"""
        # Lowercase genus
        is_valid, reason = self.validator.is_valid_species_name("escherichia coli")
        self.assertFalse(is_valid)
        self.assertIn("capitalized", reason)
        
        # Empty
        is_valid, reason = self.validator.is_valid_species_name("")
        self.assertFalse(is_valid)
        self.assertIn("Empty", reason)
    
    def test_edge_cases(self):
        """Test edge cases"""
        # Single capitalized word (genus only)
        is_valid, reason = self.validator.is_valid_species_name("Bacillus")
        self.assertTrue(is_valid)
        
        # Extra strain info (should still pass)
        is_valid, reason = self.validator.is_valid_species_name("Escherichia coli K12")
        self.assertTrue(is_valid)


class TestCacheManager(unittest.TestCase):
    """Test cache management"""
    
    def setUp(self):
        """Create temporary cache directory and database"""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir) / "genomes"
        self.metadata_db = Path(self.temp_dir) / "metadata.db"
        
        self.cache_manager = CacheManager(
            str(self.cache_dir),
            str(self.metadata_db)
        )
    
    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_cache_initialization(self):
        """Test that cache is properly initialized"""
        # Check directory created
        self.assertTrue(self.cache_dir.exists())
        
        # Check database created
        self.assertTrue(self.metadata_db.exists())
        
        # Check schema
        conn = sqlite3.connect(self.metadata_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        self.assertIn('genomes', tables)
        conn.close()
    
    def test_save_and_retrieve_metadata(self):
        """Test saving and retrieving metadata"""
        # Create test metadata
        metadata = {
            'Host_ID': 'Escherichia_coli_GCF_000005845.2',
            'Species_Name': 'Escherichia coli',
            'Strain_Name': 'K-12',
            'Assembly_Accession': 'GCF_000005845.2',
            'Assembly_Name': 'ASM584v2',
            'Assembly_Level': 'Complete Genome',
            'Genome_Length': 4641652,
            'GC_Content': 50.79,
            'RefSeq_Category': 'reference genome',
            'Download_Date': '2026-01-26',
            'Source': 'entrez_api'
        }
        
        # Create dummy file
        file_path = self.cache_dir / f"{metadata['Host_ID']}.fna"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(">test\nATCG\n")
        
        # Save metadata
        self.cache_manager.save_metadata(metadata, 'success')
        
        # Retrieve metadata
        cached = self.cache_manager.is_cached('Escherichia coli')
        
        # Verify
        self.assertIsNotNone(cached)
        self.assertEqual(cached['Host_ID'], metadata['Host_ID'])
        self.assertEqual(cached['Assembly_Accession'], metadata['Assembly_Accession'])
    
    def test_cache_miss(self):
        """Test that cache correctly returns None for missing species"""
        cached = self.cache_manager.is_cached('Nonexistent species')
        self.assertIsNone(cached)
    
    def test_get_all_successful(self):
        """Test retrieving all successful downloads"""
        # Add multiple entries
        species_list = [
            ('Escherichia coli', 'GCF_000005845.2'),
            ('Staphylococcus aureus', 'GCF_000013425.1'),
            ('Pseudomonas aeruginosa', 'GCF_000006765.1')
        ]
        
        for species, accession in species_list:
            metadata = {
                'Host_ID': f"{species.replace(' ', '_')}_{accession}",
                'Species_Name': species,
                'Assembly_Accession': accession,
                'Genome_Length': 1000000,
                'GC_Content': 50.0
            }
            
            # Create dummy file
            file_path = self.cache_dir / f"{metadata['Host_ID']}.fna"
            file_path.write_text(">test\nATCG\n")
            
            self.cache_manager.save_metadata(metadata, 'success')
        
        # Get all successful
        all_successful = self.cache_manager.get_all_successful()
        
        # Verify
        self.assertEqual(len(all_successful), 3)
        species_names = [item['Species_Name'] for item in all_successful]
        self.assertIn('Escherichia coli', species_names)


class TestRateLimiter(unittest.TestCase):
    """Test rate limiting"""
    
    def test_rate_limiting(self):
        """Test that rate limiter enforces limits"""
        # Create limiter with 5 requests per second
        limiter = RateLimiter(requests_per_second=5.0)
        
        # Should allow 5 requests immediately
        start = time.time()
        for _ in range(5):
            limiter.acquire_sync()
        elapsed = time.time() - start
        
        # Should be almost instant (< 0.1 seconds)
        self.assertLess(elapsed, 0.1)
        
        # 6th request should be delayed
        start = time.time()
        limiter.acquire_sync()
        elapsed = time.time() - start
        
        # Should wait at least 0.1 seconds (1/5 = 0.2s per token)
        self.assertGreater(elapsed, 0.05)
    
    def test_token_refill(self):
        """Test that tokens are refilled over time"""
        limiter = RateLimiter(requests_per_second=10.0)
        
        # Consume all tokens
        for _ in range(10):
            limiter.acquire_sync()
        
        # Wait for refill
        time.sleep(0.5)
        
        # Should have ~5 tokens available now
        start = time.time()
        for _ in range(5):
            limiter.acquire_sync()
        elapsed = time.time() - start
        
        # Should be almost instant
        self.assertLess(elapsed, 0.1)


class TestProgressTracker(unittest.TestCase):
    """Test progress tracking"""
    
    def setUp(self):
        """Create temporary progress file"""
        self.temp_dir = tempfile.mkdtemp()
        self.progress_file = Path(self.temp_dir) / "progress.json"
    
    def tearDown(self):
        """Clean up"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_progress_updates(self):
        """Test progress tracking updates"""
        tracker = ProgressTracker(total=100, save_file=str(self.progress_file))
        
        # Update with success
        tracker.update('success')
        self.assertEqual(tracker.successful, 1)
        
        # Update with cached
        tracker.update('cached')
        self.assertEqual(tracker.cached, 1)
        
        # Update with failure
        tracker.update('failed', 'No assembly found')
        self.assertEqual(tracker.failed, 1)
        self.assertEqual(tracker.failure_categories['No assembly found'], 1)
        
        # Update with skipped
        tracker.update('skipped')
        self.assertEqual(tracker.skipped, 1)
    
    def test_statistics(self):
        """Test statistics calculation"""
        SUCCESSFUL_COUNT = 50
        CACHED_COUNT = 10
        FAILED_COUNT = 5
        TOTAL_COUNT = 100
        EXPECTED_COMPLETED = SUCCESSFUL_COUNT + CACHED_COUNT + FAILED_COUNT
        EXPECTED_PERCENTAGE = 65.0
        
        tracker = ProgressTracker(total=TOTAL_COUNT)
        
        # Add some progress
        for _ in range(SUCCESSFUL_COUNT):
            tracker.update('success')
        for _ in range(CACHED_COUNT):
            tracker.update('cached')
        for _ in range(FAILED_COUNT):
            tracker.update('failed', 'Download failed')
        
        stats = tracker.get_stats()
        
        # Verify
        self.assertEqual(stats['total'], TOTAL_COUNT)
        self.assertEqual(stats['completed'], EXPECTED_COMPLETED)
        self.assertEqual(stats['successful'], SUCCESSFUL_COUNT)
        self.assertEqual(stats['cached'], CACHED_COUNT)
        self.assertEqual(stats['failed'], FAILED_COUNT)
        self.assertEqual(stats['percentage'], EXPECTED_PERCENTAGE)
    
    def test_progress_file_saved(self):
        """Test that progress is saved to file"""
        tracker = ProgressTracker(total=10, save_file=str(self.progress_file))
        
        tracker.update('success')
        tracker.update('cached')
        
        # Verify file was created
        self.assertTrue(self.progress_file.exists())
        
        # Verify content
        import json
        with open(self.progress_file, 'r') as f:
            state = json.load(f)
        
        self.assertEqual(state['successful'], 1)
        self.assertEqual(state['cached'], 1)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)

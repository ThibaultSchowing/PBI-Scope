#!/usr/bin/env python3
"""
Test the RobustHostGenomeDownloader

This test validates the robust genome download functionality:
- Host extraction from phage CSV
- Assembly resolution
- Metadata-only mode
- Phage-host link creation
"""

import gzip
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
        
        # Test email - require environment variable or use clearly marked test email
        self.ncbi_email = os.environ.get('NCBI_EMAIL', 'pbi-test@example.org')
    
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

        # Raw host values are preserved (see extract_unique_hosts), so
        # 'Escherichia coli' and 'Escherichia coli K12' are distinct.
        self.assertIn("Escherichia coli", species)
        self.assertIn("Escherichia coli K12", species)
        self.assertIn("Staphylococcus aureus", species)
        self.assertIn("Bacillus subtilis", species)
        self.assertEqual(len(species), 4)
    
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
    
    def test_calculate_genome_stats(self):
        """Test genome statistics calculation from FASTA file"""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            metadata_only=True
        )
        
        # Create a test FASTA file
        test_fasta = self.temp_path / "test_genome.fna"
        # Create a sequence with known length and GC content
        # Sequence: 100 bp, 50 G/C = 50% GC content
        sequence = "ATGC" * 25  # 100 bp, 25 A, 25 T, 25 G, 25 C = 50% GC
        fasta_content = f">test_contig_1\n{sequence}\n"
        test_fasta.write_text(fasta_content)
        
        # Calculate stats
        length, gc_content = downloader.calculate_genome_stats(test_fasta)
        
        # Verify results
        self.assertEqual(length, 100, "Genome length should be 100 bp")
        self.assertEqual(gc_content, 50.0, "GC content should be 50%")
        
        # Test with multiple contigs
        test_fasta_multi = self.temp_path / "test_genome_multi.fna"
        seq1 = "GGGGCCCC"  # 8 bp, 100% GC
        seq2 = "AAAATTTT"  # 8 bp, 0% GC
        fasta_multi = f">contig1\n{seq1}\n>contig2\n{seq2}\n"
        test_fasta_multi.write_text(fasta_multi)
        
        length_multi, gc_multi = downloader.calculate_genome_stats(test_fasta_multi)
        
        # Total: 16 bp, 8 GC = 50% GC
        self.assertEqual(length_multi, 16, "Total genome length should be 16 bp")
        self.assertEqual(gc_multi, 50.0, "Average GC content should be 50%")
        
        # Test with gzipped file
        test_fasta_gz = self.temp_path / "test_genome.fna.gz"
        with gzip.open(test_fasta_gz, 'wt') as f:
            f.write(fasta_content)
        
        length_gz, gc_gz = downloader.calculate_genome_stats(test_fasta_gz)
        
        self.assertEqual(length_gz, 100, "Should handle gzipped FASTA")
        self.assertEqual(gc_gz, 50.0, "GC calculation should work for gzipped FASTA")
        
        # Test with empty file
        empty_fasta = self.temp_path / "empty.fna"
        empty_fasta.write_text("")
        
        length_empty, gc_empty = downloader.calculate_genome_stats(empty_fasta)

        self.assertIsNone(length_empty, "Empty file should return None for length")
        self.assertIsNone(gc_empty, "Empty file should return None for GC content")

    def test_calculate_genome_stats_streaming_parity(self):
        """Streaming byte-counter must match legacy SeqIO semantics."""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            metadata_only=True,
        )

        seq = "aTgCnX" * 1000  # mixed case + ambiguous; length counts all
        fasta = self.temp_path / "parity.fna"
        fasta.write_text(f">c1\n{seq}\n>c2\nGGCC\n")
        length, gc = downloader.calculate_genome_stats(fasta)
        # c1: 6000 bases, 2000 G/C; c2: 4 bases, 4 G/C
        self.assertEqual(length, 6004)
        self.assertAlmostEqual(gc, round(2004 / 6004 * 100, 2))

    def test_calculate_genome_stats_size_guard(self):
        """Oversized files are skipped without reading."""
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
            metadata_only=True,
            max_fasta_bytes=10,
        )
        fasta = self.temp_path / "big.fna"
        fasta.write_text(">c1\n" + "ATGC" * 100 + "\n")
        length, gc = downloader.calculate_genome_stats(fasta)
        self.assertIsNone(length)
        self.assertIsNone(gc)

    def test_create_host_fasta_chunked_roundtrip(self):
        """Chunked decompress must reproduce source content atomically."""
        from download_host_genomes_robust import GenomeFileType

        genomes_dir = self.temp_path / "genomes"
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(genomes_dir),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
        )

        class _Asm:
            assembly_accession = "GCF_000000000.1"

        src_dir = genomes_dir / "assemblies" / "GCF_000000000.1"
        src_dir.mkdir(parents=True, exist_ok=True)
        body = ">contig1\n" + "ATGC" * 5000 + "\n"
        src = src_dir / "x_genomic.fna.gz"
        with gzip.open(src, 'wt') as f:
            f.write(body)

        out = downloader.create_host_fasta(
            _Asm(), {GenomeFileType.GENOMIC_FNA: src}
        )
        self.assertIsNotNone(out)
        self.assertTrue(out.exists())
        self.assertFalse(out.with_suffix(out.suffix + ".tmp").exists())
        self.assertEqual(out.read_text(), body)
        # Second call hits skip-existing fast path
        out2 = downloader.create_host_fasta(
            _Asm(), {GenomeFileType.GENOMIC_FNA: src}
        )
        self.assertEqual(out2, out)

    def test_checkpoint_resume_loads_progress(self):
        """Killed-run checkpoints must seed existing_metadata on re-init."""
        checkpoint = self.temp_path / "assembly_metadata.checkpoint.csv"
        checkpoint.write_text(
            "Assembly_Accession,Assembly_Name\nGCF_014191245.1,ASM1419124v1\n"
        )
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=str(self.phage_csv),
            output_dir=str(self.temp_path / "genomes"),
            metadata_output=str(self.temp_path / "host_metadata.csv"),
            assembly_metadata_output=str(self.temp_path / "assembly_metadata.csv"),
            phage_host_links_output=str(self.temp_path / "phage_host_links.csv"),
            ncbi_email=self.ncbi_email,
        )
        # Final output missing; checkpoint seeds resume
        self.assertIn("GCF_014191245.1", downloader.existing_metadata)


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

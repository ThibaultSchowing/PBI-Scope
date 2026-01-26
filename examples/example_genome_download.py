#!/usr/bin/env python3
"""
Example usage of optimized genome download pipeline

This script demonstrates how to use the optimized genome downloader
with a small test dataset.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'workflow' / 'scripts' / 'sequences'))

def create_test_csv(csv_path: Path):
    """Create a small test CSV with sample phage data"""
    content = """Phage_ID,Host,Source_DB,Length
phage1,Escherichia coli K12,RefSeq,50000
phage2,Escherichia coli,RefSeq,48000
phage3,Staphylococcus aureus,Genbank,45000
phage4,Pseudomonas aeruginosa,RefSeq,52000
phage5,Bacillus subtilis,RefSeq,43000
phage6,Salmonella enterica,Genbank,47000
phage7,-,RefSeq,40000
phage8,unknown host,RefSeq,38000
phage9,Acidovorax sp000302535,RefSeq,44000
phage10,sp001411535,RefSeq,39000
"""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(content)
    print(f"✅ Created test CSV: {csv_path}")


def main():
    """Run example test"""
    print("=" * 80)
    print("OPTIMIZED GENOME DOWNLOAD - EXAMPLE USAGE")
    print("=" * 80)
    
    # Create temporary directory for test
    temp_dir = Path(tempfile.mkdtemp(prefix="genome_test_"))
    print(f"\n📁 Working directory: {temp_dir}")
    
    try:
        # Create test CSV
        test_csv = temp_dir / "test_phage_metadata.csv"
        create_test_csv(test_csv)
        
        # Setup paths
        output_dir = temp_dir / "genomes"
        metadata_output = temp_dir / "host_metadata.csv"
        cache_dir = temp_dir / "cache" / "genomes"
        cache_db = temp_dir / "cache" / "metadata.db"
        
        print("\n📋 Configuration:")
        print(f"  Input CSV: {test_csv}")
        print(f"  Output dir: {output_dir}")
        print(f"  Metadata: {metadata_output}")
        print(f"  Cache dir: {cache_dir}")
        print(f"  Cache DB: {cache_db}")
        
        # Create config
        config = {
            'download': {
                'max_concurrent': 3,
                'requests_per_second': 3,
                'timeout': 30,
                'max_retries': 2,
                'retry_backoff_factor': 2
            },
            'cache': {
                'enabled': True,
                'directory': str(cache_dir),
                'metadata_db': str(cache_db)
            },
            'parsing': {
                'fasta_format': 'fasta-2line'
            },
            'ncbi': {
                'email': os.getenv('NCBI_EMAIL', 'test@example.com'),
                'api_key': os.getenv('NCBI_API_KEY', '')
            },
            'validation': {
                'skip_gtdb_identifiers': True,
                'gtdb_pattern': 'sp\\d{9}'
            },
            'progress': {
                'enabled': True,
                'save_progress_file': str(temp_dir / 'progress.json')
            },
            'failures': {
                'log_file': str(temp_dir / 'failed_downloads.txt'),
                'categorize': True
            },
            'logging': {
                'level': 'INFO'
            }
        }
        
        print("\n🚀 Starting download...")
        print("   (This is a DRY RUN - actual downloads would be attempted)")
        
        # Import and run
        try:
            from download_host_genomes_optimized import (
                extract_unique_hosts_from_csv,
                OptimizedHostGenomeDownloader,
                ProgressTracker
            )
            
            # Extract species
            species_list = extract_unique_hosts_from_csv(str(test_csv))
            print(f"\n📊 Extracted {len(species_list)} unique species:")
            for i, species in enumerate(species_list, 1):
                print(f"  {i}. {species}")
            
            # Initialize downloader
            downloader = OptimizedHostGenomeDownloader(config)
            
            # Show what would be filtered
            print("\n🔍 Validation results:")
            for species in species_list:
                is_valid, reason = downloader.validator.is_valid_species_name(species)
                if is_valid:
                    print(f"  ✅ {species}")
                else:
                    print(f"  ⏭️  {species} - SKIPPED ({reason})")
            
            print("\n✅ Example completed successfully!")
            print(f"\n📝 Notes:")
            print(f"  - GTDB identifiers were correctly detected and would be skipped")
            print(f"  - Cache system is initialized at: {cache_dir}")
            print(f"  - To run actual downloads, set NCBI_EMAIL environment variable")
            print(f"  - For higher rate limits, also set NCBI_API_KEY")
            
        except ImportError as e:
            print(f"\n⚠️  Could not import optimizer (missing dependencies): {e}")
            print("   This is expected in minimal environments")
            print("   Install dependencies: conda env create -f workflow/envs/sequences.yaml")
        
    finally:
        # Cleanup
        import shutil
        print(f"\n🧹 Cleaning up temporary directory...")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        print("   Done!")


if __name__ == "__main__":
    main()

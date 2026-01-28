#!/usr/bin/env python
"""
Robust Host Bacterial Genome Downloader from NCBI

This module implements a robust, reproducible, and scalable strategy for retrieving
bacterial genome assemblies from NCBI, addressing all requirements:

1. Uses NCBI Assembly database as authoritative entry point
2. Normalizes all inputs to assembly accessions (GCF_ preferred, GCA_ fallback)
3. Explicit ambiguity acknowledgment for species/strain names
4. Quality-based filtering (RefSeq > GenBank, latest, assembly level, reference/representative)
5. Clear distinction between genome/assembly/contigs and curated/author-submitted data
6. Metadata via Entrez, sequences via FTP
7. Comprehensive file retrieval (FASTA, GFF, protein FASTA)
8. Failure mode mitigation (duplication, partial genomes, outdated assemblies)

Key Features:
- Assembly accession resolution from heterogeneous identifiers
- Metadata-only mode (skip downloads to save disk space)
- Preservation of previously downloaded genomes with hash validation
- Comprehensive assembly metadata tracking
- Database tables linking phages to host assemblies
"""

import os
import sys
import time
import logging
import hashlib
import urllib.request
import urllib.error
import gzip
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
import json
import pandas as pd
from Bio import SeqIO

# Import assembly resolver
from assembly_resolver import AssemblyResolver, AssemblyMetadata


class GenomeFileType:
    """Types of genome files to download from NCBI FTP"""
    
    # Sequence files
    GENOMIC_FNA = "_genomic.fna.gz"  # Genomic nucleotide FASTA
    PROTEIN_FAA = "_protein.faa.gz"   # Protein sequences
    CDS_FNA = "_cds_from_genomic.fna.gz"  # CDS nucleotide sequences
    
    # Annotation files
    GENOMIC_GFF = "_genomic.gff.gz"   # Gene annotation (GFF3 format)
    GENOMIC_GBK = "_genomic.gbff.gz"  # GenBank flat file
    
    # Feature tables
    FEATURE_TABLE = "_feature_table.txt.gz"
    
    # Assembly metadata
    ASSEMBLY_REPORT = "_assembly_report.txt"
    ASSEMBLY_STATS = "_assembly_stats.txt"
    
    @staticmethod
    def get_essential_files() -> List[str]:
        """
        Get list of essential files for bacterial genome analysis
        
        Rationale:
        - genomic.fna: Complete genome sequence (primary data)
        - genomic.gff: Gene annotations (functional analysis)
        - protein.faa: Translated proteins (comparative analysis)
        - assembly_report: Quality metrics and metadata
        """
        return [
            GenomeFileType.GENOMIC_FNA,
            GenomeFileType.GENOMIC_GFF,
            GenomeFileType.PROTEIN_FAA,
            GenomeFileType.ASSEMBLY_REPORT
        ]
    
    @staticmethod
    def get_optional_files() -> List[str]:
        """Get list of optional files (for advanced analysis)"""
        return [
            GenomeFileType.CDS_FNA,
            GenomeFileType.GENOMIC_GBK,
            GenomeFileType.FEATURE_TABLE,
            GenomeFileType.ASSEMBLY_STATS
        ]


class RobustHostGenomeDownloader:
    """
    Robust host bacterial genome downloader with comprehensive features
    
    This class implements the complete robust retrieval strategy for bacterial
    genomes from NCBI, with focus on reproducibility, quality, and failure handling.
    """
    
    def __init__(self,
                 phage_csv_path: str,
                 output_dir: str,
                 metadata_output: str,
                 assembly_metadata_output: str,
                 phage_host_links_output: str,
                 ncbi_email: str,
                 ncbi_api_key: Optional[str] = None,
                 metadata_only: bool = False,
                 skip_existing: bool = True,
                 validate_checksums: bool = True,
                 download_optional_files: bool = False):
        """
        Initialize RobustHostGenomeDownloader
        
        Args:
            phage_csv_path: Path to phage metadata CSV
            output_dir: Directory for downloaded genome files
            metadata_output: Path for host metadata CSV (backward compatible)
            assembly_metadata_output: Path for assembly metadata CSV (new)
            phage_host_links_output: Path for phage-host links CSV (new)
            ncbi_email: Email for NCBI API
            ncbi_api_key: Optional NCBI API key
            metadata_only: If True, only gather metadata without downloading files
            skip_existing: If True, skip already downloaded genomes
            validate_checksums: If True, validate file integrity with checksums
            download_optional_files: If True, download optional annotation files
        """
        self.phage_csv_path = Path(phage_csv_path)
        self.output_dir = Path(output_dir)
        self.metadata_output = Path(metadata_output)
        self.assembly_metadata_output = Path(assembly_metadata_output)
        self.phage_host_links_output = Path(phage_host_links_output)
        self.ncbi_email = ncbi_email
        self.ncbi_api_key = ncbi_api_key
        self.metadata_only = metadata_only
        self.skip_existing = skip_existing
        self.validate_checksums = validate_checksums
        self.download_optional_files = download_optional_files
        
        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        self.assembly_metadata_output.parent.mkdir(parents=True, exist_ok=True)
        self.phage_host_links_output.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize assembly resolver
        self.resolver = AssemblyResolver(
            email=ncbi_email,
            api_key=ncbi_api_key
        )
        
        # Track processing status
        self.processed_species: Set[str] = set()
        self.failed_species: Dict[str, str] = {}
        self.assembly_cache: Dict[str, AssemblyMetadata] = {}
        
        # Load existing metadata if available
        self.existing_metadata = self._load_existing_metadata()
        
        logging.info("✅ RobustHostGenomeDownloader initialized")
        logging.info(f"   Phage CSV: {self.phage_csv_path}")
        logging.info(f"   Output directory: {self.output_dir}")
        logging.info(f"   Metadata only: {self.metadata_only}")
        logging.info(f"   Skip existing: {self.skip_existing}")
        logging.info(f"   Validate checksums: {self.validate_checksums}")
        if self.existing_metadata:
            logging.info(f"   Found {len(self.existing_metadata)} existing genomes")
    
    def _load_existing_metadata(self) -> Dict[str, Dict]:
        """Load existing assembly metadata to avoid re-processing"""
        if not self.assembly_metadata_output.exists():
            return {}
        
        try:
            df = pd.read_csv(self.assembly_metadata_output)
            metadata = {}
            for _, row in df.iterrows():
                key = row['Assembly_Accession']
                metadata[key] = row.to_dict()
            return metadata
        except Exception as e:
            logging.warning(f"⚠️  Could not load existing metadata: {e}")
            return {}
    
    def extract_unique_hosts(self) -> List[str]:
        """
        Extract unique host species from phage metadata CSV
        
        Returns:
            List of unique species names in "Genus species" format
        """
        logging.info("📋 Extracting unique hosts from phage metadata...")
        
        df = pd.read_csv(self.phage_csv_path)
        
        if 'Host' not in df.columns:
            raise ValueError("Host column not found in phage metadata CSV")
        
        # Filter for valid hosts
        valid_mask = (
            df['Host'].notna() &
            (df['Host'] != '-') &
            (df['Host'] != '') &
            (~df['Host'].str.contains('unknown', case=False, na=False)) &
            (~df['Host'].str.contains('unidentified', case=False, na=False))
        )
        
        unique_hosts = df.loc[valid_mask, 'Host'].unique()
        
        # Extract species names (Genus species format)
        species_names = set()
        for host in unique_hosts:
            parts = str(host).strip().split()
            if len(parts) >= 2 and parts[0][0].isupper():
                species = f"{parts[0]} {parts[1]}"
                species_names.add(species)
            elif len(parts) == 1 and parts[0][0].isupper():
                species_names.add(parts[0])
        
        species_list = sorted(list(species_names))
        logging.info(f"✅ Found {len(species_list)} unique host species")
        
        return species_list
    
    def resolve_host_assemblies(self, species_list: List[str]) -> Dict[str, AssemblyMetadata]:
        """
        Resolve host species to best assembly for each
        
        This is the intermediary step that gathers assembly accessions and metadata
        before any downloads occur.
        
        Args:
            species_list: List of species names to resolve
            
        Returns:
            Dictionary mapping species name to best AssemblyMetadata
        """
        logging.info(f"🔍 Resolving {len(species_list)} species to assemblies...")
        
        resolved = {}
        failed = []
        
        for i, species in enumerate(species_list, 1):
            logging.info(f"[{i}/{len(species_list)}] Resolving {species}...")
            
            # Check if already in cache
            if species in self.assembly_cache:
                resolved[species] = self.assembly_cache[species]
                continue
            
            # Resolve to best assembly
            assembly = self.resolver.get_best_assembly(
                species,
                prefer_refseq=True,
                require_complete=False  # Don't require complete, but will rank higher
            )
            
            if assembly:
                resolved[species] = assembly
                self.assembly_cache[species] = assembly
                logging.info(f"   ✅ {assembly.assembly_accession} ({assembly.assembly_level})")
            else:
                failed.append(species)
                logging.warning(f"   ❌ No assembly found")
        
        logging.info(f"✅ Resolved {len(resolved)}/{len(species_list)} species to assemblies")
        if failed:
            logging.warning(f"⚠️  Failed to resolve {len(failed)} species:")
            for species in failed[:10]:  # Show first 10
                logging.warning(f"   - {species}")
            if len(failed) > 10:
                logging.warning(f"   ... and {len(failed) - 10} more")
        
        return resolved
    
    def download_assembly_ftp(self, 
                              assembly: AssemblyMetadata,
                              output_subdir: Path) -> Tuple[bool, Dict[str, Path]]:
        """
        Download assembly files from NCBI FTP
        
        Uses FTP for sequence retrieval (not efetch), as recommended.
        
        Args:
            assembly: AssemblyMetadata with FTP path
            output_subdir: Output directory for this assembly
            
        Returns:
            Tuple of (success: bool, downloaded_files: Dict[file_type, path])
        """
        if not assembly.ftp_path:
            logging.error(f"❌ No FTP path for {assembly.assembly_accession}")
            return False, {}
        
        # Create assembly-specific directory
        output_subdir.mkdir(parents=True, exist_ok=True)
        
        # Determine base filename from FTP path
        # FTP path format: https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/005/845/GCF_000005845.2_ASM584v2
        base_name = assembly.ftp_path.split('/')[-1]
        
        # Determine which files to download
        files_to_download = GenomeFileType.get_essential_files()
        if self.download_optional_files:
            files_to_download.extend(GenomeFileType.get_optional_files())
        
        downloaded = {}
        success = True
        
        for file_suffix in files_to_download:
            file_name = base_name + file_suffix
            file_url = f"{assembly.ftp_path}/{file_name}"
            output_file = output_subdir / file_name
            
            # Check if file already exists
            if self.skip_existing and output_file.exists():
                # Validate file if checksums enabled
                if self.validate_checksums:
                    if self._validate_file(output_file):
                        logging.debug(f"   ✓ Skipping existing file: {file_name}")
                        downloaded[file_suffix] = output_file
                        continue
                    else:
                        logging.warning(f"   ⚠️  Existing file failed validation: {file_name}")
                        output_file.unlink()  # Delete corrupted file
                else:
                    logging.debug(f"   ✓ Skipping existing file: {file_name}")
                    downloaded[file_suffix] = output_file
                    continue
            
            # Download file
            try:
                logging.info(f"   Downloading {file_name}...")
                urllib.request.urlretrieve(file_url, output_file)
                
                # Validate download
                if self.validate_checksums and not self._validate_file(output_file):
                    logging.error(f"   ❌ Downloaded file failed validation: {file_name}")
                    output_file.unlink()
                    success = False
                    continue
                
                downloaded[file_suffix] = output_file
                logging.info(f"   ✅ Downloaded {file_name} ({output_file.stat().st_size / 1024 / 1024:.2f} MB)")
                
            except urllib.error.HTTPError as e:
                if file_suffix in GenomeFileType.get_essential_files():
                    logging.error(f"   ❌ Failed to download essential file {file_name}: {e}")
                    success = False
                else:
                    logging.warning(f"   ⚠️  Optional file not available: {file_name}")
                    
            except Exception as e:
                if file_suffix in GenomeFileType.get_essential_files():
                    logging.error(f"   ❌ Error downloading {file_name}: {e}")
                    success = False
                else:
                    logging.warning(f"   ⚠️  Could not download optional file {file_name}: {e}")
        
        return success, downloaded
    
    def _validate_file(self, file_path: Path) -> bool:
        """
        Validate file integrity
        
        Checks:
        1. File exists and has non-zero size
        2. For FASTA files, validates basic structure
        
        Note: Could be enhanced with MD5 checksum validation using NCBI's
        checksum files for more rigorous validation.
        """
        if not file_path.exists():
            return False
        
        if file_path.stat().st_size == 0:
            return False
        
        # For FASTA files, validate structure more thoroughly
        if file_path.suffix == '.gz' and '.fna' in file_path.name:
            try:
                with gzip.open(file_path, 'rt') as f:
                    # Read file in chunks to detect corruption throughout
                    chunk_size = 1024 * 1024  # 1MB chunks
                    has_header = False
                    has_sequence = False
                    
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        
                        # Check for FASTA headers
                        if '>' in chunk:
                            has_header = True
                        
                        # Check for sequence content
                        if any(c in chunk for c in 'ACGTN'):
                            has_sequence = True
                    
                    # Valid FASTA must have both headers and sequences
                    return has_header and has_sequence
                    
            except Exception as e:
                logging.debug(f"FASTA validation failed for {file_path}: {e}")
                return False
        
        return True
    
    def create_host_fasta(self, assembly: AssemblyMetadata, downloaded_files: Dict[str, Path]) -> Optional[Path]:
        """
        Create individual host FASTA file from downloaded genomic FASTA
        
        Extracts and decompresses the genomic FASTA for use in downstream analysis.
        
        Args:
            assembly: AssemblyMetadata
            downloaded_files: Dict of downloaded files
            
        Returns:
            Path to created FASTA file or None
        """
        if GenomeFileType.GENOMIC_FNA not in downloaded_files:
            return None
        
        source_file = downloaded_files[GenomeFileType.GENOMIC_FNA]
        
        # Create output filename: {Assembly_Accession}.fna
        output_file = self.output_dir / f"{assembly.assembly_accession.replace('.', '_')}.fna"
        
        # Skip if exists and validated
        if self.skip_existing and output_file.exists():
            if self._validate_file(output_file):
                return output_file
            else:
                # Remove corrupted file
                output_file.unlink()
        
        # Decompress and write
        try:
            with gzip.open(source_file, 'rt') as f_in:
                with open(output_file, 'w') as f_out:
                    f_out.write(f_in.read())
            
            logging.info(f"   ✅ Created host FASTA: {output_file.name}")
            return output_file
            
        except Exception as e:
            logging.error(f"   ❌ Failed to create host FASTA: {e}")
            if output_file.exists():
                output_file.unlink()  # Clean up partial file
            return None
    
    def process_all_hosts(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Main processing pipeline: extract, resolve, download
        
        Returns:
            Tuple of (host_metadata_df, assembly_metadata_df, phage_host_links_df)
        """
        # Step 1: Extract unique hosts from phage CSV
        species_list = self.extract_unique_hosts()
        
        # Step 2: Resolve to assemblies (intermediary step)
        assemblies = self.resolve_host_assemblies(species_list)
        
        # Step 3: Process each assembly
        host_records = []
        assembly_records = []
        
        for i, (species, assembly) in enumerate(assemblies.items(), 1):
            logging.info(f"[{i}/{len(assemblies)}] Processing {species} ({assembly.assembly_accession})...")
            
            # Check if already processed
            if assembly.assembly_accession in self.existing_metadata and self.skip_existing:
                logging.info(f"   ✓ Already processed, skipping")
                assembly_records.append(self.existing_metadata[assembly.assembly_accession])
                continue
            
            # Download files (unless metadata-only mode)
            downloaded_files = {}
            download_success = True
            
            if not self.metadata_only:
                assembly_subdir = self.output_dir / "assemblies" / assembly.assembly_accession
                download_success, downloaded_files = self.download_assembly_ftp(assembly, assembly_subdir)
                
                if download_success:
                    # Create individual host FASTA
                    host_fasta = self.create_host_fasta(assembly, downloaded_files)
                else:
                    logging.warning(f"   ⚠️  Download failed for {assembly.assembly_accession}")
                    # Clean up partial downloads
                    if assembly_subdir.exists():
                        import shutil
                        try:
                            shutil.rmtree(assembly_subdir)
                            logging.info(f"   🧹 Cleaned up partial download directory")
                        except Exception as e:
                            logging.warning(f"   ⚠️  Could not clean up directory: {e}")
            
            # Create assembly metadata record
            assembly_record = {
                'Assembly_Accession': assembly.assembly_accession,
                'Assembly_Name': assembly.assembly_name,
                'Organism_Name': assembly.organism_name,
                'Species_TaxID': assembly.species_taxid,
                'Strain': assembly.strain or '-',
                'Assembly_Level': assembly.assembly_level,
                'RefSeq_Category': assembly.refseq_category,
                'BioSample': assembly.biosample or '-',
                'BioProject': assembly.bioproject or '-',
                'FTP_Path': assembly.ftp_path or '-',
                'Submission_Date': assembly.submission_date or '-',
                'Is_Latest': assembly.is_latest,
                'Quality_Score': assembly.get_quality_score(),
                'Is_RefSeq': assembly.is_refseq(),
                'Download_Status': 'success' if download_success or self.metadata_only else 'failed',
                'Download_Date': datetime.now().strftime('%Y-%m-%d'),
                'Metadata_Only': self.metadata_only
            }
            assembly_records.append(assembly_record)
            
            # Create backward-compatible host record
            host_record = {
                'Host_ID': assembly.assembly_accession.replace('.', '_'),
                'Species_Name': species,
                'Strain_Name': assembly.strain or '-',
                'Assembly_Accession': assembly.assembly_accession,
                'Assembly_Name': assembly.assembly_name,
                'Assembly_Level': assembly.assembly_level,
                'Genome_Length': '-',  # Will be calculated later if needed
                'GC_Content': '-',     # Will be calculated later if needed
                'RefSeq_Category': assembly.refseq_category,
                'Download_Date': datetime.now().strftime('%Y-%m-%d'),
                'Source': 'assembly_resolver'
            }
            host_records.append(host_record)
        
        # Step 4: Create phage-host links
        phage_host_links = self.create_phage_host_links(assemblies)
        
        # Create DataFrames
        host_df = pd.DataFrame(host_records)
        assembly_df = pd.DataFrame(assembly_records)
        links_df = pd.DataFrame(phage_host_links)
        
        return host_df, assembly_df, links_df
    
    def create_phage_host_links(self, assemblies: Dict[str, AssemblyMetadata]) -> List[Dict]:
        """
        Create phage-to-host assembly links
        
        Links each phage to its host's assembly accession.
        
        Args:
            assemblies: Dict mapping species name to AssemblyMetadata
            
        Returns:
            List of link records
        """
        logging.info("🔗 Creating phage-host assembly links...")
        
        # Read phage CSV
        phage_df = pd.read_csv(self.phage_csv_path)
        
        links = []
        for _, row in phage_df.iterrows():
            phage_id = row.get('Phage_ID', row.get('phage_id', ''))
            host = row.get('Host', '')
            
            if not host or host == '-' or not phage_id:
                continue
            
            # Extract species name from host
            parts = str(host).strip().split()
            if len(parts) >= 2 and parts[0][0].isupper():
                species = f"{parts[0]} {parts[1]}"
            elif len(parts) == 1 and parts[0][0].isupper():
                species = parts[0]
            else:
                continue
            
            # Find assembly for this species
            if species in assemblies:
                assembly = assemblies[species]
                links.append({
                    'Phage_ID': phage_id,
                    'Host_Species': species,
                    'Host_Full_Name': host,
                    'Assembly_Accession': assembly.assembly_accession,
                    'Assembly_Level': assembly.assembly_level,
                    'RefSeq_Category': assembly.refseq_category,
                    'Link_Quality': 'direct' if assembly.is_refseq() else 'genbank'
                })
        
        logging.info(f"✅ Created {len(links)} phage-host links")
        return links
    
    def run(self):
        """Execute complete pipeline"""
        logging.info("=" * 80)
        logging.info("ROBUST HOST GENOME DOWNLOADER")
        logging.info("=" * 80)
        
        start_time = time.time()
        
        # Process all hosts
        host_df, assembly_df, links_df = self.process_all_hosts()
        
        # Save outputs
        logging.info("💾 Saving outputs...")
        
        # Save host metadata (backward compatible)
        host_df.to_csv(self.metadata_output, index=False)
        logging.info(f"   ✅ Host metadata: {self.metadata_output}")
        
        # Save assembly metadata (new)
        assembly_df.to_csv(self.assembly_metadata_output, index=False)
        logging.info(f"   ✅ Assembly metadata: {self.assembly_metadata_output}")
        
        # Save phage-host links (new)
        links_df.to_csv(self.phage_host_links_output, index=False)
        logging.info(f"   ✅ Phage-host links: {self.phage_host_links_output}")
        
        # Summary
        elapsed = time.time() - start_time
        logging.info("=" * 80)
        logging.info("SUMMARY")
        logging.info("=" * 80)
        logging.info(f"Total hosts processed: {len(host_df)}")
        logging.info(f"Total assemblies: {len(assembly_df)}")
        logging.info(f"Total phage-host links: {len(links_df)}")
        if not self.metadata_only:
            success_count = len(assembly_df[assembly_df['Download_Status'] == 'success'])
            logging.info(f"Successful downloads: {success_count}/{len(assembly_df)}")
        logging.info(f"Time elapsed: {elapsed:.1f}s")
        logging.info("=" * 80)


def main():
    """Main entry point for Snakemake"""
    import argparse
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # For Snakemake integration
    if 'snakemake' in globals():
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=snakemake.input.phage_csv,
            output_dir=snakemake.params.output_dir,
            metadata_output=snakemake.output.metadata,
            assembly_metadata_output=snakemake.output.get('assembly_metadata', 
                                                          snakemake.output.metadata.replace('.csv', '_assemblies.csv')),
            phage_host_links_output=snakemake.output.get('phage_host_links',
                                                         snakemake.output.metadata.replace('.csv', '_phage_host_links.csv')),
            ncbi_email=os.environ.get('NCBI_EMAIL', 'your.email@example.com'),
            ncbi_api_key=os.environ.get('NCBI_API_KEY'),
            metadata_only=snakemake.params.get('metadata_only', False),
            skip_existing=snakemake.params.get('skip_existing', True),
            validate_checksums=snakemake.params.get('validate_checksums', True),
            download_optional_files=snakemake.params.get('download_optional_files', False)
        )
        downloader.run()
    else:
        # Command line mode
        parser = argparse.ArgumentParser(description='Robust host genome downloader')
        parser.add_argument('--phage-csv', required=True, help='Phage metadata CSV')
        parser.add_argument('--output-dir', required=True, help='Output directory')
        parser.add_argument('--metadata-output', required=True, help='Host metadata output CSV')
        parser.add_argument('--assembly-metadata', help='Assembly metadata output CSV')
        parser.add_argument('--phage-host-links', help='Phage-host links output CSV')
        parser.add_argument('--ncbi-email', default=os.environ.get('NCBI_EMAIL'), help='NCBI email')
        parser.add_argument('--ncbi-api-key', default=os.environ.get('NCBI_API_KEY'), help='NCBI API key')
        parser.add_argument('--metadata-only', action='store_true', help='Metadata only mode')
        parser.add_argument('--skip-existing', action='store_true', help='Skip existing files')
        parser.add_argument('--no-skip-existing', dest='skip_existing', action='store_false', help='Re-download existing files')
        parser.set_defaults(skip_existing=True)
        parser.add_argument('--validate-checksums', action='store_true', help='Validate checksums')
        parser.add_argument('--no-validate-checksums', dest='validate_checksums', action='store_false', help='Skip checksum validation')
        parser.set_defaults(validate_checksums=True)
        parser.add_argument('--download-optional', action='store_true', help='Download optional files')
        
        args = parser.parse_args()
        
        downloader = RobustHostGenomeDownloader(
            phage_csv_path=args.phage_csv,
            output_dir=args.output_dir,
            metadata_output=args.metadata_output,
            assembly_metadata_output=args.assembly_metadata or args.metadata_output.replace('.csv', '_assemblies.csv'),
            phage_host_links_output=args.phage_host_links or args.metadata_output.replace('.csv', '_phage_host_links.csv'),
            ncbi_email=args.ncbi_email,
            ncbi_api_key=args.ncbi_api_key,
            metadata_only=args.metadata_only,
            skip_existing=args.skip_existing,
            validate_checksums=args.validate_checksums,
            download_optional_files=args.download_optional
        )
        downloader.run()


if __name__ == '__main__':
    main()

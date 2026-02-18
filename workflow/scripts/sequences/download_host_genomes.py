#!/usr/bin/env python
"""
Download host bacterial genomes from NCBI RefSeq

This script downloads reference genomes for all unique hosts found in the phage metadata CSV,
using NCBI datasets CLI as primary method with Entrez API as fallback.

Note: Reads from CSV instead of database to avoid circular dependency.
"""

import os
import sys
import time
import logging
import subprocess
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import pandas as pd
from Bio import Entrez, SeqIO
from Bio.SeqUtils import gc_fraction

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# Regex patterns for assembly accessions (module-level constants)
GCA_PATTERN_WITH_SPACE = re.compile(r'\b(GCF|GCA)\s+(\d{9}\.\d+)\b')
ASSEMBLY_ACCESSION_PATTERN = re.compile(r'^(GCF|GCA)_\d{9}\.\d+$')


def extract_best_host_identifier(host_field: str) -> str:
    """
    Parse a host field and extract the best identifier for resolution
    
    Handles fields like "NA;GCA 900066335.1;UBA9502;Blautia..." by:
    1. Splitting on semicolons
    2. Fixing GCA/GCF accessions with spaces (e.g., "GCA 900066335.1" → "GCA_900066335.1")
    3. Filtering out "NA" and empty values
    4. Returning the first valid identifier (prioritizing accessions)
    
    Args:
        host_field: Raw host field value
        
    Returns:
        Best identifier to use for resolution, or empty string if none found
    """
    if not host_field or host_field is None:
        return ""
    
    # Handle various "null" representations
    host_field = str(host_field).strip()
    if host_field == '' or host_field.lower() in ('nan', 'none', 'null'):
        return ""
    
    # Fix GCA/GCF accessions with spaces (e.g., "GCA 900066335.1" → "GCA_900066335.1")
    host_field = GCA_PATTERN_WITH_SPACE.sub(r'\1_\2', host_field)
    
    # Split on semicolons and try each part
    parts = [p.strip() for p in host_field.split(';')]
    
    # First, look for assembly accessions (highest priority)
    for part in parts:
        if ASSEMBLY_ACCESSION_PATTERN.match(part):
            return part
    
    # Then look for any valid species names (non-NA, non-empty)
    for part in parts:
        if part and part.upper() != 'NA' and part != '-' and len(part) > 1:
            # Return first valid non-accession identifier
            return part
    
    return ""


class HostGenomeDownloader:
    """
    Download and process host bacterial genomes from NCBI RefSeq
    
    Features:
    - Extract unique hosts from phage database
    - Search NCBI RefSeq for reference genomes
    - Download using datasets CLI (primary) or Entrez API (fallback)
    - Calculate genome statistics (length, GC content)
    - Generate host metadata CSV
    """
    
    def __init__(self, 
                 phage_csv_path: str,
                 output_dir: str,
                 metadata_output: str,
                 ncbi_email: str = "your.email@example.com",
                 max_retries: int = 3,
                 delay: float = 0.5,
                 prefer_complete: bool = True):
        """
        Initialize HostGenomeDownloader
        
        Args:
            phage_csv_path: Path to merged phage metadata CSV file
            output_dir: Directory for individual host genome files
            metadata_output: Path for host metadata CSV
            ncbi_email: Email for NCBI API (required)
            max_retries: Maximum download retry attempts
            delay: Delay between NCBI requests (seconds)
            prefer_complete: Prefer complete genome assemblies
        """
        self.phage_csv_path = phage_csv_path
        self.output_dir = Path(output_dir)
        self.metadata_output = Path(metadata_output)
        self.ncbi_email = ncbi_email
        self.max_retries = max_retries
        self.delay = delay
        self.prefer_complete = prefer_complete
        
        # Setup Entrez
        Entrez.email = ncbi_email
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_output.parent.mkdir(parents=True, exist_ok=True)
        
        # Status tracking file for resume capability
        self.status_file = self.metadata_output.parent / "host_download_status.json"
        self.download_status = self._load_download_status()
        
        # Track download status
        self.successful_downloads = []
        self.failed_downloads = []
        
        logging.info(f"🔧 Initialized HostGenomeDownloader")
        logging.info(f"   Phage CSV: {self.phage_csv_path}")
        logging.info(f"   Output directory: {self.output_dir}")
        logging.info(f"   Metadata output: {self.metadata_output}")
        logging.info(f"   Status file: {self.status_file}")
        logging.info(f"   NCBI email: {self.ncbi_email}")
        
        # Log resume information
        if self.download_status:
            success_count = sum(1 for s in self.download_status.values() if s == 'success')
            fail_count = sum(1 for s in self.download_status.values() if s == 'failed')
            logging.info(f"   Resuming: {success_count} successful, {fail_count} failed from previous run")
    
    def _load_download_status(self) -> Dict[str, str]:
        """
        Load download status from JSON file
        
        Returns:
            Dictionary mapping species_name -> status ('success', 'failed', or 'not_attempted')
        """
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logging.warning(f"Could not load status file: {e}. Starting fresh.")
                return {}
        return {}
    
    def _save_download_status(self):
        """
        Save download status to JSON file atomically
        
        Uses atomic write (write to temp file, then rename) to prevent corruption
        """
        try:
            # Write to temporary file first
            temp_file = self.status_file.with_suffix('.json.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self.download_status, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.status_file)
        except (IOError, OSError) as e:
            logging.warning(f"Could not save status file: {e}")
            # Clean up temp file if it exists
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass  # Ignore cleanup errors
    
    def _update_status(self, species_name: str, status: str):
        """
        Update status for a species and save to file
        
        Args:
            species_name: Species name
            status: One of 'success', 'failed', 'not_attempted'
        """
        self.download_status[species_name] = status
        self._save_download_status()
    
    def _reconstruct_metadata_from_file(self, species_name: str) -> Optional[Dict]:
        """
        Reconstruct metadata from existing genome file
        
        This is used when resuming and the genome file exists but metadata wasn't saved.
        Scans output directory for files matching the species name.
        
        Args:
            species_name: Species name (e.g., "Escherichia coli")
        
        Returns:
            Dictionary with host metadata or None if file not found
        """
        # Search for files matching this species
        species_clean = species_name.replace(' ', '_')
        matching_files = list(self.output_dir.glob(f"{species_clean}_*.fna"))
        
        if not matching_files:
            return None
        
        # Use the first matching file (should only be one per species)
        fasta_path = matching_files[0]
        
        # Extract Host_ID from filename
        host_id = fasta_path.stem
        
        # Extract accession using regex for GenBank/RefSeq format (GCF_ or GCA_ followed by digits and version)
        accession_match = re.search(r'(GC[AF]_\d+\.\d+)', host_id)
        if not accession_match:
            logging.warning(f"Could not extract accession from filename: {host_id}")
            return None
        
        accession = accession_match.group(1)
        
        # Calculate statistics from file
        genome_length, gc_content = self.calculate_genome_stats(fasta_path)
        
        # Create minimal metadata record
        metadata = {
            'Host_ID': host_id,
            'Species_Name': species_name,
            'Strain_Name': '-',
            'Assembly_Accession': accession,
            'Assembly_Name': '-',
            'Assembly_Level': '-',
            'Genome_Length': genome_length,
            'GC_Content': gc_content,
            'RefSeq_Category': '-',
            'Download_Date': datetime.fromtimestamp(fasta_path.stat().st_mtime).strftime('%Y-%m-%d'),
            'Source': 'reconstructed'
        }
        
        logging.info(f"   📄 Reconstructed metadata from existing file: {host_id}")
        
        return metadata
    
    def get_unique_hosts_from_csv(self) -> List[str]:
        """
        Extract unique host species from phage metadata CSV
        
        Returns:
            List of unique host species names
        """
        logging.info(f"📊 Extracting unique hosts from CSV: {self.phage_csv_path}")
        
        # Read CSV file
        df = pd.read_csv(self.phage_csv_path)
        
        # Check if Host column exists
        if 'Host' not in df.columns:
            logging.error(f"❌ 'Host' column not found in CSV file!")
            logging.error(f"   Available columns: {list(df.columns)}")
            raise ValueError("Host column not found in phage metadata CSV")
        
        # Filter for valid hosts using a single boolean mask for efficiency
        valid_mask = (
            df['Host'].notna() &                                                    # Not null
            (df['Host'] != '-') &                                                    # Not dash
            (df['Host'] != '') &                                                     # Not empty
            (~df['Host'].str.contains('unknown', case=False, na=False)) &           # Not unknown
            (~df['Host'].str.contains('unidentified', case=False, na=False))       # Not unidentified
        )
        
        # Get unique hosts
        unique_hosts = df.loc[valid_mask, 'Host'].unique()
        
        logging.info(f"✅ Found {len(unique_hosts)} unique hosts")
        
        # Parse each host field to extract the best identifier
        host_identifiers = set()
        for host in unique_hosts:
            identifier = extract_best_host_identifier(host)
            if identifier:
                host_identifiers.add(identifier)
        
        host_list = sorted(list(host_identifiers))
        logging.info(f"✅ Extracted {len(host_list)} unique host identifiers")
        
        # Log some examples
        for i, host_id in enumerate(host_list[:5]):
            logging.info(f"   Example {i+1}: {host_id}")
        
        return host_list
    
    def _is_assembly_accession(self, identifier: str) -> bool:
        """Check if identifier is an assembly accession (GCF_/GCA_)"""
        return ASSEMBLY_ACCESSION_PATTERN.match(identifier) is not None
    
    def search_assembly_by_accession(self, accession: str) -> Optional[Dict]:
        """
        Search for assembly by accession number
        
        Args:
            accession: Assembly accession (e.g., "GCA_900066335.1")
        
        Returns:
            Dictionary with assembly info or None if not found
        """
        try:
            time.sleep(self.delay)
            
            # Search for exact accession
            handle = Entrez.esearch(
                db="assembly",
                term=f"{accession}[Assembly Accession]",
                retmax=1
            )
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                logging.warning(f"⚠️  Assembly not found: {accession}")
                return None
            
            # Get assembly summary
            time.sleep(self.delay)
            handle = Entrez.esummary(db="assembly", id=search_results['IdList'][0])
            summary = Entrez.read(handle, validate=False)
            handle.close()
            
            doc_sum = summary['DocumentSummarySet']['DocumentSummary'][0]
            
            return {
                'accession': doc_sum.get('AssemblyAccession', ''),
                'assembly_name': doc_sum.get('AssemblyName', ''),
                'assembly_level': doc_sum.get('AssemblyStatus', ''),
                'organism_name': doc_sum.get('SpeciesName', ''),
                'ftp_path': doc_sum.get('FtpPath_RefSeq', '') or doc_sum.get('FtpPath_GenBank', '')
            }
            
        except Exception as e:
            logging.error(f"❌ Error searching assembly {accession}: {e}")
            return None
    
    def search_refseq_assembly_datasets(self, species_name: str) -> Optional[Dict]:
        """
        Search for RefSeq assembly using NCBI datasets CLI
        
        Args:
            species_name: Species name (e.g., "Escherichia coli")
        
        Returns:
            Dictionary with assembly info or None if not found
        """
        try:
            # Check if datasets command is available
            result = subprocess.run(['datasets', 'version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logging.warning("⚠️  NCBI datasets CLI not found, will use Entrez fallback")
                return None
            
            # Search for genome
            cmd = [
                'datasets', 'summary', 'genome', 'taxon',
                species_name,
                '--refseq',
                '--as-json-lines'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logging.debug(f"datasets search failed for {species_name}: {result.stderr}")
                return None
            
            # Parse JSON lines output
            assemblies = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    data = json.loads(line)
                    if 'assemblies' in data:
                        assemblies.extend(data['assemblies'])
            
            if not assemblies:
                return None
            
            # Select best assembly based on priority
            best_assembly = self._select_best_assembly(assemblies)
            
            return best_assembly
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logging.debug(f"datasets CLI error for {species_name}: {e}")
            return None
        except FileNotFoundError:
            # datasets command not found
            return None
    
    def search_refseq_assembly_entrez(self, species_name: str) -> Optional[Dict]:
        """
        Search for RefSeq assembly using Entrez API (fallback method)
        
        Args:
            species_name: Species name (e.g., "Escherichia coli")
        
        Returns:
            Dictionary with assembly info or None if not found
        """
        try:
            time.sleep(self.delay)  # Rate limiting
            
            # Search assembly database
            search_term = f'"{species_name}"[Organism] AND "latest refseq"[Filter]'
            
            handle = Entrez.esearch(db="assembly", term=search_term, retmax=10)
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                return None
            
            # Get assembly summaries
            time.sleep(self.delay)
            ids = search_results['IdList'][:5]  # Get top 5
            
            handle = Entrez.esummary(db="assembly", id=",".join(ids))
            summaries = Entrez.read(handle, validate=False)
            handle.close()
            
            # Parse summaries
            assemblies = []
            for doc_sum in summaries['DocumentSummarySet']['DocumentSummary']:
                assembly_info = {
                    'accession': doc_sum.get('AssemblyAccession', ''),
                    'assembly_name': doc_sum.get('AssemblyName', ''),
                    'assembly_level': doc_sum.get('AssemblyStatus', ''),
                    'species_name': doc_sum.get('SpeciesName', species_name),
                    'refseq_category': doc_sum.get('RefSeq_category', ''),
                    'source': 'entrez_api'
                }
                assemblies.append(assembly_info)
            
            if not assemblies:
                return None
            
            # Select best assembly
            best = self._select_best_assembly_entrez(assemblies)
            return best
            
        except Exception as e:
            logging.debug(f"Entrez search error for {species_name}: {e}")
            return None
    
    def _select_best_assembly(self, assemblies: List[Dict]) -> Optional[Dict]:
        """
        Select best assembly from datasets CLI results based on priority
        
        Priority:
        1. Reference genome
        2. Representative genome
        3. Complete Genome level
        4. Chromosome level
        5. Latest version
        """
        if not assemblies:
            return None
        
        def score_assembly(asm):
            score = 0
            
            # RefSeq category priority
            assembly_info = asm.get('assembly', {})
            refseq_cat = assembly_info.get('refseq_category', '')
            if refseq_cat == 'reference genome':
                score += 1000
            elif refseq_cat == 'representative genome':
                score += 500
            
            # Assembly level priority
            level = assembly_info.get('assembly_level', '')
            if level == 'Complete Genome':
                score += 100
            elif level == 'Chromosome':
                score += 50
            elif level == 'Scaffold':
                score += 25
            
            return score
        
        best = max(assemblies, key=score_assembly)
        
        assembly_info = best.get('assembly', {})
        return {
            'accession': assembly_info.get('assembly_accession', ''),
            'assembly_name': assembly_info.get('assembly_name', ''),
            'assembly_level': assembly_info.get('assembly_level', ''),
            'species_name': best.get('organism', {}).get('organism_name', ''),
            'strain': best.get('organism', {}).get('infraspecific_names', {}).get('strain', ''),
            'refseq_category': assembly_info.get('refseq_category', ''),
            'source': 'datasets_cli'
        }
    
    def _select_best_assembly_entrez(self, assemblies: List[Dict]) -> Optional[Dict]:
        """Select best assembly from Entrez API results"""
        if not assemblies:
            return None
        
        def score_assembly(asm):
            score = 0
            
            # RefSeq category
            if asm.get('refseq_category') == 'reference genome':
                score += 1000
            elif asm.get('refseq_category') == 'representative genome':
                score += 500
            
            # Assembly level
            level = asm.get('assembly_level', '')
            if level == 'Complete Genome':
                score += 100
            elif level == 'Chromosome':
                score += 50
            elif level == 'Scaffold':
                score += 25
            
            return score
        
        return max(assemblies, key=score_assembly)
    
    def download_genome_datasets(self, assembly_accession: str, output_path: Path) -> bool:
        """
        Download genome using NCBI datasets CLI
        
        Args:
            assembly_accession: Assembly accession (e.g., GCF_000005845.2)
            output_path: Output FASTA file path
        
        Returns:
            True if successful, False otherwise
        """
        try:
            temp_dir = output_path.parent / f"temp_{assembly_accession}"
            temp_dir.mkdir(exist_ok=True)
            
            # Download genome
            cmd = [
                'datasets', 'download', 'genome', 'accession',
                assembly_accession,
                '--include', 'genome',
                '--filename', str(temp_dir / 'genome.zip')
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logging.debug(f"datasets download failed: {result.stderr}")
                return False
            
            # Unzip
            import zipfile
            with zipfile.ZipFile(temp_dir / 'genome.zip', 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            # Find FASTA file
            fasta_files = list(temp_dir.rglob('*.fna'))
            if not fasta_files:
                logging.warning(f"No FASTA file found in downloaded data")
                return False
            
            # Move to output location
            import shutil
            shutil.copy(fasta_files[0], output_path)
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            return True
            
        except Exception as e:
            logging.debug(f"datasets download error: {e}")
            return False
    
    def download_genome_entrez(self, assembly_accession: str, output_path: Path) -> bool:
        """
        Download genome using Entrez API (fallback)
        
        Args:
            assembly_accession: Assembly accession
            output_path: Output FASTA file path
        
        Returns:
            True if successful, False otherwise
        """
        try:
            time.sleep(self.delay)
            
            # Get nucleotide IDs for assembly
            handle = Entrez.esearch(
                db="nuccore",
                term=f"{assembly_accession}[Assembly Accession]",
                retmax=100
            )
            search_results = Entrez.read(handle)
            handle.close()
            
            if not search_results['IdList']:
                return False
            
            # Download sequences
            time.sleep(self.delay)
            
            handle = Entrez.efetch(
                db="nuccore",
                id=search_results['IdList'],
                rettype="fasta",
                retmode="text"
            )
            
            # Read the content and close the handle
            fasta_content = handle.read()
            handle.close()
            
            # Validate content before writing
            if not fasta_content or len(fasta_content.strip()) == 0:
                logging.debug(f"Downloaded content is empty for {assembly_accession}")
                return False
            
            # Quick validation - check if content starts with '>'
            lines = fasta_content.splitlines()
            if not lines:
                logging.debug(f"Downloaded content has no lines for {assembly_accession}")
                return False
            
            first_line = lines[0].strip()
            if not first_line or not first_line.startswith('>'):
                content_preview = first_line[:100] if first_line else "(empty)"
                logging.debug(f"Invalid FASTA format for {assembly_accession}: {content_preview}")
                return False
            
            # Write to file after validation
            with open(output_path, 'w') as f:
                f.write(fasta_content)
            
            return True
            
        except Exception as e:
            logging.debug(f"Entrez download error: {e}")
            return False
    
    def calculate_genome_stats(self, fasta_path: Path) -> Tuple[int, float]:
        """
        Calculate genome length and GC content from FASTA file
        
        Args:
            fasta_path: Path to FASTA file
        
        Returns:
            Tuple of (total_length, gc_content_percent)
        """
        try:
            total_length = 0
            total_gc = 0
            
            # Use fasta-2line format to handle FASTA files with comments
            # This prevents Biopython deprecation warnings
            for record in SeqIO.parse(fasta_path, "fasta-2line"):
                seq_len = len(record.seq)
                total_length += seq_len
                total_gc += gc_fraction(record.seq) * seq_len
            
            gc_content = (total_gc / total_length * 100) if total_length > 0 else 0
            
            return total_length, round(gc_content, 2)
            
        except Exception as e:
            logging.warning(f"Error calculating genome stats: {e}")
            return 0, 0.0
    
    def download_host_genome(self, species_name: str) -> Optional[Dict]:
        """
        Download host genome for a given species or assembly accession
        
        Args:
            species_name: Species name (e.g., "Escherichia coli") or assembly accession (e.g., "GCA_900066335.1")
        
        Returns:
            Dictionary with host metadata or None if failed
        """
        logging.info(f"🔍 Processing: {species_name}")
        
        # Check if already successfully downloaded
        if self.download_status.get(species_name) == 'success':
            logging.info(f"   ✅ Already downloaded successfully (skipping)")
            
            # Try to reconstruct metadata from existing file
            metadata = self._reconstruct_metadata_from_file(species_name)
            if metadata:
                return metadata
            else:
                # If reconstruction fails, mark for re-download
                logging.warning(f"   ⚠️  Could not reconstruct metadata, will re-download")
                self._update_status(species_name, 'not_attempted')
        
        # Check if this is an assembly accession
        if self._is_assembly_accession(species_name):
            logging.info(f"   Detected assembly accession: {species_name}")
            assembly_info = self.search_assembly_by_accession(species_name)
        else:
            # Search for assembly (try datasets CLI first, then Entrez)
            assembly_info = self.search_refseq_assembly_datasets(species_name)
            
            if not assembly_info:
                logging.info(f"   Trying Entrez API fallback...")
                assembly_info = self.search_refseq_assembly_entrez(species_name)
        
        if not assembly_info:
            logging.warning(f"   ❌ No assembly found for {species_name}")
            self._update_status(species_name, 'failed')
            return None
        
        # Create Host_ID
        accession = assembly_info['accession']
        species_clean = species_name.replace(' ', '_')
        host_id = f"{species_clean}_{accession}"
        
        output_path = self.output_dir / f"{host_id}.fna"
        
        # Skip if already downloaded
        if output_path.exists() and output_path.stat().st_size > 0:
            logging.info(f"   ✅ Already exists: {host_id}")
            genome_length, gc_content = self.calculate_genome_stats(output_path)
        else:
            # Download genome
            logging.info(f"   📥 Downloading: {accession}")
            
            success = False
            for attempt in range(self.max_retries):
                if assembly_info['source'] == 'datasets_cli':
                    success = self.download_genome_datasets(accession, output_path)
                
                if not success:
                    # Try Entrez fallback
                    logging.info(f"   Trying Entrez download (attempt {attempt + 1}/{self.max_retries})...")
                    success = self.download_genome_entrez(accession, output_path)
                
                if success:
                    break
                
                time.sleep(self.delay * (2 ** attempt))  # Exponential backoff
            
            if not success:
                logging.warning(f"   ❌ Download failed after {self.max_retries} attempts")
                self._update_status(species_name, 'failed')
                return None
            
            # Calculate statistics
            genome_length, gc_content = self.calculate_genome_stats(output_path)
            logging.info(f"   ✅ Downloaded: {genome_length:,} bp, GC: {gc_content}%")
        
        # Create metadata record
        metadata = {
            'Host_ID': host_id,
            'Species_Name': species_name,
            'Strain_Name': assembly_info.get('strain', '-'),
            'Assembly_Accession': accession,
            'Assembly_Name': assembly_info.get('assembly_name', '-'),
            'Assembly_Level': assembly_info.get('assembly_level', '-'),
            'Genome_Length': genome_length,
            'GC_Content': gc_content,
            'RefSeq_Category': assembly_info.get('refseq_category', '-'),
            'Download_Date': datetime.now().strftime('%Y-%m-%d'),
            'Source': assembly_info.get('source', 'unknown')
        }
        
        # Mark as successful
        self._update_status(species_name, 'success')
        
        return metadata
    
    def create_host_metadata_csv(self, host_records: List[Dict], output_path: Path):
        """
        Generate host metadata CSV file
        
        Args:
            host_records: List of host metadata dictionaries
            output_path: Output CSV path
        """
        df = pd.DataFrame(host_records)
        
        # Ensure columns are in correct order
        columns = [
            'Host_ID', 'Species_Name', 'Strain_Name', 'Assembly_Accession',
            'Assembly_Name', 'Assembly_Level', 'Genome_Length', 'GC_Content',
            'RefSeq_Category', 'Download_Date', 'Source'
        ]
        
        df = df[columns]
        
        # Save to CSV
        df.to_csv(output_path, index=False)
        logging.info(f"✅ Saved metadata: {output_path}")
        logging.info(f"   Total hosts: {len(df)}")
    
    def run(self, limit: Optional[int] = None):
        """
        Run the full host genome download pipeline
        
        Args:
            limit: Optional limit on number of species to download (for testing)
        """
        logging.info("🚀 Starting host genome download pipeline")
        
        # Get unique hosts from CSV
        species_list = self.get_unique_hosts_from_csv()
        
        if limit:
            logging.info(f"⚠️  Limiting to {limit} species for testing")
            species_list = species_list[:limit]
        
        # Count how many need to be downloaded vs skipped
        to_process = []
        skipped = []
        for species in species_list:
            if self.download_status.get(species) == 'success':
                skipped.append(species)
            else:
                to_process.append(species)
        
        logging.info(f"📊 Resume Summary:")
        logging.info(f"   Total species: {len(species_list)}")
        logging.info(f"   Already completed: {len(skipped)}")
        logging.info(f"   To process: {len(to_process)}")
        
        # Download genomes
        host_records = []
        
        for i, species in enumerate(species_list, 1):
            logging.info(f"\n[{i}/{len(species_list)}] Processing: {species}")
            
            metadata = self.download_host_genome(species)
            
            if metadata:
                host_records.append(metadata)
                self.successful_downloads.append(species)
            else:
                self.failed_downloads.append(species)
        
        # Generate metadata CSV
        if host_records:
            self.create_host_metadata_csv(host_records, self.metadata_output)
        
        # Summary
        logging.info("\n" + "="*80)
        logging.info("📊 Download Summary:")
        logging.info(f"   Total species: {len(species_list)}")
        logging.info(f"   ✅ Successful: {len(self.successful_downloads)}")
        logging.info(f"   ❌ Failed: {len(self.failed_downloads)}")
        
        if self.failed_downloads:
            logging.warning(f"\n⚠️  Failed downloads:")
            for species in self.failed_downloads[:10]:
                logging.warning(f"   - {species}")
            if len(self.failed_downloads) > 10:
                logging.warning(f"   ... and {len(self.failed_downloads) - 10} more")


def main():
    """Main entry point for Snakemake"""
    
    # Verify snakemake is available
    if 'snakemake' not in globals():
        raise RuntimeError("This script must be run from Snakemake")
    
    # Get parameters from Snakemake
    phage_csv_path = snakemake.input.phage_csv
    output_dir = snakemake.params.output_dir
    metadata_output = snakemake.output.metadata
    
    ncbi_email = snakemake.config.get('ncbi_email', 'phage.pipeline@example.com')
    max_retries = snakemake.config.get('max_host_download_retries', 3)
    delay = snakemake.config.get('host_download_delay', 0.5)
    
    # Optional limit for testing
    limit = snakemake.params.get('limit', None)
    
    # Initialize downloader
    downloader = HostGenomeDownloader(
        phage_csv_path=phage_csv_path,
        output_dir=output_dir,
        metadata_output=metadata_output,
        ncbi_email=ncbi_email,
        max_retries=max_retries,
        delay=delay
    )
    
    # Run pipeline
    downloader.run(limit=limit)


if __name__ == "__main__":
    if 'snakemake' in globals():
        main()
    else:
        # Standalone mode for testing
        import argparse
        
        parser = argparse.ArgumentParser(description='Download host bacterial genomes')
        parser.add_argument('--phage-csv', required=True, help='Path to merged phage metadata CSV')
        parser.add_argument('--output-dir', required=True, help='Output directory for genomes')
        parser.add_argument('--metadata', required=True, help='Output path for metadata CSV')
        parser.add_argument('--email', default='phage.pipeline@example.com', help='NCBI email')
        parser.add_argument('--limit', type=int, help='Limit number of species (for testing)')
        
        args = parser.parse_args()
        
        downloader = HostGenomeDownloader(
            phage_csv_path=args.phage_csv,
            output_dir=args.output_dir,
            metadata_output=args.metadata,
            ncbi_email=args.email
        )
        
        downloader.run(limit=args.limit)

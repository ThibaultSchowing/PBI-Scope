#!/usr/bin/env python3
"""
Index individual host genome FASTA files using pyfaidx

This script reads the host mapping JSON file and creates .fai index files
for each individual host genome FASTA file. This allows efficient random
access to host sequences without needing to merge all files.
"""

import json
import logging
from pathlib import Path
from pyfaidx import Fasta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def index_host_files(mapping_file: str, log_file: str):
    """
    Index all host FASTA files listed in the mapping file
    
    Args:
        mapping_file: Path to JSON file containing Host_ID to file path mapping
        log_file: Path to log file
    """
    # Read mapping file
    with open(mapping_file, 'r') as f:
        host_mapping = json.load(f)
    
    total_files = len(host_mapping)
    logging.info(f"📊 Indexing {total_files} host FASTA files...")
    
    indexed_count = 0
    error_count = 0
    
    for host_id, fasta_path in host_mapping.items():
        try:
            fasta_file = Path(fasta_path)
            index_file = Path(str(fasta_file) + '.fai')
            
            # Check if index already exists
            if index_file.exists():
                logging.debug(f"✓ Index already exists for {host_id}")
                indexed_count += 1
                continue
            
            # Create index using pyfaidx
            # Use duplicate_action='first' to handle FASTA files with duplicate
            # sequence IDs (raises ValueError with default 'stop' action)
            with Fasta(str(fasta_file), duplicate_action='first'):
                pass
            
            # Verify index was created
            if index_file.exists():
                indexed_count += 1
                if indexed_count % 100 == 0:
                    logging.info(f"⏳ Indexed {indexed_count}/{total_files} files...")
            else:
                error_count += 1
                logging.warning(f"⚠️ Failed to create index for {host_id}: {fasta_path}")
                
        except Exception as e:
            error_count += 1
            logging.error(f"❌ Error indexing {host_id}: {str(e)}")
    
    # Write summary to log file
    with open(log_file, 'w') as f:
        f.write(f"✅ Successfully indexed {indexed_count}/{total_files} host FASTA files\n")
        if error_count > 0:
            f.write(f"⚠️ {error_count} files failed to index\n")
    
    logging.info(f"✅ Indexing complete: {indexed_count}/{total_files} files indexed")
    if error_count > 0:
        logging.warning(f"⚠️ {error_count} files failed to index")


if __name__ == "__main__":
    # Snakemake variables
    mapping_file = snakemake.input.mapping
    log_file = snakemake.log[0]
    
    index_host_files(mapping_file, log_file)

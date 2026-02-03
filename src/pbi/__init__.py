"""
PBI - Phage Bioinformatics Interface

A package for interacting with phage genomics databases created by the workflow pipeline.

Main classes:
    - SequenceRetriever: Retrieve sequences from indexed FASTA files using SQL queries
    - NegativeExampleGenerator: Generate negative training examples for ML
    - DatabaseManager: (future) Database connection management utilities
"""

# Import main classes for easy access
from .sequence_retrieval import SequenceRetriever
from .negative_examples import NegativeExampleGenerator
# from .database import DatabaseManager  # If you have this class / later

# Package metadata
__version__ = "0.1.0"
__author__ = "Thibault Schowing, CI4CB"

# Define what gets imported with "from pbi import *"
__all__ = [
    'SequenceRetriever',
    'NegativeExampleGenerator',
    # 'DatabaseManager',
]

# Optional: Add convenience functions
def get_default_paths():
    """
    Get default paths for database and FASTA files
    
    Checks DATA_PATH environment variable first (for Docker containers),
    then falls back to project-relative paths (for local development).
    
    Returns:
        dict: Paths to database and FASTA files
    """
    import os
    from pathlib import Path
    
    # Check if DATA_PATH environment variable is set (Docker/container mode)
    data_path = os.environ.get('DATA_PATH')
    
    if data_path:
        # Container mode: use DATA_PATH directly
        base_path = Path(data_path)
    else:
        # Local mode: use project-relative path
        project_root = Path(__file__).parent.parent.parent
        base_path = project_root / 'data' / 'processed'
    
    return {
        'database': base_path / 'databases' / 'phage_database_optimized.duckdb',
        'phage_fasta': base_path / 'sequences' / 'all_phages.fasta',
        'protein_fasta': base_path / 'sequences' / 'all_proteins.fasta',
        'host_mapping': base_path / 'sequences' / 'host_fasta_mapping.json',
        # Legacy path for backward compatibility
        'host_fasta': base_path / 'sequences' / 'all_hosts.fasta',
    }

def quick_connect():
    """
    Quick connection to default database with all sequence files
    
    Returns:
        SequenceRetriever: Connected retriever instance
    
    Example:
        >>> import pbi
        >>> retriever = pbi.quick_connect()
        >>> df = retriever.get_phage_sequences("SELECT Phage_ID FROM fact_phages LIMIT 10")
    """
    paths = get_default_paths()
    
    # Prefer host mapping file (new approach), fallback to single file (legacy)
    host_mapping = str(paths['host_mapping']) if paths['host_mapping'].exists() else None
    host_fasta = str(paths['host_fasta']) if paths['host_fasta'].exists() else None
    
    return SequenceRetriever(
        str(paths['database']),
        str(paths['phage_fasta']),
        str(paths['protein_fasta']),
        host_fasta_path=host_fasta,
        host_mapping_path=host_mapping
    )
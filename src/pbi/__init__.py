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
    
    Returns:
        dict: Default paths relative to project root
    """
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent.parent
    
    return {
        'database': project_root / 'data' / 'processed' / 'databases' / 'phage_database_optimized.duckdb',
        'phage_fasta': project_root / 'data' / 'processed' / 'sequences' / 'all_phages.fasta',
        'protein_fasta': project_root / 'data' / 'processed' / 'sequences' / 'all_proteins.fasta',
        'host_fasta': project_root / 'data' / 'processed' / 'sequences' / 'all_hosts.fasta',
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
    
    # Check if host FASTA exists
    host_fasta = str(paths['host_fasta']) if paths['host_fasta'].exists() else None
    
    return SequenceRetriever(
        str(paths['database']),
        str(paths['phage_fasta']),
        str(paths['protein_fasta']),
        host_fasta
    )
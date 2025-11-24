"""
PBI - Phage Bioinformatics Interface

A package for interacting with phage genomics databases created by the workflow pipeline.

Main classes:
    - SequenceRetriever: Retrieve sequences from indexed FASTA files using SQL queries
    - DatabaseManager: (future) Database connection management utilities
"""

# Import main classes for easy access
from .sequence_retrieval import SequenceRetriever
# from .database import DatabaseManager  # If you have this class / later

# Package metadata
__version__ = "0.1.0"
__author__ = "Thibault Schowing"

# Define what gets imported with "from pbi import *"
__all__ = [
    'SequenceRetriever',
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
    }

def quick_connect():
    """
    Quick connection to default database with standard paths
    
    Returns:
        SequenceRetriever: Connected retriever instance
    
    Example:
        >>> import pbi
        >>> retriever = pbi.quick_connect()
        >>> df = retriever.get_phage_sequences("SELECT Phage_ID FROM fact_phages LIMIT 10")
    """
    paths = get_default_paths()
    return SequenceRetriever(
        str(paths['database']),
        str(paths['phage_fasta']),
        str(paths['protein_fasta'])
    )
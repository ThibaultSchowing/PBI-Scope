"""
Test for get_stats() method when phage_host_associations table is missing.

This test validates that the get_stats() method handles the scenario where
the phage_host_associations table doesn't exist in the database without
raising a KeyError.
"""
import sys
import os
import tempfile
import duckdb
import logging
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pbi.sequence_retrieval import SequenceRetriever

logging.basicConfig(level=logging.INFO)


def create_test_database_with_missing_table():
    """
    Create a test database that has dim_hosts table but is missing 
    phage_host_associations table to simulate the error scenario.
    """
    # Create a temporary database
    import uuid
    db_path = f"/tmp/test_db_{uuid.uuid4().hex}.duckdb"
    
    conn = duckdb.connect(db_path)
    
    # Create minimal schema
    conn.execute("""
        CREATE TABLE fact_phages (
            Phage_ID VARCHAR PRIMARY KEY,
            Length INTEGER
        )
    """)
    
    conn.execute("""
        CREATE TABLE dim_proteins (
            Protein_ID VARCHAR PRIMARY KEY,
            Phage_ID VARCHAR
        )
    """)
    
    # Create dim_hosts table (this exists)
    conn.execute("""
        CREATE TABLE dim_hosts (
            Host_ID VARCHAR PRIMARY KEY,
            Species_Name VARCHAR
        )
    """)
    
    # Note: We intentionally DO NOT create phage_host_associations table
    # to simulate the error scenario
    
    # Add some test data
    conn.execute("INSERT INTO fact_phages VALUES ('phage1', 50000), ('phage2', 60000)")
    conn.execute("INSERT INTO dim_proteins VALUES ('prot1', 'phage1'), ('prot2', 'phage2')")
    conn.execute("INSERT INTO dim_hosts VALUES ('host1', 'E. coli')")
    
    conn.close()
    
    return db_path


def create_test_fasta_files():
    """Create minimal test FASTA files"""
    phage_fasta = tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False)
    phage_fasta.write(">phage1\nATCG\n>phage2\nGCTA\n")
    phage_fasta.close()
    
    protein_fasta = tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False)
    protein_fasta.write(">prot1\nMKL\n>prot2\nMPL\n")
    protein_fasta.close()
    
    return phage_fasta.name, protein_fasta.name


def test_get_stats_with_missing_phage_host_associations():
    """
    Test that get_stats() doesn't raise KeyError when phage_host_associations table is missing.
    """
    print("="*80)
    print("🧪 Testing get_stats() with missing phage_host_associations table")
    print("="*80)
    
    # Create test database and FASTA files
    db_path = create_test_database_with_missing_table()
    phage_fasta, protein_fasta = create_test_fasta_files()
    
    try:
        # Initialize retriever with preload disabled
        retriever = SequenceRetriever(
            db_path=db_path,
            phage_fasta_path=phage_fasta,
            protein_fasta_path=protein_fasta,
            preload=False  # Disable background loading for test
        )
        
        print("\n📋 Calling get_stats()...")
        # This should NOT raise a KeyError even though phage_host_associations is missing
        stats = retriever.get_stats()
        
        # Verify basic stats are present
        assert 'database' in stats, "Stats should contain 'database' key"
        assert 'fasta' in stats, "Stats should contain 'fasta' key"
        assert stats['database']['phages'] == 2, "Should have 2 phages"
        assert stats['database']['proteins'] == 2, "Should have 2 proteins"
        
        # Verify hosts count is present (since dim_hosts table exists)
        assert 'hosts' in stats['database'], "Should have hosts in database stats"
        assert stats['database']['hosts'] == 1, "Should have 1 host"
        
        # Verify phage_host_associations is NOT in stats (since the table doesn't exist)
        # and that it doesn't cause a KeyError
        if 'phage_host_associations' in stats['database']:
            print("⚠️  phage_host_associations found in stats (unexpected but not an error)")
        else:
            print("✅ phage_host_associations not in stats (expected)")
        
        print("\n✅ TEST PASSED: get_stats() handled missing table gracefully")
        print(f"📊 Stats returned: {stats}")
        
        retriever.close()
        
    finally:
        # Cleanup
        os.unlink(db_path)
        os.unlink(phage_fasta)
        os.unlink(protein_fasta)
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)


if __name__ == "__main__":
    test_get_stats_with_missing_phage_host_associations()

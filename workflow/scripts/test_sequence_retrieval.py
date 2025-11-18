#!.pixi/envs/default/bin/python

from sequence_retrieval import SequenceRetriever
import logging

logging.basicConfig(level=logging.INFO)

def test_sequence_retrieval():
    """Comprehensive test of sequence retrieval"""
    
    print("="*80)
    print("🧪 SEQUENCE RETRIEVAL TEST SUITE")
    print("="*80)
    
    # Paths
    db_path = "../data/databases/phage_database_optimized.duckdb"
    phage_fasta = "../data/sequences/all_phages.fasta"
    protein_fasta = "../data/sequences/all_proteins.fasta"
    
    # Initialize retriever
    print("\n📋 Test 1: Initialization")
    retriever = SequenceRetriever(db_path, phage_fasta, protein_fasta)
    print("✅ Retriever initialized")
    
    # Test stats
    print("\n📋 Test 2: Get Statistics")
    stats = retriever.get_stats()
    assert stats['database']['phages'] > 0, "No phages in database"
    assert stats['database']['proteins'] > 0, "No proteins in database"
    print("✅ Stats retrieved")
    
    # Test phage query
    print("\n📋 Test 3: Phage Query Retrieval")
    query = "SELECT Phage_ID FROM fact_phages WHERE Length > 50000 LIMIT 10"
    phage_df = retriever.get_phage_sequences(query)
    assert len(phage_df) > 0, "No phages retrieved"
    assert 'sequence' in phage_df.columns, "Missing sequence column"
    print(f"✅ Retrieved {len(phage_df)} phages")
    print(phage_df[['Phage_ID', 'length']].head())
    
    # Test protein query
    print("\n📋 Test 4: Protein Query Retrieval")
    query = "SELECT Protein_ID FROM dim_proteins LIMIT 10"
    protein_df = retriever.get_protein_sequences(query)
    assert len(protein_df) > 0, "No proteins retrieved"
    print(f"✅ Retrieved {len(protein_df)} proteins")
    print(protein_df[['Protein_ID', 'length']].head())
    
    # Test direct ID retrieval
    print("\n📋 Test 5: Direct ID Retrieval")
    sample_phage_ids = phage_df['Phage_ID'].head(3).tolist()
    sample_protein_ids = protein_df['Protein_ID'].head(3).tolist()
    
    result = retriever.get_sequences_by_ids(
        phage_ids=sample_phage_ids,
        protein_ids=sample_protein_ids
    )
    assert 'phages' in result, "Missing phages in result"
    assert 'proteins' in result, "Missing proteins in result"
    print(f"✅ Retrieved {len(result['phages'])} phages and {len(result['proteins'])} proteins")
    
    # Test export
    print("\n📋 Test 6: FASTA Export")
    retriever.export_fasta(phage_df.head(5), "test_phages.fasta", "Phage_ID")
    retriever.export_fasta(protein_df.head(5), "test_proteins.fasta", "Protein_ID")
    print("✅ FASTA files exported")
    
    # Test proteins by phage
    print("\n📋 Test 7: Get Proteins by Phage")
    sample_phage = sample_phage_ids[0]
    proteins_for_phage = retriever.get_protein_sequences_by_phage(sample_phage)
    print(f"✅ Retrieved {len(proteins_for_phage)} proteins for phage {sample_phage}")
    
    # Cleanup
    retriever.close()
    
    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)

if __name__ == "__main__":
    test_sequence_retrieval()
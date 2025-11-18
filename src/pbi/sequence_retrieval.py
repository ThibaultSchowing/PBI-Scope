#!.pixi/envs/default/bin/python

import duckdb
from pyfaidx import Fasta
from typing import List, Dict, Optional
import pandas as pd
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SequenceRetriever:
    """
    Retrieve sequences from indexed FASTA files based on DuckDB queries
    
    Features:
    - Query-based sequence retrieval from DuckDB
    - Direct ID-based retrieval
    - Batch processing support
    - Missing sequence handling
    - Memory-efficient streaming
    - Handles full FASTA headers (Phage_ID + Protein_ID format)
    """
    
    def __init__(self, db_path: str, phage_fasta_path: str, protein_fasta_path: str):
        """
        Initialize SequenceRetriever
        
        Args:
            db_path: Path to DuckDB database
            phage_fasta_path: Path to indexed phage FASTA file
            protein_fasta_path: Path to indexed protein FASTA file
        """
        # Validate paths
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        if not Path(phage_fasta_path).exists():
            raise FileNotFoundError(f"Phage FASTA not found: {phage_fasta_path}")
        if not Path(protein_fasta_path).exists():
            raise FileNotFoundError(f"Protein FASTA not found: {protein_fasta_path}")
        
        # Check for index files
        phage_index = Path(str(phage_fasta_path) + '.fai')
        protein_index = Path(str(protein_fasta_path) + '.fai')
        
        if not phage_index.exists():
            raise FileNotFoundError(f"Phage FASTA index not found: {phage_index}")
        if not protein_index.exists():
            raise FileNotFoundError(f"Protein FASTA index not found: {protein_index}")
        
        # Initialize connections
        logging.info(f"📂 Connecting to database: {db_path}")
        self.conn = duckdb.connect(db_path, read_only=True)
        
        logging.info(f"📂 Loading phage FASTA index: {phage_fasta_path}")
        # Use split_char to preserve full headers as keys
        self.phage_fasta = Fasta(
            phage_fasta_path,
            split_char='\x00',  # Null byte - won't appear in headers
            read_long_names=True
        )
        logging.info(f"   ✅ {len(self.phage_fasta.keys()):,} phage sequences indexed")
        
        logging.info(f"📂 Loading protein FASTA index: {protein_fasta_path}")
        # CRITICAL: Use split_char to preserve full headers (Phage_ID + Protein_ID)
        self.protein_fasta = Fasta(
            protein_fasta_path,
            split_char='\x00',  # Null byte - won't appear in headers
            read_long_names=True
        )
        logging.info(f"   ✅ {len(self.protein_fasta.keys()):,} protein sequences indexed")
        
        # Sample keys to verify format
        sample_phage = list(self.phage_fasta.keys())[:3]
        sample_protein = list(self.protein_fasta.keys())[:3]
        
        logging.info(f"🔍 Sample phage keys:")
        for key in sample_phage:
            logging.info(f"   - '{key[:80]}...'")
        
        logging.info(f"🔍 Sample protein keys:")
        for key in sample_protein:
            logging.info(f"   - '{key[:80]}...'")
    
    def get_phage_sequences(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get phage sequences based on SQL query
        
        Args:
            query: SQL query that returns Phage_ID column
            limit: Optional limit on number of sequences
        
        Returns:
            DataFrame with columns: Phage_ID, sequence, length
        
        Example:
            query = "SELECT Phage_ID FROM fact_phages WHERE Length > 50000"
            df = retriever.get_phage_sequences(query, limit=1000)
        """
        logging.info(f"🔍 Executing query: {query[:100]}...")
        
        if limit:
            query = f"{query} LIMIT {limit}"
        
        result = self.conn.execute(query).fetchdf()
        
        if 'Phage_ID' not in result.columns:
            raise ValueError("Query must return 'Phage_ID' column")
        
        phage_ids = result['Phage_ID'].tolist()
        logging.info(f"📊 Retrieved {len(phage_ids):,} Phage IDs from query")
        
        return self._fetch_phage_sequences(phage_ids)
    
    def get_protein_sequences(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get protein sequences based on SQL query
        
        Args:
            query: SQL query that returns Protein_ID column (full header)
            limit: Optional limit on number of sequences
        
        Returns:
            DataFrame with columns: Protein_ID, sequence, length
        
        Example:
            query = "SELECT Protein_ID FROM dim_proteins WHERE Molecular_weight > 50000"
            df = retriever.get_protein_sequences(query, limit=1000)
        """
        logging.info(f"🔍 Executing query: {query[:100]}...")
        
        if limit:
            query = f"{query} LIMIT {limit}"
        
        result = self.conn.execute(query).fetchdf()
        
        if 'Protein_ID' not in result.columns:
            raise ValueError("Query must return 'Protein_ID' column")
        
        protein_ids = result['Protein_ID'].tolist()
        logging.info(f"📊 Retrieved {len(protein_ids):,} Protein IDs from query")
        
        return self._fetch_protein_sequences(protein_ids)
    
    def get_sequences_by_ids(self, 
                            phage_ids: Optional[List[str]] = None, 
                            protein_ids: Optional[List[str]] = None) -> Dict:
        """
        Direct ID-based retrieval
        
        Args:
            phage_ids: List of phage IDs to retrieve
            protein_ids: List of protein IDs to retrieve (full headers)
        
        Returns:
            Dictionary with 'phages' and/or 'proteins' DataFrames
        """
        result = {}
        
        if phage_ids:
            logging.info(f"🔍 Fetching {len(phage_ids):,} phage sequences")
            result['phages'] = self._fetch_phage_sequences(phage_ids)
        
        if protein_ids:
            logging.info(f"🔍 Fetching {len(protein_ids):,} protein sequences")
            result['proteins'] = self._fetch_protein_sequences(protein_ids)
        
        return result
    
    def get_protein_sequences_by_phage(self, phage_id: str) -> pd.DataFrame:
        """
        Get all protein sequences for a given phage
        
        Args:
            phage_id: Phage ID to retrieve proteins for
        
        Returns:
            DataFrame with protein sequences
        """
        query = f"""
            SELECT Protein_ID 
            FROM dim_proteins 
            WHERE Phage_ID = '{phage_id}'
        """
        return self.get_protein_sequences(query)
    
    def _fetch_phage_sequences(self, phage_ids: List[str]) -> pd.DataFrame:
        """Internal method to fetch phage sequences"""
        sequences = []
        missing = []
        
        for pid in phage_ids:
            try:
                # Try exact match first
                if pid in self.phage_fasta.keys():
                    seq = str(self.phage_fasta[pid])
                    sequences.append({
                        'Phage_ID': pid, 
                        'sequence': seq, 
                        'length': len(seq)
                    })
                else:
                    # Try fuzzy match (in case of formatting differences)
                    found = False
                    for key in self.phage_fasta.keys():
                        if key.startswith(pid):
                            seq = str(self.phage_fasta[key])
                            sequences.append({
                                'Phage_ID': pid,
                                'sequence': seq,
                                'length': len(seq)
                            })
                            found = True
                            break
                    if not found:
                        missing.append(pid)
                        
            except (KeyError, Exception) as e:
                missing.append(pid)
                logging.debug(f"Error fetching {pid}: {e}")
        
        if missing:
            logging.warning(f"⚠️ {len(missing):,} phage sequences not found in FASTA")
            if len(missing) <= 10:
                logging.warning(f"   Missing IDs: {', '.join(missing)}")
        
        logging.info(f"✅ Retrieved {len(sequences):,}/{len(phage_ids):,} phage sequences")
        
        return pd.DataFrame(sequences)
    
    def _fetch_protein_sequences(self, protein_ids: List[str]) -> pd.DataFrame:
        """
        Internal method to fetch protein sequences
        
        NOTE: Protein IDs should be the FULL header from metadata
        e.g., "NC_000866.4 YP_009137915.1 terminase large subunit"
        """
        sequences = []
        missing = []
        
        for pid in protein_ids:
            try:
                # Try exact match first
                if pid in self.protein_fasta.keys():
                    seq = str(self.protein_fasta[pid])
                    sequences.append({
                        'Protein_ID': pid, 
                        'sequence': seq, 
                        'length': len(seq)
                    })
                else:
                    # Try fuzzy match on second token (actual protein ID)
                    # If metadata has just "YP_009137915.1" but FASTA has full header
                    found = False
                    pid_parts = pid.split()
                    if len(pid_parts) > 0:
                        search_token = pid_parts[-1] if len(pid_parts) == 1 else pid_parts[1]
                        for key in self.protein_fasta.keys():
                            if search_token in key:
                                seq = str(self.protein_fasta[key])
                                sequences.append({
                                    'Protein_ID': pid,
                                    'sequence': seq,
                                    'length': len(seq)
                                })
                                found = True
                                break
                    if not found:
                        missing.append(pid)
                        
            except (KeyError, Exception) as e:
                missing.append(pid)
                logging.debug(f"Error fetching {pid}: {e}")
        
        if missing:
            logging.warning(f"⚠️ {len(missing):,} protein sequences not found in FASTA")
            if len(missing) <= 10:
                logging.warning(f"   Missing IDs: {', '.join(missing[:10])}")
        
        logging.info(f"✅ Retrieved {len(sequences):,}/{len(protein_ids):,} protein sequences")
        
        return pd.DataFrame(sequences)
    
    def export_fasta(self, df: pd.DataFrame, output_path: str, id_col: str = 'Phage_ID'):
        """
        Export sequences to FASTA file
        
        Args:
            df: DataFrame with sequence data
            output_path: Path to output FASTA file
            id_col: Column name containing sequence IDs
        """
        logging.info(f"💾 Exporting {len(df):,} sequences to: {output_path}")
        
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            for _, row in df.iterrows():
                f.write(f">{row[id_col]}\n")
                # Wrap sequence at 80 characters
                seq = row['sequence']
                for i in range(0, len(seq), 80):
                    f.write(f"{seq[i:i+80]}\n")
        
        logging.info(f"✅ FASTA file saved: {output_path}")
    
    def get_stats(self) -> Dict:
        """Get database and FASTA statistics"""
        stats = {
            'database': {
                'phages': self.conn.execute("SELECT COUNT(*) FROM fact_phages").fetchone()[0],
                'proteins': self.conn.execute("SELECT COUNT(*) FROM dim_proteins").fetchone()[0],
            },
            'fasta': {
                'phages': len(self.phage_fasta.keys()),
                'proteins': len(self.protein_fasta.keys()),
            }
        }
        
        logging.info(f"📊 Database Stats:")
        logging.info(f"   Phages: {stats['database']['phages']:,}")
        logging.info(f"   Proteins: {stats['database']['proteins']:,}")
        logging.info(f"📊 FASTA Stats:")
        logging.info(f"   Phages: {stats['fasta']['phages']:,}")
        logging.info(f"   Proteins: {stats['fasta']['proteins']:,}")
        
        return stats
    
    def close(self):
        """Close database connection"""
        self.conn.close()
        logging.info("🔒 Database connection closed")


# Example usage and testing
if __name__ == "__main__":
    import sys
    
    # Test script
    if len(sys.argv) < 4:
        print("Usage: sequence_retrieval.py <db_path> <phage_fasta> <protein_fasta>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    phage_fasta = sys.argv[2]
    protein_fasta = sys.argv[3]
    
    print("🧪 Testing SequenceRetriever")
    print("="*80)
    
    try:
        # Initialize
        retriever = SequenceRetriever(db_path, phage_fasta, protein_fasta)
        
        # Get stats
        retriever.get_stats()
        
        # Test 1: Get phages by query
        print("\n🧪 Test 1: Query-based phage retrieval")
        query = "SELECT Phage_ID FROM fact_phages WHERE Length > 50000 LIMIT 5"
        phage_df = retriever.get_phage_sequences(query)
        print(phage_df)
        
        # Test 2: Get proteins by query
        print("\n🧪 Test 2: Query-based protein retrieval")
        query = "SELECT Protein_ID FROM dim_proteins LIMIT 5"
        protein_df = retriever.get_protein_sequences(query)
        print(protein_df)
        
        # Test 3: Export to FASTA
        print("\n🧪 Test 3: Export to FASTA")
        retriever.export_fasta(phage_df, "test_output_phages.fasta", "Phage_ID")
        retriever.export_fasta(protein_df, "test_output_proteins.fasta", "Protein_ID")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        retriever.close()
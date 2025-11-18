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
        self.phage_fasta = Fasta(phage_fasta_path)
        logging.info(f"   ✅ {len(self.phage_fasta.keys()):,} phage sequences indexed")
        
        logging.info(f"📂 Loading protein FASTA index: {protein_fasta_path}")
        self.protein_fasta = Fasta(protein_fasta_path)
        logging.info(f"   ✅ {len(self.protein_fasta.keys()):,} protein sequences indexed")
    
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
            query: SQL query that returns Protein_ID column
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
            protein_ids: List of protein IDs to retrieve
        
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
    
    def _fetch_phage_sequences(self, phage_ids: List[str]) -> pd.DataFrame:
        """Internal method to fetch phage sequences"""
        sequences = []
        missing = []
        
        for pid in phage_ids:
            try:
                seq = str(self.phage_fasta[pid])
                sequences.append({
                    'Phage_ID': pid, 
                    'sequence': seq, 
                    'length': len(seq)
                })
            except KeyError:
                missing.append(pid)
        
        if missing:
            logging.warning(f"⚠️ {len(missing):,} phage sequences not found in FASTA")
            if len(missing) <= 10:
                logging.warning(f"   Missing IDs: {', '.join(missing)}")
        
        logging.info(f"✅ Retrieved {len(sequences):,}/{len(phage_ids):,} phage sequences")
        
        return pd.DataFrame(sequences)
    
    def _fetch_protein_sequences(self, protein_ids: List[str]) -> pd.DataFrame:
        """Internal method to fetch protein sequences"""
        sequences = []
        missing = []
        
        for pid in protein_ids:
            try:
                seq = str(self.protein_fasta[pid])
                sequences.append({
                    'Protein_ID': pid, 
                    'sequence': seq, 
                    'length': len(seq)
                })
            except KeyError:
                missing.append(pid)
        
        if missing:
            logging.warning(f"⚠️ {len(missing):,} protein sequences not found in FASTA")
            if len(missing) <= 10:
                logging.warning(f"   Missing IDs: {', '.join(missing)}")
        
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
        
        with open(output_path, 'w') as f:
            for _, row in df.iterrows():
                f.write(f">{row[id_col]}\n")
                f.write(f"{row['sequence']}\n")
        
        logging.info(f"✅ FASTA file saved: {output_path}")
    
    def close(self):
        """Close database connection"""
        self.conn.close()
        logging.info("🔒 Database connection closed")
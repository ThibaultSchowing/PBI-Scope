#!.pixi/envs/default/bin/python

import duckdb
from pyfaidx import Fasta
from typing import List, Dict, Optional
import pandas as pd
import logging
from pathlib import Path
import threading
import time
from typing import Optional
from Bio.SeqUtils import gc_fraction

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class SequenceRetriever:
    """
    Retrieve sequences from indexed FASTA files based on DuckDB queries
    
    Features:
    - Lazy loading with background thread support
    - Query-based sequence retrieval from DuckDB
    - Direct ID-based retrieval
    - Batch processing support
    - Memory-efficient streaming
    """
    
    def __init__(self, db_path: str, phage_fasta_path: str, protein_fasta_path: str, 
                 host_fasta_path: Optional[str] = None, preload: bool = True):
        """
        Initialize SequenceRetriever with lazy FASTA loading
        
        Args:
            db_path: Path to DuckDB database
            phage_fasta_path: Path to indexed phage FASTA file
            protein_fasta_path: Path to indexed protein FASTA file
            host_fasta_path: Path to indexed host FASTA file (optional)
            preload: If True, load FASTA files in background thread (default: True)
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
        
        logging.info(f"📂 Checking FASTA index files:")
        logging.info(f"   Phage index: {phage_index.exists()} ({phage_index.stat().st_size / 1024:.1f} KB)")
        logging.info(f"   Protein index: {protein_index.exists()} ({protein_index.stat().st_size / 1024:.1f} KB)")
        
        if not phage_index.exists():
            raise FileNotFoundError(f"Phage FASTA index not found: {phage_index}")
        if not protein_index.exists():
            raise FileNotFoundError(f"Protein FASTA index not found: {protein_index}")
        
        # Validate host FASTA if provided
        self._host_fasta_path = host_fasta_path
        self._host_fasta = None
        self._host_lock = threading.Lock()
        self._host_count = None
        self._has_host_data = False
        
        if host_fasta_path:
            if Path(host_fasta_path).exists():
                host_index = Path(str(host_fasta_path) + '.fai')
                if host_index.exists():
                    logging.info(f"   Host index: {host_index.exists()} ({host_index.stat().st_size / 1024:.1f} KB)")
                    self._has_host_data = True
                else:
                    logging.warning(f"⚠️  Host FASTA index not found: {host_index}")
            else:
                logging.warning(f"⚠️  Host FASTA not found: {host_fasta_path}")
        
        # Initialize database connection (fast)
        logging.info(f"📂 Connecting to database: {db_path}")
        self.conn = duckdb.connect(db_path, read_only=True)
        
        # Store paths for lazy loading
        self._phage_fasta_path = phage_fasta_path
        self._protein_fasta_path = protein_fasta_path
        
        # Lazy-loaded FASTA objects
        self._phage_fasta = None
        self._protein_fasta = None
        
        # Thread synchronization
        self._phage_lock = threading.Lock()
        self._protein_lock = threading.Lock()
        self._loading_complete = threading.Event()
        
        # Stats
        self._phage_count = None
        self._protein_count = None
        
        if preload:
            # Start background loading
            logging.info("🔄 Starting background FASTA loading...")
            self._load_thread = threading.Thread(target=self._preload_fasta, daemon=True)
            self._load_thread.start()
            logging.info("✅ Initialization complete (FASTA loading in background)")
        else:
            logging.info("✅ Initialization complete (FASTA files will load on first use)")
    
    def _preload_fasta(self):
        """Background task to load FASTA files"""
        start_total = time.time()
        
        try:
            # Load phage FASTA
            logging.info(f"🔄 [Background] Loading phage FASTA: {self._phage_fasta_path}")
            start = time.time()
            
            with self._phage_lock:
                self._phage_fasta = Fasta(
                    self._phage_fasta_path,
                    rebuild=False,
                    split_char='\x00',
                    read_long_names=True
                )
                self._phage_count = len(self._phage_fasta.keys())
            
            elapsed = time.time() - start
            logging.info(f"   ✅ Phage FASTA loaded in {elapsed:.2f}s ({self._phage_count:,} sequences)")
            
            # Load protein FASTA
            logging.info(f"🔄 [Background] Loading protein FASTA: {self._protein_fasta_path}")
            start = time.time()
            
            with self._protein_lock:
                self._protein_fasta = Fasta(
                    self._protein_fasta_path,
                    rebuild=False,
                    split_char='\x00',
                    read_long_names=True
                )
                self._protein_count = len(self._protein_fasta.keys())
            
            elapsed = time.time() - start
            logging.info(f"   ✅ Protein FASTA loaded in {elapsed:.2f}s ({self._protein_count:,} sequences)")
            
            # Load host FASTA if available
            if self._has_host_data and self._host_fasta_path:
                logging.info(f"🔄 [Background] Loading host FASTA: {self._host_fasta_path}")
                start = time.time()
                
                with self._host_lock:
                    self._host_fasta = Fasta(
                        self._host_fasta_path,
                        rebuild=False,
                        split_char='\x00',
                        read_long_names=True
                    )
                    self._host_count = len(self._host_fasta.keys())
                
                elapsed = time.time() - start
                logging.info(f"   ✅ Host FASTA loaded in {elapsed:.2f}s ({self._host_count:,} sequences)")
            
            # Mark as complete
            self._loading_complete.set()
            
            total_elapsed = time.time() - start_total
            logging.info(f"🎉 All FASTA files loaded in {total_elapsed:.2f}s")
            
            # Sample keys
            sample_phage = list(self._phage_fasta.keys())[:3]
            sample_protein = list(self._protein_fasta.keys())[:3]
            
            logging.info(f"🔍 Sample phage keys:")
            for key in sample_phage:
                logging.info(f"   - '{key[:80]}...'")
            
            logging.info(f"🔍 Sample protein keys:")
            for key in sample_protein:
                logging.info(f"   - '{key[:80]}...'")
            
            if self._host_fasta:
                sample_host = list(self._host_fasta.keys())[:3]
                logging.info(f"🔍 Sample host keys:")
                for key in sample_host:
                    logging.info(f"   - '{key[:80]}...'")
                
        except Exception as e:
            logging.error(f"❌ Error loading FASTA files: {e}")
            import traceback
            traceback.print_exc()
    
    @property
    def phage_fasta(self):
        """Get phage FASTA, loading if necessary"""
        if self._phage_fasta is None:
            with self._phage_lock:
                if self._phage_fasta is None:  # Double-check locking
                    logging.info(f"📂 Loading phage FASTA on-demand: {self._phage_fasta_path}")
                    start = time.time()
                    self._phage_fasta = Fasta(
                        self._phage_fasta_path,
                        rebuild=False,
                        split_char='\x00',
                        read_long_names=True
                    )
                    elapsed = time.time() - start
                    logging.info(f"   ✅ Loaded in {elapsed:.2f}s")
        return self._phage_fasta
    
    @property
    def protein_fasta(self):
        """Get protein FASTA, loading if necessary"""
        if self._protein_fasta is None:
            with self._protein_lock:
                if self._protein_fasta is None:  # Double-check locking
                    logging.info(f"📂 Loading protein FASTA on-demand: {self._protein_fasta_path}")
                    start = time.time()
                    self._protein_fasta = Fasta(
                        self._protein_fasta_path,
                        rebuild=False,
                        split_char='\x00',
                        read_long_names=True
                    )
                    elapsed = time.time() - start
                    logging.info(f"   ✅ Loaded in {elapsed:.2f}s")
        return self._protein_fasta
    
    @property
    def host_fasta(self):
        """Get host FASTA, loading if necessary"""
        if not self._has_host_data:
            raise ValueError("Host FASTA not configured - pass host_fasta_path to __init__")
        
        if self._host_fasta is None:
            with self._host_lock:
                if self._host_fasta is None:  # Double-check locking
                    logging.info(f"📂 Loading host FASTA on-demand: {self._host_fasta_path}")
                    start = time.time()
                    self._host_fasta = Fasta(
                        self._host_fasta_path,
                        rebuild=False,
                        split_char='\x00',
                        read_long_names=True
                    )
                    elapsed = time.time() - start
                    logging.info(f"   ✅ Loaded in {elapsed:.2f}s")
        return self._host_fasta
    
    def wait_until_ready(self, timeout: Optional[float] = None):
        """
        Wait for background loading to complete
        
        Args:
            timeout: Maximum seconds to wait (None = wait forever)
        
        Returns:
            bool: True if loading completed, False if timeout
        """
        if not hasattr(self, '_load_thread'):
            return True  # No background loading was started
        
        logging.info("⏳ Waiting for FASTA loading to complete...")
        result = self._loading_complete.wait(timeout=timeout)
        
        if result:
            logging.info("✅ FASTA loading complete")
        else:
            logging.warning(f"⚠️ Timeout after {timeout}s - FASTA may still be loading")
        
        return result
    
    def is_ready(self) -> bool:
        """Check if FASTA files are loaded"""
        return self._loading_complete.is_set()
    
    def get_phage_sequences(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get phage sequences based on SQL query
        
        Note: Will wait for phage FASTA to load if background loading is still in progress
        """
        # Ensure phage FASTA is loaded (property handles this)
        _ = self.phage_fasta  # Trigger loading if needed
        
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
        
        Note: Will wait for protein FASTA to load if background loading is still in progress
        """
        # Ensure protein FASTA is loaded (property handles this)
        _ = self.protein_fasta  # Trigger loading if needed
        
        logging.info(f"🔍 Executing query: {query[:100]}...")
        
        if limit:
            query = f"{query} LIMIT {limit}"
        
        result = self.conn.execute(query).fetchdf()
        
        if 'Protein_ID' not in result.columns:
            raise ValueError("Query must return 'Protein_ID' column")
        
        protein_ids = result['Protein_ID'].tolist()
        logging.info(f"📊 Retrieved {len(protein_ids):,} Protein IDs from query")
        
        return self._fetch_protein_sequences(protein_ids)
    
    def get_stats(self) -> Dict:
        """
        Get database and FASTA statistics
        
        Note: Will wait for FASTA loading to complete
        """
        # Wait for background loading if still running
        if hasattr(self, '_load_thread') and not self.is_ready():
            self.wait_until_ready(timeout=300)  # 5 minute timeout
        
        # Ensure FASTA files are loaded
        _ = self.phage_fasta
        _ = self.protein_fasta
        
        stats = {
            'database': {
                'phages': self.conn.execute("SELECT COUNT(*) FROM fact_phages").fetchone()[0],
                'proteins': self.conn.execute("SELECT COUNT(*) FROM dim_proteins").fetchone()[0],
            },
            'fasta': {
                'phages': self._phage_count if self._phage_count else len(self.phage_fasta.keys()),
                'proteins': self._protein_count if self._protein_count else len(self.protein_fasta.keys()),
            }
        }
        
        # Add host stats if available
        if self._has_host_data:
            try:
                stats['database']['hosts'] = self.conn.execute("SELECT COUNT(*) FROM dim_hosts").fetchone()[0]
                stats['database']['phage_host_associations'] = self.conn.execute(
                    "SELECT COUNT(*) FROM phage_host_associations"
                ).fetchone()[0]
                
                _ = self.host_fasta
                stats['fasta']['hosts'] = self._host_count if self._host_count else len(self.host_fasta.keys())
            except Exception as e:
                logging.debug(f"Host stats not available: {e}")
        
        logging.info(f"📊 Database Stats:")
        logging.info(f"   Phages: {stats['database']['phages']:,}")
        logging.info(f"   Proteins: {stats['database']['proteins']:,}")
        if 'hosts' in stats['database']:
            logging.info(f"   Hosts: {stats['database']['hosts']:,}")
            logging.info(f"   Phage-Host Associations: {stats['database']['phage_host_associations']:,}")
        
        logging.info(f"📊 FASTA Stats:")
        logging.info(f"   Phages: {stats['fasta']['phages']:,}")
        logging.info(f"   Proteins: {stats['fasta']['proteins']:,}")
        if 'hosts' in stats['fasta']:
            logging.info(f"   Hosts: {stats['fasta']['hosts']:,}")
        
        return stats

    
    def get_host_sequences(self, query: str, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get host sequences based on SQL query
        
        Args:
            query: SQL query that returns Host_ID column
            limit: Optional limit on number of sequences
        
        Returns:
            DataFrame with columns: Host_ID, Species_Name, Sequence, Length, GC_Content
        
        Example:
            query = "SELECT Host_ID FROM dim_hosts WHERE Species_Name LIKE '%Escherichia%'"
            df = retriever.get_host_sequences(query)
        """
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")
        
        # Ensure host FASTA is loaded
        _ = self.host_fasta
        
        logging.info(f"🔍 Executing query: {query[:100]}...")
        
        if limit:
            query = f"{query} LIMIT {limit}"
        
        result = self.conn.execute(query).fetchdf()
        
        if 'Host_ID' not in result.columns:
            raise ValueError("Query must return 'Host_ID' column")
        
        host_ids = result['Host_ID'].tolist()
        logging.info(f"📊 Retrieved {len(host_ids):,} Host IDs from query")
        
        return self._fetch_host_sequences(host_ids)
    
    def get_host_by_phage(self, phage_id: str) -> pd.DataFrame:
        """
        Get host genome(s) for a given phage
        
        Args:
            phage_id: Phage ID
        
        Returns:
            DataFrame with host sequences associated with the phage
        
        Example:
            df = retriever.get_host_by_phage("NC_000866")
        """
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")
        
        query = f"""
        SELECT h.Host_ID
        FROM phage_host_associations pha
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        WHERE pha.Phage_ID = '{phage_id}'
        """
        
        return self.get_host_sequences(query)
    
    def get_phage_host_pairs(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get phage-host interaction pairs with sequences
        
        Args:
            where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
            limit: Optional limit on number of pairs
        
        Returns:
            DataFrame with columns: Phage_ID, Host_ID, Phage_Sequence, Host_Sequence,
                                    Phage_Length, Host_Length, Phage_GC, Host_GC
        
        Example:
            # Get all pairs
            pairs = retriever.get_phage_host_pairs()
            
            # Get pairs for specific lifestyle
            pairs = retriever.get_phage_host_pairs("p.Lifestyle = 'Lytic'", limit=1000)
        """
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")
        
        # Ensure FASTA files are loaded
        _ = self.phage_fasta
        _ = self.host_fasta
        
        # Build query
        query = """
        SELECT DISTINCT
            pha.Phage_ID,
            pha.Host_ID,
            p.Length as Phage_Length,
            p.GC_content as Phage_GC,
            h.Genome_Length as Host_Length,
            h.GC_Content as Host_GC,
            p.Lifestyle,
            h.Species_Name
        FROM phage_host_associations pha
        JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        """
        
        if where_clause:
            query += f" WHERE {where_clause}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        logging.info(f"🔍 Querying phage-host pairs...")
        result = self.conn.execute(query).fetchdf()
        
        logging.info(f"📊 Found {len(result):,} phage-host pairs")
        
        # Fetch sequences
        phage_ids = result['Phage_ID'].tolist()
        host_ids = result['Host_ID'].tolist()
        
        logging.info(f"📥 Fetching sequences for {len(phage_ids):,} phages and {len(set(host_ids)):,} unique hosts")
        
        phage_seqs = {}
        host_seqs = {}
        
        # Fetch phage sequences
        for phage_id in phage_ids:
            try:
                seq = self.phage_fasta[phage_id][:].seq
                phage_seqs[phage_id] = str(seq)
            except KeyError:
                phage_seqs[phage_id] = None
        
        # Fetch host sequences (unique only)
        for host_id in set(host_ids):
            try:
                seq = self.host_fasta[host_id][:].seq
                host_seqs[host_id] = str(seq)
            except KeyError:
                host_seqs[host_id] = None
        
        # Add sequences to result
        result['Phage_Sequence'] = result['Phage_ID'].map(phage_seqs)
        result['Host_Sequence'] = result['Host_ID'].map(host_seqs)
        
        # Filter out rows with missing sequences
        before_count = len(result)
        result = result.dropna(subset=['Phage_Sequence', 'Host_Sequence'])
        after_count = len(result)
        
        if before_count > after_count:
            logging.warning(f"⚠️  Removed {before_count - after_count} pairs with missing sequences")
        
        logging.info(f"✅ Retrieved {len(result):,} complete phage-host pairs with sequences")
        
        return result
    
    def _fetch_host_sequences(self, host_ids: list) -> pd.DataFrame:
        """
        Fetch host sequences for given Host IDs
        
        Args:
            host_ids: List of Host IDs to retrieve sequences for
        
        Returns:
            DataFrame with Host_ID and Sequence columns
        """
        if not host_ids:
            logging.warning("No Host IDs provided")
            return pd.DataFrame(columns=['Host_ID', 'Sequence', 'Length', 'GC_Content'])
        
        logging.info(f"🔍 Fetching sequences for {len(host_ids):,} hosts")
        
        sequences = []
        missing_ids = []
        
        for host_id in host_ids:
            try:
                seq = self.host_fasta[host_id][:].seq
                sequences.append({
                    'Host_ID': host_id,
                    'Sequence': str(seq),
                    'Length': len(seq),
                    'GC_Content': round(gc_fraction(seq) * 100, 2) if len(seq) > 0 else 0.0
                })
            except KeyError:
                missing_ids.append(host_id)
                logging.warning(f"⚠️  Host ID '{host_id}' not found in FASTA")
        
        if missing_ids:
            logging.warning(f"⚠️  {len(missing_ids):,} host IDs not found in FASTA file")
        
        df = pd.DataFrame(sequences)
        logging.info(f"✅ Retrieved {len(df):,} sequences")
        
        return df
    
    def help(self):
        """Print help information"""
        help_text = """
        SequenceRetriever Help:
        
        Methods:
            - get_phage_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_protein_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_sequences_by_ids(phage_ids: Optional[List[str]] = None, protein_ids: Optional[List[str]] = None) -> Dict
            - get_protein_sequences_by_phage(phage_id: str) -> pd.DataFrame
            - export_fasta(df: pd.DataFrame, output_path: str, id_col: str = 'Phage_ID')
            - get_stats() -> Dict
            - close()
        
        Usage Examples:
            retriever = SequenceRetriever(db_path, phage_fasta_path, protein_fasta_path)
            phage_df = retriever.get_phage_sequences("SELECT Phage_ID FROM fact_phages WHERE Length > 50000", limit=100)
            protein_df = retriever.get_protein_sequences("SELECT Protein_ID FROM dim_proteins WHERE Molecular_weight > 50000", limit=100)
            retriever.export_fasta(phage_df, "output_phages.fasta", id_col='Phage_ID')
            stats = retriever.get_stats()
            retriever.close()
        """
        print(help_text)
    
    def close(self):
        """Close database connection"""
        self.conn.close()
        logging.info("🔒 Database connection closed")
    
    def _fetch_phage_sequences(self, phage_ids: list) -> pd.DataFrame:
        """
        Fetch phage sequences for given Phage IDs.
        
        Args:
            phage_ids: List of Phage IDs to retrieve sequences for
            
        Returns:
            DataFrame with Phage_ID and Sequence columns
        """
        if not phage_ids:
            logging.warning("No Phage IDs provided")
            return pd.DataFrame(columns=['Phage_ID', 'Sequence'])
        
        logging.info(f"🔍 Fetching sequences for {len(phage_ids):,} phages")
        
        # Read sequences from the FASTA index
        sequences = []
        missing_ids = []
        
        for phage_id in phage_ids:
            try:
                # Fetch sequence from indexed FASTA
                seq = self.phage_fasta[phage_id][:].seq
                sequences.append({
                    'Phage_ID': phage_id,
                    'Sequence': str(seq)
                })
            except KeyError:
                missing_ids.append(phage_id)
                logging.warning(f"⚠️  Phage ID '{phage_id}' not found in FASTA")
        
        if missing_ids:
            logging.warning(f"⚠️  {len(missing_ids):,} phage IDs not found in FASTA file")
        
        df = pd.DataFrame(sequences)
        logging.info(f"✅ Retrieved {len(df):,} sequences")
        
        return df

    def _fetch_protein_sequences(self, protein_ids: list) -> pd.DataFrame:
        """
        Fetch protein sequences for given Protein IDs.
        
        Args:
            protein_ids: List of Protein IDs to retrieve sequences for
            
        Returns:
            DataFrame with Protein_ID and Sequence columns
        """
        if not protein_ids:
            logging.warning("No Protein IDs provided")
            return pd.DataFrame(columns=['Protein_ID', 'Sequence'])
        
        logging.info(f"🔍 Fetching sequences for {len(protein_ids):,} proteins")
        
        sequences = []
        missing_ids = []
        
        for protein_id in protein_ids:
            try:
                seq = self.protein_fasta[protein_id][:].seq
                sequences.append({
                    'Protein_ID': protein_id,
                    'Sequence': str(seq)
                })
            except KeyError:
                missing_ids.append(protein_id)
                logging.warning(f"⚠️  Protein ID '{protein_id}' not found in FASTA")
        
        if missing_ids:
            logging.warning(f"⚠️  {len(missing_ids):,} protein IDs not found in FASTA file")
        
        df = pd.DataFrame(sequences)
        logging.info(f"✅ Retrieved {len(df):,} sequences")
        
        return df

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
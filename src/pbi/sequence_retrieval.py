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


def parse_where_clause(where_clause: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Parse a where_clause that may contain WHERE conditions, LIMIT, and/or OFFSET.
    
    Args:
        where_clause: The clause to parse (e.g., "LIMIT 100", "p.Length > 1000 LIMIT 50", 
                     "LIMIT 1000 OFFSET 5000", etc.)
    
    Returns:
        Tuple of (where_conditions, limit_offset_clause)
        - where_conditions: The WHERE conditions only (without LIMIT/OFFSET), or None
        - limit_offset_clause: The LIMIT/OFFSET clause only, or None
    
    Examples:
        >>> parse_where_clause("LIMIT 100")
        (None, "LIMIT 100")
        >>> parse_where_clause("p.Length > 1000 LIMIT 50")
        ("p.Length > 1000", "LIMIT 50")
        >>> parse_where_clause("LIMIT 1000 OFFSET 5000")
        (None, "LIMIT 1000 OFFSET 5000")
        >>> parse_where_clause("p.GC > 0.5")
        ("p.GC > 0.5", None)
    """
    if not where_clause:
        return None, None
    
    # Normalize whitespace
    clause = ' '.join(where_clause.split())
    
    # Case-insensitive search for LIMIT keyword
    clause_upper = clause.upper()
    limit_pos = clause_upper.find(' LIMIT ')
    
    # Handle case where LIMIT is at the start
    if clause_upper.startswith('LIMIT '):
        limit_pos = 0
    
    if limit_pos == -1:
        # No LIMIT clause found
        return clause.strip(), None
    elif limit_pos == 0:
        # LIMIT is at the start, no WHERE conditions
        return None, clause.strip()
    else:
        # Split at LIMIT position
        where_part = clause[:limit_pos].strip()
        limit_part = clause[limit_pos:].strip()
        
        return where_part if where_part else None, limit_part if limit_part else None


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
                 host_fasta_path: Optional[str] = None, host_mapping_path: Optional[str] = None,
                 preload: bool = True):
        """
        Initialize SequenceRetriever with lazy FASTA loading
        
        Args:
            db_path: Path to DuckDB database
            phage_fasta_path: Path to indexed phage FASTA file
            protein_fasta_path: Path to indexed protein FASTA file
            host_fasta_path: Path to indexed host FASTA file (DEPRECATED - use host_mapping_path)
            host_mapping_path: Path to JSON mapping file for individual host FASTA files
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
        
        # Initialize host data handling
        self._host_fasta_path = host_fasta_path  # Legacy single-file mode
        self._host_mapping_path = host_mapping_path  # New mapping mode
        self._host_mapping = None  # Mapping from Host_ID to file path
        self._host_fasta_cache = {}  # Cache of loaded Fasta objects per host
        self._host_fasta = None  # For legacy single-file mode
        self._host_lock = threading.Lock()
        self._host_count = None
        self._has_host_data = False
        self._use_host_mapping = False
        
        # Check if using new mapping-based approach
        if host_mapping_path:
            if Path(host_mapping_path).exists():
                logging.info(f"📂 Using host mapping file: {host_mapping_path}")
                self._has_host_data = True
                self._use_host_mapping = True
                # Load mapping file
                import json
                with open(host_mapping_path, 'r') as f:
                    self._host_mapping = json.load(f)
                self._host_count = len(self._host_mapping)
                logging.info(f"   Loaded mapping for {self._host_count} hosts")
            else:
                logging.warning(f"⚠️  Host mapping file not found: {host_mapping_path}")
        # Fallback to legacy single-file mode
        elif host_fasta_path:
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
            
            # Load host FASTA if available (only for legacy single-file mode)
            if self._has_host_data and self._host_fasta_path and not self._use_host_mapping:
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
            elif self._use_host_mapping:
                logging.info(f"   ℹ️  Using on-demand loading for {self._host_count:,} individual host files")
            
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
        """
        Get host FASTA, loading if necessary
        
        DEPRECATED: This property is maintained for backward compatibility
        but is not available when using host_mapping_path. Use 
        get_host_sequence() method instead for individual host access.
        """
        if not self._has_host_data:
            raise ValueError("Host FASTA not configured - pass host_fasta_path or host_mapping_path to __init__")
        
        # If using mapping mode, this operation is not supported
        if self._use_host_mapping:
            raise ValueError(
                "Direct access to host_fasta is not available when using host_mapping_path. "
                "The host genomes are stored as individual files for efficiency. "
                "Use get_host_sequence(host_id) method instead to load individual host files on-demand."
            )
        
        # Legacy single-file mode
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
    
    def _get_host_fasta_for_id(self, host_id: str) -> Fasta:
        """
        Get Fasta object for a specific host ID (used in mapping mode)
        
        Args:
            host_id: Host identifier
            
        Returns:
            Fasta object for the host genome
            
        Raises:
            KeyError: If host_id not found in mapping
            FileNotFoundError: If host file doesn't exist
        """
        if not self._use_host_mapping:
            # Should not be called in legacy mode
            raise RuntimeError("This method is only for host mapping mode")
        
        # Check if already cached
        if host_id in self._host_fasta_cache:
            return self._host_fasta_cache[host_id]
        
        # Get file path from mapping
        if host_id not in self._host_mapping:
            raise KeyError(f"Host ID '{host_id}' not found in mapping")
        
        fasta_path = self._host_mapping[host_id]
        
        # Load the fasta file
        with self._host_lock:
            if host_id not in self._host_fasta_cache:  # Double-check locking
                logging.debug(f"Loading host FASTA for {host_id}: {fasta_path}")
                fasta_obj = Fasta(
                    fasta_path,
                    rebuild=False,
                    split_char='\x00',
                    read_long_names=True
                )
                self._host_fasta_cache[host_id] = fasta_obj
        
        return self._host_fasta_cache[host_id]
    
    def get_host_sequence(self, host_id: str) -> str:
        """
        Get sequence for a specific host ID
        
        Works with both legacy single-file mode and new mapping mode.
        In mapping mode, loads individual host files on-demand.
        
        Args:
            host_id: Host identifier
            
        Returns:
            Host sequence as string
            
        Raises:
            KeyError: If host_id not found
        """
        if not self._has_host_data:
            raise ValueError("Host FASTA not configured")
        
        if self._use_host_mapping:
            # New mapping mode - load individual file
            fasta_obj = self._get_host_fasta_for_id(host_id)
            # The fasta file should contain the host genome
            # Get the first (and typically only) sequence
            keys = list(fasta_obj.keys())
            if not keys:
                raise KeyError(f"No sequences found in host file for {host_id}")
            # Return the sequence from the file
            return str(fasta_obj[keys[0]][:].seq)
        else:
            # Legacy mode - use single merged file
            return str(self.host_fasta[host_id][:].seq)
    
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
                
                # For mapping mode, use the count from the mapping
                if self._use_host_mapping:
                    stats['fasta']['hosts'] = self._host_count
                else:
                    # Legacy mode - access the merged file
                    _ = self.host_fasta
                    stats['fasta']['hosts'] = self._host_count if self._host_count else len(self.host_fasta.keys())
            except Exception as e:
                logging.warning(f"Host data configured but tables not found. Run host genome workflow first. Error: {e}")
                self._has_host_data = False  # Disable host support if tables don't exist
        
        logging.info(f"📊 Database Stats:")
        logging.info(f"   Phages: {stats['database']['phages']:,}")
        logging.info(f"   Proteins: {stats['database']['proteins']:,}")
        if 'hosts' in stats['database']:
            logging.info(f"   Hosts: {stats['database']['hosts']:,}")
            if 'phage_host_associations' in stats['database']:
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
            raise ValueError(
                "Host data not available. Please run the host genome download workflow first:\n"
                "  snakemake --use-conda --cores 1 all_hosts\n"
                "Or check that host_fasta_path or host_mapping_path was provided when creating SequenceRetriever."
            )
        
        # In legacy mode, ensure host FASTA is loaded
        if not self._use_host_mapping:
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
        Get phage-host interaction pairs with sequences and metadata
        
        Args:
            where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
            limit: Optional limit on number of pairs
        
        Returns:
            DataFrame with columns: Phage_ID, Host_ID, Phage_Source, Phage_Length, Phage_GC,
                                    Phage_Taxonomy, Phage_Completeness, Phage_Lifestyle, Phage_Cluster,
                                    Phage_Subcluster, Species_Name, Host_Assembly_Level, Host_Length,
                                    Host_GC, Host_RefSeq_Category, Phage_Sequence, Host_Sequence
        
        Example:
            # Get all pairs
            pairs = retriever.get_phage_host_pairs()
            
            # Get pairs for specific lifestyle
            pairs = retriever.get_phage_host_pairs("p.Lifestyle = 'Lytic'", limit=1000)
            
            # Get pairs from specific source
            pairs = retriever.get_phage_host_pairs("p.Source_DB = 'PhagesDB'")
            
            # Get pairs with complete host genomes
            pairs = retriever.get_phage_host_pairs("h.Assembly_Level = 'Complete Genome'")
        """
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")
        
        # Ensure FASTA files are loaded (phage always needs to be loaded)
        _ = self.phage_fasta
        # For legacy mode, ensure host FASTA is loaded
        if not self._use_host_mapping:
            _ = self.host_fasta
        
        # Build query
        query = """
        SELECT DISTINCT
            pha.Phage_ID,
            pha.Host_ID,
            p.Source_DB as Phage_Source,
            p.Length as Phage_Length,
            p.GC_content as Phage_GC,
            p.Taxonomy as Phage_Taxonomy,
            p.Completeness as Phage_Completeness,
            p.Lifestyle as Phage_Lifestyle,
            p.Cluster as Phage_Cluster,
            p.Subcluster as Phage_Subcluster,
            h.Species_Name,
            h.Assembly_Level as Host_Assembly_Level,
            h.Genome_Length as Host_Length,
            h.GC_Content as Host_GC,
            h.RefSeq_Category as Host_RefSeq_Category
        FROM phage_host_associations pha
        JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        """
        
        # Parse where_clause to separate WHERE conditions from LIMIT/OFFSET
        where_conditions, limit_offset = parse_where_clause(where_clause)
        
        if where_conditions:
            query += f" WHERE {where_conditions}"
        
        # If limit parameter is provided, it takes precedence over any LIMIT in where_clause
        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"
        
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
                seq = self.get_host_sequence(host_id)
                host_seqs[host_id] = seq
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
                seq_str = self.get_host_sequence(host_id)
                sequences.append({
                    'Host_ID': host_id,
                    'Sequence': seq_str,
                    'Length': len(seq_str),
                    'GC_Content': round(gc_fraction(seq_str) * 100, 2) if len(seq_str) > 0 else 0.0
                })
            except KeyError:
                missing_ids.append(host_id)
                logging.warning(f"⚠️  Host ID '{host_id}' not found in FASTA")
        
        if missing_ids:
            logging.warning(f"⚠️  {len(missing_ids):,} host IDs not found in FASTA file")
        
        df = pd.DataFrame(sequences)
        logging.info(f"✅ Retrieved {len(df):,} sequences")
        
        return df
    
    def get_phage_metadata(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get phage metadata from the database
        
        Args:
            where_clause: Optional SQL WHERE clause to filter phages (without WHERE keyword)
            limit: Optional limit on number of phages
        
        Returns:
            DataFrame with phage metadata including: Phage_ID, Source_DB, Length, GC_content,
            Taxonomy, Completeness, Host, Lifestyle, Cluster, Subcluster
        
        Example:
            # Get all phages metadata
            metadata = retriever.get_phage_metadata()
            
            # Get phages from specific source
            metadata = retriever.get_phage_metadata("Source_DB = 'PhagesDB'", limit=1000)
            
            # Get lytic phages
            metadata = retriever.get_phage_metadata("Lifestyle = 'Lytic'")
        """
        query = """
        SELECT 
            Phage_ID,
            Source_DB,
            Length,
            GC_content,
            Taxonomy,
            Completeness,
            Host,
            Lifestyle,
            Cluster,
            Subcluster
        FROM fact_phages
        """
        
        # Parse where_clause to separate WHERE conditions from LIMIT/OFFSET
        where_conditions, limit_offset = parse_where_clause(where_clause)
        
        if where_conditions:
            query += f" WHERE {where_conditions}"
        
        # If limit parameter is provided, it takes precedence over any LIMIT in where_clause
        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"
        
        logging.info(f"🔍 Querying phage metadata...")
        result = self.conn.execute(query).fetchdf()
        
        logging.info(f"✅ Retrieved metadata for {len(result):,} phages")
        
        return result
    
    def get_host_metadata(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get host metadata from the database
        
        Args:
            where_clause: Optional SQL WHERE clause to filter hosts (without WHERE keyword)
            limit: Optional limit on number of hosts
        
        Returns:
            DataFrame with host metadata including: Host_ID, Species_Name, Strain_Name,
            Assembly_Accession, Assembly_Name, Assembly_Level, Genome_Length, GC_Content,
            RefSeq_Category, Download_Date, Source
        
        Example:
            # Get all hosts metadata
            metadata = retriever.get_host_metadata()
            
            # Get hosts of specific species
            metadata = retriever.get_host_metadata("Species_Name LIKE '%Escherichia%'")
            
            # Get complete genomes only
            metadata = retriever.get_host_metadata("Assembly_Level = 'Complete Genome'")
        """
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")
        
        query = """
        SELECT 
            Host_ID,
            Species_Name,
            Strain_Name,
            Assembly_Accession,
            Assembly_Name,
            Assembly_Level,
            Genome_Length,
            GC_Content,
            RefSeq_Category,
            Download_Date,
            Source
        FROM dim_hosts
        """
        
        # Parse where_clause to separate WHERE conditions from LIMIT/OFFSET
        where_conditions, limit_offset = parse_where_clause(where_clause)
        
        if where_conditions:
            query += f" WHERE {where_conditions}"
        
        # If limit parameter is provided, it takes precedence over any LIMIT in where_clause
        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"
        
        logging.info(f"🔍 Querying host metadata...")
        result = self.conn.execute(query).fetchdf()
        
        logging.info(f"✅ Retrieved metadata for {len(result):,} hosts")
        
        return result
    
    def get_phage_host_metadata(self, where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Get combined phage-host metadata for interaction pairs
        
        Args:
            where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
            limit: Optional limit on number of pairs
        
        Returns:
            DataFrame with combined phage and host metadata
        
        Example:
            # Get all pairs metadata
            metadata = retriever.get_phage_host_metadata()
            
            # Get pairs from specific phage source
            metadata = retriever.get_phage_host_metadata("p.Source_DB = 'PhagesDB'")
            
            # Get pairs with lytic phages only
            metadata = retriever.get_phage_host_metadata("p.Lifestyle = 'Lytic'", limit=1000)
        """
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")
        
        query = """
        SELECT DISTINCT
            pha.Phage_ID,
            pha.Host_ID,
            p.Source_DB as Phage_Source,
            p.Length as Phage_Length,
            p.GC_content as Phage_GC,
            p.Taxonomy as Phage_Taxonomy,
            p.Completeness as Phage_Completeness,
            p.Lifestyle as Phage_Lifestyle,
            p.Cluster as Phage_Cluster,
            p.Subcluster as Phage_Subcluster,
            h.Species_Name as Host_Species,
            h.Strain_Name as Host_Strain,
            h.Assembly_Accession as Host_Assembly,
            h.Assembly_Level as Host_Assembly_Level,
            h.Genome_Length as Host_Length,
            h.GC_Content as Host_GC,
            h.RefSeq_Category as Host_RefSeq_Category,
            h.Source as Host_Source
        FROM phage_host_associations pha
        JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        """
        
        # Parse where_clause to separate WHERE conditions from LIMIT/OFFSET
        where_conditions, limit_offset = parse_where_clause(where_clause)
        
        if where_conditions:
            query += f" WHERE {where_conditions}"
        
        # If limit parameter is provided, it takes precedence over any LIMIT in where_clause
        if limit:
            query += f" LIMIT {limit}"
        elif limit_offset:
            query += f" {limit_offset}"
        
        logging.info(f"🔍 Querying phage-host metadata...")
        result = self.conn.execute(query).fetchdf()
        
        logging.info(f"✅ Retrieved metadata for {len(result):,} phage-host pairs")
        
        return result
    
    def help(self):
        """Print help information"""
        help_text = """
        SequenceRetriever Help:
        
        Methods:
            - get_phage_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_protein_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_host_sequences(query: str, limit: Optional[int] = None) -> pd.DataFrame
            - get_phage_host_pairs(where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame
            - get_sequences_by_ids(phage_ids: Optional[List[str]] = None, protein_ids: Optional[List[str]] = None) -> Dict
            - get_protein_sequences_by_phage(phage_id: str) -> pd.DataFrame
            - get_phage_metadata(where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame
            - get_host_metadata(where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame
            - get_phage_host_metadata(where_clause: str = None, limit: Optional[int] = None) -> pd.DataFrame
            - export_fasta(df: pd.DataFrame, output_path: str, id_col: str = 'Phage_ID')
            - get_stats() -> Dict
            - close()
        
        Usage Examples:
            # Sequences
            retriever = SequenceRetriever(db_path, phage_fasta_path, protein_fasta_path)
            phage_df = retriever.get_phage_sequences("SELECT Phage_ID FROM fact_phages WHERE Length > 50000", limit=100)
            protein_df = retriever.get_protein_sequences("SELECT Protein_ID FROM dim_proteins WHERE Molecular_weight > 50000", limit=100)
            
            # Metadata
            phage_meta = retriever.get_phage_metadata("Source_DB = 'PhagesDB'", limit=100)
            host_meta = retriever.get_host_metadata("Species_Name LIKE '%Escherichia%'")
            pairs_meta = retriever.get_phage_host_metadata("p.Lifestyle = 'Lytic'")
            
            # Phage-host pairs with sequences and metadata
            pairs = retriever.get_phage_host_pairs("p.Source_DB = 'PhagesDB'", limit=100)
            
            # Export
            retriever.export_fasta(phage_df, "output_phages.fasta", id_col='Phage_ID')
            stats = retriever.get_stats()
            retriever.close()
        """
        print(help_text)
    
    def create_streaming_dataset(
        self,
        where_clause: Optional[str] = None,
        batch_size: int = 1000,
        transform: Optional[object] = None,
        missing_hosts_csv: Optional[str] = None
    ):
        """
        Create a PhageHostStreamingDataset for memory-efficient iteration.
        
        This factory method creates a streaming dataset that fetches data in batches
        from DuckDB and loads sequences on-demand. Ideal for large datasets.
        
        Args:
            where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
            batch_size: Number of records to fetch per database query (default: 1000)
            transform: Optional transform function to apply to each sample
            missing_hosts_csv: Optional path to save CSV of phages with missing hosts
                              (e.g., "/data/intermediate/missing_hosts.csv")
            
        Returns:
            PhageHostStreamingDataset instance
            
        Example:
            >>> dataset = retriever.create_streaming_dataset(
            ...     where_clause="Confidence > 0.8",
            ...     batch_size=1000,
            ...     missing_hosts_csv="/data/intermediate/missing_hosts.csv"
            ... )
            >>> from torch.utils.data import DataLoader
            >>> dataloader = DataLoader(dataset, batch_size=32)
            >>> for batch in dataloader:
            ...     # Process batch
            ...     pass
        """
        from .streaming_dataset import PhageHostStreamingDataset
        
        # Get database path from connection
        # PRAGMA database_list returns (seq, name, file) - index 2 is the file path
        db_path = str(self.conn.execute("PRAGMA database_list").fetchone()[2])
        
        return PhageHostStreamingDataset(
            db_path=db_path,
            phage_fasta_path=self._phage_fasta_path,
            host_fasta_path=self._host_fasta_path,
            host_mapping_path=self._host_mapping_path,
            where_clause=where_clause,
            batch_size=batch_size,
            transform=transform,
            missing_hosts_csv=missing_hosts_csv
        )
    
    def create_indexed_dataset(
        self,
        where_clause: Optional[str] = None,
        transform: Optional[object] = None,
        missing_hosts_csv: Optional[str] = None
    ):
        """
        Create a PhageHostIndexedDataset for random access with caching.
        
        This factory method creates an indexed dataset that caches metadata in memory
        and provides random access. Suitable for medium-sized datasets.
        
        Args:
            where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
            transform: Optional transform function to apply to each sample
            missing_hosts_csv: Optional path to save CSV of phages with missing hosts
                              (e.g., "/data/intermediate/missing_hosts.csv")
            
        Returns:
            PhageHostIndexedDataset instance
            
        Example:
            >>> dataset = retriever.create_indexed_dataset(
            ...     where_clause="Confidence > 0.8",
            ...     missing_hosts_csv="/data/intermediate/missing_hosts.csv"
            ... )
            >>> from torch.utils.data import DataLoader
            >>> # Supports shuffling and multi-worker loading
            >>> dataloader = DataLoader(dataset, batch_size=32, shuffle=True, num_workers=4)
            >>> for batch in dataloader:
            ...     # Process batch
            ...     pass
        """
        from .streaming_dataset import PhageHostIndexedDataset
        
        # Get database path from connection
        # PRAGMA database_list returns (seq, name, file) - index 2 is the file path
        db_path = str(self.conn.execute("PRAGMA database_list").fetchone()[2])
        
        return PhageHostIndexedDataset(
            db_path=db_path,
            phage_fasta_path=self._phage_fasta_path,
            host_fasta_path=self._host_fasta_path,
            host_mapping_path=self._host_mapping_path,
            where_clause=where_clause,
            transform=transform,
            missing_hosts_csv=missing_hosts_csv
        )
    
    def get_phage_host_pairs_iterator(
        self,
        where_clause: Optional[str] = None,
        batch_size: int = 1000
    ):
        """
        Get an iterator that yields batches of phage-host pairs as DataFrames.
        
        This provides a simple memory-efficient way to process large datasets
        in batches without loading everything into memory at once.
        Alternative for non-PyTorch workflows.
        
        Args:
            where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
            batch_size: Number of pairs to fetch per batch (default: 1000)
            
        Yields:
            DataFrame batches containing phage-host pairs with sequences and metadata
            
        Example:
            >>> for batch_df in retriever.get_phage_host_pairs_iterator(
            ...     where_clause="Confidence > 0.8",
            ...     batch_size=1000
            ... ):
            ...     # Process batch DataFrame
            ...     print(f"Processing {len(batch_df)} pairs")
            ...     # Do feature extraction, analysis, etc.
        """
        if not self._has_host_data:
            raise ValueError("Host data not available - run host genome download workflow first")
        
        # Ensure FASTA files are loaded
        _ = self.phage_fasta
        if not self._use_host_mapping:
            _ = self.host_fasta
        
        # Build query
        query = """
        SELECT DISTINCT
            pha.Phage_ID,
            pha.Host_ID,
            p.Source_DB as Phage_Source,
            p.Length as Phage_Length,
            p.GC_content as Phage_GC,
            p.Taxonomy as Phage_Taxonomy,
            p.Completeness as Phage_Completeness,
            p.Lifestyle as Phage_Lifestyle,
            p.Cluster as Phage_Cluster,
            p.Subcluster as Phage_Subcluster,
            h.Species_Name,
            h.Assembly_Level as Host_Assembly_Level,
            h.Genome_Length as Host_Length,
            h.GC_Content as Host_GC,
            h.RefSeq_Category as Host_RefSeq_Category
        FROM phage_host_associations pha
        JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
        JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
        """
        
        # Parse where_clause to separate WHERE conditions from LIMIT/OFFSET
        where_conditions, limit_offset = parse_where_clause(where_clause)
        
        if where_conditions:
            query += f" WHERE {where_conditions}"
        
        if limit_offset:
            query += f" {limit_offset}"
        
        logging.info(f"🔍 Starting batch iteration with batch_size={batch_size}")
        
        # Execute query and fetch in batches
        cursor = self.conn.execute(query)
        batch_num = 0
        
        while True:
            # Fetch a batch
            batch_df = cursor.fetch_df_chunk(batch_size)
            if batch_df is None or len(batch_df) == 0:
                break
            
            batch_num += 1
            logging.info(f"📦 Processing batch {batch_num} ({len(batch_df)} pairs)")
            
            # Fetch sequences for this batch
            phage_seqs = {}
            host_seqs = {}
            
            for phage_id in batch_df['Phage_ID'].unique():
                phage_seqs[phage_id] = self._get_sequence_safe(phage_id, 'phage')
            
            for host_id in batch_df['Host_ID'].unique():
                host_seqs[host_id] = self._get_sequence_safe(host_id, 'host')
            
            # Add sequences to batch
            batch_df['Phage_Sequence'] = batch_df['Phage_ID'].map(phage_seqs)
            batch_df['Host_Sequence'] = batch_df['Host_ID'].map(host_seqs)
            
            # Filter out rows with missing sequences
            before_count = len(batch_df)
            batch_df = batch_df.dropna(subset=['Phage_Sequence', 'Host_Sequence'])
            after_count = len(batch_df)
            
            if before_count > after_count:
                logging.warning(f"⚠️  Removed {before_count - after_count} pairs with missing sequences from batch")
            
            if len(batch_df) > 0:
                yield batch_df
        
        logging.info(f"✅ Completed iteration over {batch_num} batches")
    
    def _get_sequence_safe(self, seq_id: str, seq_type: str) -> str:
        """
        Helper method for safe sequence retrieval with error handling.
        
        Args:
            seq_id: Sequence identifier (Phage_ID or Host_ID)
            seq_type: Type of sequence ('phage' or 'host')
            
        Returns:
            Sequence as string, or empty string if not found
        """
        try:
            if seq_type == 'phage':
                return str(self.phage_fasta[seq_id][:].seq)
            elif seq_type == 'host':
                return self.get_host_sequence(seq_id)
            else:
                raise ValueError(f"Invalid seq_type: {seq_type}")
        except KeyError:
            logging.warning(f"⚠️  {seq_type.capitalize()} sequence not found for ID: {seq_id}")
            return ""
        except Exception as e:
            logging.warning(f"⚠️  Error retrieving {seq_type} sequence for {seq_id}: {e}")
            return ""
    
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
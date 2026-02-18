"""
PyTorch-compatible streaming datasets for large-scale ML workflows.

This module provides memory-efficient dataset classes for loading phage-host interaction
data from DuckDB databases in a streaming fashion, compatible with PyTorch DataLoader.

Classes:
    - PhageHostStreamingDataset: Streaming dataset using IterableDataset
    - PhageHostIndexedDataset: Random-access dataset using Dataset
"""

import duckdb
import logging
from typing import Optional, Callable, Dict, Any, List
from pathlib import Path
import json
from collections import OrderedDict
import csv
import os

try:
    from torch.utils.data import IterableDataset, Dataset
    TORCH_AVAILABLE = True
except ImportError:
    # Fallback for environments without PyTorch
    TORCH_AVAILABLE = False
    # Create dummy base classes
    class IterableDataset:
        pass
    class Dataset:
        pass

from pyfaidx import Fasta


logger = logging.getLogger(__name__)


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


def phage_host_collate_fn(batch):
    """
    Custom collate function for phage-host datasets.
    
    PyTorch's default collate function cannot handle dictionaries with mixed types
    (strings, numbers, None values). This function keeps the batch as a list of
    dictionaries instead of trying to stack values into tensors.
    
    Args:
        batch: List of sample dictionaries from the dataset
        
    Returns:
        Dictionary where each key maps to a list of values from all samples
        
    Example:
        Input: [{'Phage_ID': 'p1', 'Length': 100}, {'Phage_ID': 'p2', 'Length': 200}]
        Output: {'Phage_ID': ['p1', 'p2'], 'Length': [100, 200]}
    """
    if not batch:
        return {}
    
    # Get all keys from the first sample
    keys = batch[0].keys()
    
    # Create a dictionary with lists for each key
    # Use .get() to handle missing keys gracefully (defaults to None)
    collated = {key: [sample.get(key, None) for sample in batch] for key in keys}
    
    return collated

# FASTA file configuration constants
# The null character split is used to handle FASTA headers with spaces
FASTA_SPLIT_CHAR = '\x00'
FASTA_DUPLICATE_ACTION = 'first'  # Use first occurrence when duplicates exist

# Maximum number of host FASTA files to keep open simultaneously
# This prevents "too many open files" errors when using host mapping mode
MAX_HOST_FASTA_CACHE_SIZE = 100


def load_fasta_file(fasta_path: str) -> Fasta:
    """
    Load a FASTA file with standard configuration.
    
    This helper function automatically creates .fai index files if they don't exist.
    
    Args:
        fasta_path: Path to FASTA file (string or Path object)
        
    Returns:
        Loaded Fasta object
    """
    # Check if index file exists, if not allow pyfaidx to create it
    fasta_path_obj = Path(fasta_path)
    # .fai index is appended to the full filename (e.g., file.fasta -> file.fasta.fai)
    index_path = Path(str(fasta_path_obj) + '.fai')
    rebuild = not index_path.exists()
    
    if rebuild:
        logger.info(f"Creating index for {fasta_path}")
    
    return Fasta(
        fasta_path,
        rebuild=rebuild,
        split_char=FASTA_SPLIT_CHAR,
        read_long_names=True,
        duplicate_action=FASTA_DUPLICATE_ACTION
    )


class PhageHostStreamingDataset(IterableDataset):
    """
    Streaming dataset for phage-host interactions that fetches data in batches from DuckDB.
    
    This dataset is memory-efficient and suitable for large datasets. It streams data
    from the database in batches and fetches sequences on-demand from FASTA files.
    
    Compatible with PyTorch DataLoader for ML training workflows.
    
    Args:
        db_path: Path to DuckDB database
        phage_fasta_path: Path to indexed phage FASTA file
        host_fasta_path: Path to indexed host FASTA file (legacy single-file mode)
        host_mapping_path: Path to JSON mapping file for individual host FASTA files
        where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
        batch_size: Number of records to fetch per database query (default: 1000)
        transform: Optional transform function to apply to each sample
        
    Example:
        >>> dataset = PhageHostStreamingDataset(
        ...     db_path="database.duckdb",
        ...     phage_fasta_path="phages.fasta",
        ...     host_mapping_path="host_mapping.json",
        ...     where_clause="Confidence > 0.8",
        ...     batch_size=1000
        ... )
        >>> from torch.utils.data import DataLoader
        >>> dataloader = DataLoader(dataset, batch_size=32)
        >>> for batch in dataloader:
        ...     # Train model with batch
        ...     pass
    """
    
    def __init__(
        self,
        db_path: str,
        phage_fasta_path: str,
        host_fasta_path: Optional[str] = None,
        host_mapping_path: Optional[str] = None,
        where_clause: Optional[str] = None,
        batch_size: int = 1000,
        transform: Optional[Callable] = None,
        missing_hosts_csv: Optional[str] = None,
    ):
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available. Dataset will work but cannot be used with DataLoader.")
        
        # Validate paths
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        if not Path(phage_fasta_path).exists():
            raise FileNotFoundError(f"Phage FASTA not found: {phage_fasta_path}")
        
        self.db_path = db_path
        self.phage_fasta_path = phage_fasta_path
        self.host_fasta_path = host_fasta_path
        self.host_mapping_path = host_mapping_path
        self.where_clause = where_clause
        self.batch_size = batch_size
        self.transform = transform
        self.missing_hosts_csv = missing_hosts_csv
        
        # Determine host mode
        self.use_host_mapping = False
        self.host_mapping = None
        
        if host_mapping_path and Path(host_mapping_path).exists():
            self.use_host_mapping = True
            with open(host_mapping_path, 'r') as f:
                self.host_mapping = json.load(f)
            logger.info(f"Using host mapping with {len(self.host_mapping)} hosts")
        elif host_fasta_path and Path(host_fasta_path).exists():
            logger.info("Using legacy single-file host FASTA mode")
        else:
            raise ValueError("Either host_fasta_path or host_mapping_path must be provided and exist")
        
        # Connection will be initialized per worker in __iter__
        self.conn = None
        self.phage_fasta = None
        self.host_fasta = None
        # Use OrderedDict for LRU cache behavior
        self.host_fasta_cache = OrderedDict()
        
        # Track missing hosts for CSV export
        self.missing_hosts_data: List[Dict[str, Any]] = []
        
        # Track if cleanup has already occurred
        self._closed = False
    
    def _load_fasta_file(self, fasta_path: str) -> Fasta:
        """
        Load a FASTA file with standard configuration.
        
        Args:
            fasta_path: Path to FASTA file
            
        Returns:
            Loaded Fasta object
        """
        return load_fasta_file(fasta_path)
    
    def _init_worker(self):
        """Initialize database connection and FASTA files for the current worker."""
        # Create a new connection for this worker
        self.conn = duckdb.connect(self.db_path, read_only=True)
        
        # Load phage FASTA
        self.phage_fasta = self._load_fasta_file(self.phage_fasta_path)
        
        # Load host FASTA (legacy mode only)
        if not self.use_host_mapping and self.host_fasta_path:
            self.host_fasta = self._load_fasta_file(self.host_fasta_path)
        
        # Reset cache for host mapping mode (use OrderedDict for LRU)
        self.host_fasta_cache = OrderedDict()
    
    def _track_missing_host(self, host_id: str, sample_metadata: Dict[str, Any], failure_reason: str):
        """
        Track a missing host for later CSV export.
        
        Args:
            host_id: Host identifier that failed
            sample_metadata: Metadata about the phage-host pair
            failure_reason: Description of why the host retrieval failed
        """
        self.missing_hosts_data.append({
            'Phage_ID': sample_metadata.get('Phage_ID', ''),
            'Host_ID': host_id,
            'Species_Name': sample_metadata.get('Species_Name', ''),
            'Phage_Source': sample_metadata.get('Phage_Source', ''),
            'Phage_Length': sample_metadata.get('Phage_Length', ''),
            'Phage_Taxonomy': sample_metadata.get('Phage_Taxonomy', ''),
            'Host_Assembly_Level': sample_metadata.get('Host_Assembly_Level', ''),
            'Failure_Reason': failure_reason,
        })
    
    def _save_missing_hosts_csv(self):
        """Save missing hosts data to CSV file if configured."""
        if not self.missing_hosts_csv or not self.missing_hosts_data:
            return
        
        try:
            # Create directory if needed
            csv_path = Path(self.missing_hosts_csv)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write CSV
            with open(csv_path, 'w', newline='') as f:
                if self.missing_hosts_data:
                    writer = csv.DictWriter(f, fieldnames=self.missing_hosts_data[0].keys())
                    writer.writeheader()
                    writer.writerows(self.missing_hosts_data)
            
            logger.info(f"💾 Saved {len(self.missing_hosts_data)} missing host records to {csv_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save missing hosts CSV: {e}")
    
    def _get_host_sequence_safe(self, host_id: str, sample_metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Safely get host sequence with error handling.
        
        Args:
            host_id: Host identifier
            sample_metadata: Optional metadata about the sample for tracking missing hosts
            
        Returns:
            Host sequence as string, or empty string if not found
        """
        failure_reason = None
        try:
            if self.use_host_mapping:
                # Load individual host file on-demand with LRU cache
                if host_id in self.host_fasta_cache:
                    # Move to end (most recently used)
                    self.host_fasta_cache.move_to_end(host_id)
                else:
                    if host_id not in self.host_mapping:
                        failure_reason = "Host genome not in mapping (not downloaded/available for this host)"
                        logger.warning(f"⚠️  {failure_reason}: {host_id}")
                        if sample_metadata:
                            self._track_missing_host(host_id, sample_metadata, failure_reason)
                        return ""
                    
                    fasta_path = self.host_mapping[host_id]
                    if not Path(fasta_path).exists():
                        failure_reason = f"Host FASTA file not found on filesystem: {fasta_path}"
                        logger.warning(f"⚠️  {failure_reason}")
                        if sample_metadata:
                            self._track_missing_host(host_id, sample_metadata, failure_reason)
                        return ""
                    
                    # Check cache size and evict oldest if needed
                    if len(self.host_fasta_cache) >= MAX_HOST_FASTA_CACHE_SIZE:
                        # Remove oldest (first) item
                        oldest_id, oldest_fasta = self.host_fasta_cache.popitem(last=False)
                        if hasattr(oldest_fasta, 'close'):
                            try:
                                oldest_fasta.close()
                            except Exception:
                                pass
                    
                    # Load FASTA file using helper method (will create .fai if missing)
                    try:
                        self.host_fasta_cache[host_id] = self._load_fasta_file(fasta_path)
                    except Exception as e:
                        failure_reason = f"Error loading/indexing FASTA file: {type(e).__name__}: {e}"
                        logger.warning(f"⚠️  {failure_reason} for {host_id}")
                        logger.warning(f"   File path: {fasta_path}")
                        logger.warning(f"   This may indicate a corrupt file or missing/corrupt .fai index")
                        if sample_metadata:
                            self._track_missing_host(host_id, sample_metadata, failure_reason)
                        return ""
                
                fasta_obj = self.host_fasta_cache[host_id]
                keys = list(fasta_obj.keys())
                if not keys:
                    failure_reason = "FASTA file is empty (no sequences found)"
                    logger.warning(f"⚠️  {failure_reason} for {host_id}")
                    if sample_metadata:
                        self._track_missing_host(host_id, sample_metadata, failure_reason)
                    return ""
                return str(fasta_obj[keys[0]][:].seq)
            else:
                # Legacy single-file mode
                return str(self.host_fasta[host_id][:].seq)
        except KeyError:
            failure_reason = "Host sequence ID not found in FASTA file (KeyError)"
            logger.warning(f"⚠️  {failure_reason}: {host_id}")
            if sample_metadata:
                self._track_missing_host(host_id, sample_metadata, failure_reason)
            return ""
        except Exception as e:
            failure_reason = f"Unexpected error retrieving sequence: {type(e).__name__}: {e}"
            logger.warning(f"⚠️  {failure_reason} for {host_id}")
            if sample_metadata:
                self._track_missing_host(host_id, sample_metadata, failure_reason)
            return ""
    
    def _get_phage_sequence_safe(self, phage_id: str) -> str:
        """
        Safely get phage sequence with error handling.
        
        Args:
            phage_id: Phage identifier
            
        Returns:
            Phage sequence as string, or empty string if not found
        """
        try:
            return str(self.phage_fasta[phage_id][:].seq)
        except KeyError:
            logger.warning(f"⚠️  Phage sequence not found for ID: {phage_id}")
            return ""
        except Exception as e:
            logger.warning(f"⚠️  Error retrieving phage sequence for {phage_id}: {e}")
            return ""
    
    def __iter__(self):
        """Iterate over the dataset in streaming fashion."""
        # Initialize connection and FASTA files for this worker
        self._init_worker()
        
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
        where_conditions, limit_offset = parse_where_clause(self.where_clause)
        
        if where_conditions:
            query += f" WHERE {where_conditions}"
        
        if limit_offset:
            query += f" {limit_offset}"
        
        # Execute query and fetch in batches
        cursor = self.conn.execute(query)
        
        # Track if we yield any samples
        sample_count = 0
        
        while True:
            # Fetch a batch
            batch = cursor.fetchmany(self.batch_size)
            if not batch:
                break
            
            # Process each row in the batch
            for row in batch:
                # Convert row to dict
                sample = {
                    'Phage_ID': row[0],
                    'Host_ID': row[1],
                    'Phage_Source': row[2],
                    'Phage_Length': row[3],
                    'Phage_GC': row[4],
                    'Phage_Taxonomy': row[5],
                    'Phage_Completeness': row[6],
                    'Phage_Lifestyle': row[7],
                    'Phage_Cluster': row[8],
                    'Phage_Subcluster': row[9],
                    'Species_Name': row[10],
                    'Host_Assembly_Level': row[11],
                    'Host_Length': row[12],
                    'Host_GC': row[13],
                    'Host_RefSeq_Category': row[14],
                }
                
                # Fetch sequences
                sample['Phage_Sequence'] = self._get_phage_sequence_safe(sample['Phage_ID'])
                sample['Host_Sequence'] = self._get_host_sequence_safe(sample['Host_ID'], sample_metadata=sample)
                
                # Skip samples with missing sequences
                if not sample['Phage_Sequence'] or not sample['Host_Sequence']:
                    continue
                
                # Apply transform if provided
                if self.transform:
                    sample = self.transform(sample)
                
                sample_count += 1
                yield sample
        
        # Warn if no samples were yielded - diagnose the issue
        if sample_count == 0:
            logger.warning("⚠️  Streaming dataset yielded 0 samples")
            if self.where_clause:
                logger.warning(f"   WHERE clause: {self.where_clause}")
            
            # Diagnose the issue
            logger.warning("   Diagnosing issue...")
            
            # Check if there are ANY phage-host associations
            total_assoc = self.conn.execute("""
                SELECT COUNT(*) as count 
                FROM phage_host_associations
            """).fetchdf()['count'].iloc[0]
            
            logger.warning(f"   Total phage-host associations in database: {total_assoc}")
            
            if total_assoc == 0:
                logger.warning("   ❌ Database has no phage-host associations!")
            elif self.where_clause:
                # Check how many rows the query returns (before sequence filtering)
                test_query = """
                SELECT COUNT(*) as count
                FROM phage_host_associations pha
                JOIN fact_phages p ON pha.Phage_ID = p.Phage_ID
                JOIN dim_hosts h ON pha.Host_ID = h.Host_ID
                """
                test_query += f" WHERE {self.where_clause}"
                
                rows_before_seq_filter = self.conn.execute(test_query).fetchdf()['count'].iloc[0]
                logger.warning(f"   Rows matching WHERE clause: {rows_before_seq_filter}")
                
                if rows_before_seq_filter == 0:
                    # WHERE clause is the problem
                    logger.warning("   ❌ WHERE clause filters out all data!")
                    
                    # Check what values actually exist
                    if 'Completeness' in self.where_clause or 'completeness' in self.where_clause.lower():
                        completeness_values = self.conn.execute("""
                            SELECT DISTINCT Completeness, COUNT(*) as count
                            FROM fact_phages
                            WHERE Completeness IS NOT NULL
                            GROUP BY Completeness
                            ORDER BY count DESC
                        """).fetchdf()
                        logger.warning(f"   Available Completeness values:")
                        for _, row in completeness_values.iterrows():
                            logger.warning(f"     - '{row['Completeness']}': {row['count']} phages")
                    
                    if 'Assembly_Level' in self.where_clause or 'assembly_level' in self.where_clause.lower():
                        assembly_values = self.conn.execute("""
                            SELECT DISTINCT Assembly_Level, COUNT(*) as count
                            FROM dim_hosts
                            WHERE Assembly_Level IS NOT NULL
                            GROUP BY Assembly_Level
                            ORDER BY count DESC
                        """).fetchdf()
                        logger.warning(f"   Available Assembly_Level values:")
                        for _, row in assembly_values.iterrows():
                            logger.warning(f"     - '{row['Assembly_Level']}': {row['count']} hosts")
                else:
                    # Sequence files are the problem
                    logger.warning(f"   ⚠️  {rows_before_seq_filter} rows matched WHERE clause but all were filtered due to missing sequences")
                    logger.warning("   Check that FASTA files contain the required phage/host sequences")
        
        # Save missing hosts CSV before cleanup
        self._save_missing_hosts_csv()
        
        # Clean up resources
        self._cleanup()
    
    def _cleanup(self):
        """Clean up resources (close database connection and FASTA files)."""
        # Close database connection
        if self.conn:
            self.conn.close()
            self.conn = None
        
        # Close cached host FASTA files
        if self.host_fasta_cache:
            for fasta_obj in self.host_fasta_cache.values():
                if hasattr(fasta_obj, 'close'):
                    try:
                        fasta_obj.close()
                    except Exception:
                        pass
            self.host_fasta_cache.clear()
        
        # Note: phage_fasta and host_fasta will be closed when Fasta objects are garbage collected
        # or we can explicitly close them if they support it
        if self.phage_fasta and hasattr(self.phage_fasta, 'close'):
            try:
                self.phage_fasta.close()
            except Exception:
                pass
        
        if self.host_fasta and hasattr(self.host_fasta, 'close'):
            try:
                self.host_fasta.close()
            except Exception:
                pass
    
    def close(self):
        """Close all open file handles and database connections to prevent resource leaks."""
        if self._closed:
            return  # Already closed, prevent duplicate operations
        
        self._closed = True
        self._save_missing_hosts_csv()
        self._cleanup()
    
    def __enter__(self):
        """Enter context manager - returns self for use in with statement."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - ensures cleanup is called."""
        self.close()
        return False  # Don't suppress exceptions
    
    def __del__(self):
        """Destructor to ensure cleanup when object is deleted."""
        try:
            self.close()
        except Exception:
            # Ignore errors during cleanup in destructor
            pass


class PhageHostIndexedDataset(Dataset):
    """
    Indexed dataset for phage-host interactions with random access support.
    
    This dataset caches metadata in memory and fetches sequences on-demand,
    making it suitable for medium-sized datasets that fit in memory.
    Supports shuffling and multi-worker data loading.
    
    Compatible with PyTorch DataLoader for ML training workflows.
    
    Args:
        db_path: Path to DuckDB database
        phage_fasta_path: Path to indexed phage FASTA file
        host_fasta_path: Path to indexed host FASTA file (legacy single-file mode)
        host_mapping_path: Path to JSON mapping file for individual host FASTA files
        where_clause: Optional SQL WHERE clause to filter pairs (without WHERE keyword)
        transform: Optional transform function to apply to each sample
        
    Example:
        >>> dataset = PhageHostIndexedDataset(
        ...     db_path="database.duckdb",
        ...     phage_fasta_path="phages.fasta",
        ...     host_mapping_path="host_mapping.json",
        ...     where_clause="Confidence > 0.8"
        ... )
        >>> from torch.utils.data import DataLoader
        >>> # Supports shuffling and multi-worker loading
        >>> dataloader = DataLoader(dataset, batch_size=32, shuffle=True, num_workers=4)
        >>> for batch in dataloader:
        ...     # Train model with batch
        ...     pass
    """
    
    def __init__(
        self,
        db_path: str,
        phage_fasta_path: str,
        host_fasta_path: Optional[str] = None,
        host_mapping_path: Optional[str] = None,
        where_clause: Optional[str] = None,
        transform: Optional[Callable] = None,
        missing_hosts_csv: Optional[str] = None,
    ):
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available. Dataset will work but cannot be used with DataLoader.")
        
        # Validate paths
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")
        if not Path(phage_fasta_path).exists():
            raise FileNotFoundError(f"Phage FASTA not found: {phage_fasta_path}")
        
        self.db_path = db_path
        self.phage_fasta_path = phage_fasta_path
        self.host_fasta_path = host_fasta_path
        self.host_mapping_path = host_mapping_path
        self.transform = transform
        self.missing_hosts_csv = missing_hosts_csv
        
        # Determine host mode
        self.use_host_mapping = False
        self.host_mapping = None
        
        if host_mapping_path and Path(host_mapping_path).exists():
            self.use_host_mapping = True
            with open(host_mapping_path, 'r') as f:
                self.host_mapping = json.load(f)
            logger.info(f"Using host mapping with {len(self.host_mapping)} hosts")
        elif host_fasta_path and Path(host_fasta_path).exists():
            logger.info("Using legacy single-file host FASTA mode")
        else:
            raise ValueError("Either host_fasta_path or host_mapping_path must be provided and exist")
        
        # Load metadata into memory
        self._load_metadata(where_clause)
        
        # FASTA files will be loaded lazily
        self.phage_fasta = None
        self.host_fasta = None
        # Use OrderedDict for LRU cache behavior
        self.host_fasta_cache = OrderedDict()
        
        # Track missing hosts for CSV export
        self.missing_hosts_data: List[Dict[str, Any]] = []
        
        # Track if cleanup has already occurred
        self._closed = False
    
    def _load_metadata(self, where_clause: Optional[str] = None):
        """Load metadata from database into memory."""
        conn = duckdb.connect(self.db_path, read_only=True)
        
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
        
        result = conn.execute(query).fetchdf()
        
        # Store metadata
        self.metadata = result.to_dict('records')
        
        if len(self.metadata) == 0:
            logger.warning("⚠️  Dataset is empty (0 phage-host pairs loaded)")
            if where_clause:
                logger.warning(f"   WHERE clause: {where_clause}")
            
            # Diagnose the issue - check what data actually exists
            logger.warning("   Diagnosing issue...")
            
            # Check if there are ANY phage-host associations
            total_assoc = conn.execute("""
                SELECT COUNT(*) as count 
                FROM phage_host_associations
            """).fetchdf()['count'].iloc[0]
            
            logger.warning(f"   Total phage-host associations in database: {total_assoc}")
            
            if total_assoc == 0:
                logger.warning("   ❌ Database has no phage-host associations!")
                logger.warning("   The database may not be fully populated yet.")
            elif where_clause:
                # Check without the WHERE clause
                query_no_where = """
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
                total_without_filter = conn.execute(query_no_where).fetchdf()
                logger.warning(f"   Total pairs without WHERE clause: {len(total_without_filter)}")
                
                if len(total_without_filter) > 0:
                    # Check what Completeness values exist
                    if 'Completeness' in where_clause or 'completeness' in where_clause.lower():
                        completeness_values = conn.execute("""
                            SELECT DISTINCT Completeness, COUNT(*) as count
                            FROM fact_phages
                            WHERE Completeness IS NOT NULL
                            GROUP BY Completeness
                            ORDER BY count DESC
                        """).fetchdf()
                        logger.warning(f"   Available Completeness values in database:")
                        for _, row in completeness_values.iterrows():
                            logger.warning(f"     - '{row['Completeness']}': {row['count']} phages")
                    
                    # Check what Assembly_Level values exist
                    if 'Assembly_Level' in where_clause or 'assembly_level' in where_clause.lower():
                        assembly_values = conn.execute("""
                            SELECT DISTINCT Assembly_Level, COUNT(*) as count
                            FROM dim_hosts
                            WHERE Assembly_Level IS NOT NULL
                            GROUP BY Assembly_Level
                            ORDER BY count DESC
                        """).fetchdf()
                        logger.warning(f"   Available Assembly_Level values in database:")
                        for _, row in assembly_values.iterrows():
                            logger.warning(f"     - '{row['Assembly_Level']}': {row['count']} hosts")
                    
                    logger.warning("   ⚠️  WHERE clause filters out all data!")
                    logger.warning("   Suggestion: Adjust WHERE clause to match actual database values")
        else:
            logger.info(f"Loaded metadata for {len(self.metadata)} phage-host pairs")
        
        conn.close()
    
    def _load_fasta_file(self, fasta_path: str) -> Fasta:
        """
        Load a FASTA file with standard configuration.
        
        Args:
            fasta_path: Path to FASTA file
            
        Returns:
            Loaded Fasta object
        """
        return load_fasta_file(fasta_path)
    
    def _ensure_fasta_loaded(self):
        """Ensure FASTA files are loaded."""
        if self.phage_fasta is None:
            self.phage_fasta = self._load_fasta_file(self.phage_fasta_path)
        
        if not self.use_host_mapping and self.host_fasta is None and self.host_fasta_path:
            self.host_fasta = self._load_fasta_file(self.host_fasta_path)
    
    def _track_missing_host(self, host_id: str, sample_metadata: Dict[str, Any], failure_reason: str):
        """
        Track a missing host for later CSV export.
        
        Args:
            host_id: Host identifier that failed
            sample_metadata: Metadata about the phage-host pair
            failure_reason: Description of why the host retrieval failed
        """
        self.missing_hosts_data.append({
            'Phage_ID': sample_metadata.get('Phage_ID', ''),
            'Host_ID': host_id,
            'Species_Name': sample_metadata.get('Species_Name', ''),
            'Phage_Source': sample_metadata.get('Phage_Source', ''),
            'Phage_Length': sample_metadata.get('Phage_Length', ''),
            'Phage_Taxonomy': sample_metadata.get('Phage_Taxonomy', ''),
            'Host_Assembly_Level': sample_metadata.get('Host_Assembly_Level', ''),
            'Failure_Reason': failure_reason,
        })
    
    def _save_missing_hosts_csv(self):
        """Save missing hosts data to CSV file if configured."""
        if not self.missing_hosts_csv or not self.missing_hosts_data:
            return
        
        try:
            # Create directory if needed
            csv_path = Path(self.missing_hosts_csv)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write CSV
            with open(csv_path, 'w', newline='') as f:
                if self.missing_hosts_data:
                    writer = csv.DictWriter(f, fieldnames=self.missing_hosts_data[0].keys())
                    writer.writeheader()
                    writer.writerows(self.missing_hosts_data)
            
            logger.info(f"💾 Saved {len(self.missing_hosts_data)} missing host records to {csv_path}")
        except Exception as e:
            logger.error(f"❌ Failed to save missing hosts CSV: {e}")
    
    def _get_host_sequence_safe(self, host_id: str, sample_metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Safely get host sequence with error handling.
        
        Args:
            host_id: Host identifier
            sample_metadata: Optional metadata about the sample for tracking missing hosts
            
        Returns:
            Host sequence as string, or empty string if not found
        """
        failure_reason = None
        try:
            if self.use_host_mapping:
                # Load individual host file on-demand with LRU cache
                if host_id in self.host_fasta_cache:
                    # Move to end (most recently used)
                    self.host_fasta_cache.move_to_end(host_id)
                else:
                    if host_id not in self.host_mapping:
                        failure_reason = "Host genome not in mapping (not downloaded/available for this host)"
                        logger.warning(f"⚠️  {failure_reason}: {host_id}")
                        if sample_metadata:
                            self._track_missing_host(host_id, sample_metadata, failure_reason)
                        return ""
                    
                    fasta_path = self.host_mapping[host_id]
                    if not Path(fasta_path).exists():
                        failure_reason = f"Host FASTA file not found on filesystem: {fasta_path}"
                        logger.warning(f"⚠️  {failure_reason}")
                        if sample_metadata:
                            self._track_missing_host(host_id, sample_metadata, failure_reason)
                        return ""
                    
                    # Check cache size and evict oldest if needed
                    if len(self.host_fasta_cache) >= MAX_HOST_FASTA_CACHE_SIZE:
                        # Remove oldest (first) item
                        oldest_id, oldest_fasta = self.host_fasta_cache.popitem(last=False)
                        if hasattr(oldest_fasta, 'close'):
                            try:
                                oldest_fasta.close()
                            except Exception:
                                pass
                    
                    # Load FASTA file using helper method (will create .fai if missing)
                    try:
                        self.host_fasta_cache[host_id] = self._load_fasta_file(fasta_path)
                    except Exception as e:
                        failure_reason = f"Error loading/indexing FASTA file: {type(e).__name__}: {e}"
                        logger.warning(f"⚠️  {failure_reason} for {host_id}")
                        logger.warning(f"   File path: {fasta_path}")
                        logger.warning(f"   This may indicate a corrupt file or missing/corrupt .fai index")
                        if sample_metadata:
                            self._track_missing_host(host_id, sample_metadata, failure_reason)
                        return ""
                
                fasta_obj = self.host_fasta_cache[host_id]
                keys = list(fasta_obj.keys())
                if not keys:
                    failure_reason = "FASTA file is empty (no sequences found)"
                    logger.warning(f"⚠️  {failure_reason} for {host_id}")
                    if sample_metadata:
                        self._track_missing_host(host_id, sample_metadata, failure_reason)
                    return ""
                return str(fasta_obj[keys[0]][:].seq)
            else:
                # Legacy single-file mode
                return str(self.host_fasta[host_id][:].seq)
        except KeyError:
            failure_reason = "Host sequence ID not found in FASTA file (KeyError)"
            logger.warning(f"⚠️  {failure_reason}: {host_id}")
            if sample_metadata:
                self._track_missing_host(host_id, sample_metadata, failure_reason)
            return ""
        except Exception as e:
            failure_reason = f"Unexpected error retrieving sequence: {type(e).__name__}: {e}"
            logger.warning(f"⚠️  {failure_reason} for {host_id}")
            if sample_metadata:
                self._track_missing_host(host_id, sample_metadata, failure_reason)
            return ""
    
    def _get_phage_sequence_safe(self, phage_id: str) -> str:
        """
        Safely get phage sequence with error handling.
        
        Args:
            phage_id: Phage identifier
            
        Returns:
            Phage sequence as string, or empty string if not found
        """
        try:
            return str(self.phage_fasta[phage_id][:].seq)
        except KeyError:
            logger.warning(f"⚠️  Phage sequence not found for ID: {phage_id}")
            return ""
        except Exception as e:
            logger.warning(f"⚠️  Error retrieving phage sequence for {phage_id}: {e}")
            return ""
    
    def __len__(self):
        """Return the number of samples in the dataset."""
        return len(self.metadata)
    
    def __getitem__(self, idx):
        """
        Get a sample by index.
        
        Args:
            idx: Index of the sample
            
        Returns:
            Dictionary containing phage-host pair data with sequences
        """
        # Ensure FASTA files are loaded
        self._ensure_fasta_loaded()
        
        # Get metadata for this index
        meta = self.metadata[idx]
        
        # Create sample dict
        sample = dict(meta)
        
        # Fetch sequences
        sample['Phage_Sequence'] = self._get_phage_sequence_safe(meta['Phage_ID'])
        sample['Host_Sequence'] = self._get_host_sequence_safe(meta['Host_ID'], sample_metadata=meta)
        
        # Apply transform if provided
        if self.transform:
            sample = self.transform(sample)
        
        return sample
    
    def close(self):
        """Close all open FASTA file handles to prevent resource leaks."""
        if self._closed:
            return  # Already closed, prevent duplicate operations
        
        self._closed = True
        
        # Save missing hosts CSV before closing
        self._save_missing_hosts_csv()
        
        # Close cached host FASTA files
        if self.host_fasta_cache:
            for fasta_obj in self.host_fasta_cache.values():
                if hasattr(fasta_obj, 'close'):
                    try:
                        fasta_obj.close()
                    except Exception:
                        pass
            self.host_fasta_cache.clear()
        
        # Close phage FASTA
        if self.phage_fasta and hasattr(self.phage_fasta, 'close'):
            try:
                self.phage_fasta.close()
            except Exception:
                pass
            self.phage_fasta = None
        
        # Close host FASTA (legacy mode)
        if self.host_fasta and hasattr(self.host_fasta, 'close'):
            try:
                self.host_fasta.close()
            except Exception:
                pass
            self.host_fasta = None
    
    def __enter__(self):
        """Enter context manager - returns self for use in with statement."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - ensures cleanup is called."""
        self.close()
        return False  # Don't suppress exceptions
    
    def __del__(self):
        """Destructor to ensure cleanup when object is deleted."""
        self.close()

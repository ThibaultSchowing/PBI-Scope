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
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import json
from collections import OrderedDict

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

# FASTA file configuration constants
# The null character split is used to handle FASTA headers with spaces
FASTA_SPLIT_CHAR = '\x00'
FASTA_DUPLICATE_ACTION = 'first'  # Use first occurrence when duplicates exist

# Maximum number of host FASTA files to keep open simultaneously
# This prevents "too many open files" errors when using host mapping mode
MAX_HOST_FASTA_CACHE_SIZE = 100


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
    
    def _load_fasta_file(self, fasta_path: str) -> Fasta:
        """
        Load a FASTA file with standard configuration.
        
        Args:
            fasta_path: Path to FASTA file
            
        Returns:
            Loaded Fasta object
        """
        # Check if index file exists, if not allow pyfaidx to create it
        index_path = Path(str(fasta_path) + '.fai')
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
    
    def _get_host_sequence_safe(self, host_id: str) -> str:
        """
        Safely get host sequence with error handling.
        
        Args:
            host_id: Host identifier
            
        Returns:
            Host sequence as string, or empty string if not found
        """
        try:
            if self.use_host_mapping:
                # Load individual host file on-demand with LRU cache
                if host_id in self.host_fasta_cache:
                    # Move to end (most recently used)
                    self.host_fasta_cache.move_to_end(host_id)
                else:
                    if host_id not in self.host_mapping:
                        logger.warning(f"⚠️  Host ID '{host_id}' not found in mapping")
                        return ""
                    
                    fasta_path = self.host_mapping[host_id]
                    if not Path(fasta_path).exists():
                        logger.warning(f"⚠️  Host FASTA file not found: {fasta_path}")
                        return ""
                    
                    # Check if .fai index file exists
                    index_path = Path(str(fasta_path) + '.fai')
                    if not index_path.exists():
                        logger.warning(f"⚠️  Host FASTA index not found: {index_path}")
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
                    
                    # Load FASTA file using helper method
                    self.host_fasta_cache[host_id] = self._load_fasta_file(fasta_path)
                
                fasta_obj = self.host_fasta_cache[host_id]
                keys = list(fasta_obj.keys())
                if not keys:
                    logger.warning(f"⚠️  No sequences found in host file for {host_id}")
                    return ""
                return str(fasta_obj[keys[0]][:].seq)
            else:
                # Legacy single-file mode
                return str(self.host_fasta[host_id][:].seq)
        except KeyError:
            logger.warning(f"⚠️  Host sequence not found for ID: {host_id}")
            return ""
        except Exception as e:
            logger.warning(f"⚠️  Error retrieving host sequence for {host_id}: {e}")
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
        
        if self.where_clause:
            query += f" WHERE {self.where_clause}"
        
        # Execute query and fetch in batches
        cursor = self.conn.execute(query)
        
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
                sample['Host_Sequence'] = self._get_host_sequence_safe(sample['Host_ID'])
                
                # Skip samples with missing sequences
                if not sample['Phage_Sequence'] or not sample['Host_Sequence']:
                    continue
                
                # Apply transform if provided
                if self.transform:
                    sample = self.transform(sample)
                
                yield sample
        
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
        
        if where_clause:
            query += f" WHERE {where_clause}"
        
        result = conn.execute(query).fetchdf()
        conn.close()
        
        # Store metadata
        self.metadata = result.to_dict('records')
        logger.info(f"Loaded metadata for {len(self.metadata)} phage-host pairs")
    
    def _load_fasta_file(self, fasta_path: str) -> Fasta:
        """
        Load a FASTA file with standard configuration.
        
        Args:
            fasta_path: Path to FASTA file
            
        Returns:
            Loaded Fasta object
        """
        # Check if index file exists, if not allow pyfaidx to create it
        index_path = Path(str(fasta_path) + '.fai')
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
    
    def _ensure_fasta_loaded(self):
        """Ensure FASTA files are loaded."""
        if self.phage_fasta is None:
            self.phage_fasta = self._load_fasta_file(self.phage_fasta_path)
        
        if not self.use_host_mapping and self.host_fasta is None and self.host_fasta_path:
            self.host_fasta = self._load_fasta_file(self.host_fasta_path)
    
    def _get_host_sequence_safe(self, host_id: str) -> str:
        """
        Safely get host sequence with error handling.
        
        Args:
            host_id: Host identifier
            
        Returns:
            Host sequence as string, or empty string if not found
        """
        try:
            if self.use_host_mapping:
                # Load individual host file on-demand with LRU cache
                if host_id in self.host_fasta_cache:
                    # Move to end (most recently used)
                    self.host_fasta_cache.move_to_end(host_id)
                else:
                    if host_id not in self.host_mapping:
                        logger.warning(f"⚠️  Host ID '{host_id}' not found in mapping")
                        return ""
                    
                    fasta_path = self.host_mapping[host_id]
                    if not Path(fasta_path).exists():
                        logger.warning(f"⚠️  Host FASTA file not found: {fasta_path}")
                        return ""
                    
                    # Check if .fai index file exists
                    index_path = Path(str(fasta_path) + '.fai')
                    if not index_path.exists():
                        logger.warning(f"⚠️  Host FASTA index not found: {index_path}")
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
                    
                    self.host_fasta_cache[host_id] = self._load_fasta_file(fasta_path)
                
                fasta_obj = self.host_fasta_cache[host_id]
                keys = list(fasta_obj.keys())
                if not keys:
                    logger.warning(f"⚠️  No sequences found in host file for {host_id}")
                    return ""
                return str(fasta_obj[keys[0]][:].seq)
            else:
                # Legacy single-file mode
                return str(self.host_fasta[host_id][:].seq)
        except KeyError:
            logger.warning(f"⚠️  Host sequence not found for ID: {host_id}")
            return ""
        except Exception as e:
            logger.warning(f"⚠️  Error retrieving host sequence for {host_id}: {e}")
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
        sample['Host_Sequence'] = self._get_host_sequence_safe(meta['Host_ID'])
        
        # Apply transform if provided
        if self.transform:
            sample = self.transform(sample)
        
        return sample
    
    def close(self):
        """Close all open FASTA file handles to prevent resource leaks."""
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
    
    def __del__(self):
        """Destructor to ensure cleanup when object is deleted."""
        self.close()

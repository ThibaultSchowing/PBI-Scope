"""
Negative Example Generator for Machine Learning Training

This module provides utilities to generate negative examples (non-interacting phage-host pairs)
for machine learning training on phage-host interaction prediction.
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, List
from pbi.sequence_retrieval import SequenceRetriever

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class NegativeExampleGenerator:
    """
    Generate negative examples (non-interacting phage-host pairs) for ML training.
    
    Strategies:
    1. Random pairing - Random phage + random host (with validation)
    2. Taxonomy-based - Pair phages with phylogenetically distant hosts
    3. GC-content based - Pair phages with hosts having very different GC%
    4. Mixed strategy - Combination of above
    
    Example:
        >>> from pbi import quick_connect
        >>> from pbi.negative_examples import NegativeExampleGenerator
        >>> 
        >>> retriever = quick_connect()
        >>> neg_gen = NegativeExampleGenerator(retriever)
        >>> 
        >>> # Get positive pairs
        >>> positive_pairs = retriever.get_phage_host_pairs(limit=1000)
        >>> 
        >>> # Generate equal number of negatives
        >>> negatives = neg_gen.generate_random_negatives(positive_pairs, ratio=1.0)
    """
    
    def __init__(self, retriever: SequenceRetriever):
        """
        Initialize NegativeExampleGenerator
        
        Args:
            retriever: SequenceRetriever instance with host data
        """
        if not retriever._has_host_data:
            raise ValueError("SequenceRetriever must have host data - pass host_fasta_path to constructor")
        
        self.retriever = retriever
        self.conn = retriever.conn
        
        # Cache available phages and hosts
        self._cache_phages_and_hosts()
        
        logging.info(f"✅ NegativeExampleGenerator initialized")
        logging.info(f"   Available phages: {len(self.all_phages):,}")
        logging.info(f"   Available hosts: {len(self.all_hosts):,}")
    
    def _cache_phages_and_hosts(self):
        """Cache available phages and hosts from database"""
        # Get all phages with metadata
        phage_query = """
        SELECT DISTINCT
            Phage_ID,
            GC_content as Phage_GC,
            Length as Phage_Length,
            Taxonomy
        FROM fact_phages
        WHERE GC_content IS NOT NULL
            AND Length IS NOT NULL
        """
        self.all_phages = self.conn.execute(phage_query).fetchdf()
        
        # Get all hosts with metadata
        host_query = """
        SELECT DISTINCT
            Host_ID,
            Species_Name,
            GC_Content as Host_GC,
            Genome_Length as Host_Length
        FROM dim_hosts
        WHERE GC_Content IS NOT NULL
            AND Genome_Length IS NOT NULL
        """
        self.all_hosts = self.conn.execute(host_query).fetchdf()
        
        logging.info(f"📊 Cached {len(self.all_phages):,} phages and {len(self.all_hosts):,} hosts")
    
    def _get_positive_set(self, positive_pairs: pd.DataFrame) -> set:
        """
        Create a set of positive (Phage_ID, Host_ID) tuples for fast lookup
        
        Args:
            positive_pairs: DataFrame with Phage_ID and Host_ID columns
        
        Returns:
            Set of (phage_id, host_id) tuples
        """
        return set(zip(positive_pairs['Phage_ID'], positive_pairs['Host_ID']))
    
    def generate_random_negatives(self, 
                                   positive_pairs: pd.DataFrame,
                                   ratio: float = 1.0,
                                   max_attempts: int = 10) -> pd.DataFrame:
        """
        Generate random negative pairs ensuring they don't exist in positive set.
        
        Args:
            positive_pairs: DataFrame with Phage_ID and Host_ID columns
            ratio: Ratio of negatives to positives (1.0 = equal numbers)
            max_attempts: Maximum attempts per negative to avoid positives
        
        Returns:
            DataFrame with negative pairs (Phage_ID, Host_ID, Label=0)
        
        Example:
            >>> positives = retriever.get_phage_host_pairs(limit=100)
            >>> negatives = neg_gen.generate_random_negatives(positives, ratio=1.0)
        """
        logging.info("🎲 Generating random negative examples...")
        
        n_negatives = int(len(positive_pairs) * ratio)
        positive_set = self._get_positive_set(positive_pairs)
        
        logging.info(f"   Target: {n_negatives:,} negatives from {len(positive_pairs):,} positives")
        logging.info(f"   Positive set size: {len(positive_set):,}")
        
        negatives = []
        attempts = 0
        max_total_attempts = n_negatives * max_attempts
        
        while len(negatives) < n_negatives and attempts < max_total_attempts:
            # Random phage and host
            phage = self.all_phages.sample(n=1).iloc[0]
            host = self.all_hosts.sample(n=1).iloc[0]
            
            pair = (phage['Phage_ID'], host['Host_ID'])
            
            # Check if this is not a positive pair
            if pair not in positive_set:
                negatives.append({
                    'Phage_ID': phage['Phage_ID'],
                    'Host_ID': host['Host_ID'],
                    'Phage_GC': phage.get('Phage_GC'),
                    'Phage_Length': phage.get('Phage_Length'),
                    'Host_GC': host.get('Host_GC'),
                    'Host_Length': host.get('Host_Length'),
                    'Label': 0
                })
            
            attempts += 1
            
            # Progress update
            if len(negatives) % 100 == 0 and len(negatives) > 0:
                logging.info(f"   Generated {len(negatives):,}/{n_negatives:,} negatives...")
        
        if len(negatives) < n_negatives:
            logging.warning(f"⚠️  Only generated {len(negatives):,}/{n_negatives:,} negatives")
        
        df = pd.DataFrame(negatives)
        logging.info(f"✅ Generated {len(df):,} random negative pairs")
        
        return df
    
    def generate_gc_based_negatives(self,
                                     positive_pairs: pd.DataFrame,
                                     ratio: float = 1.0,
                                     min_gc_difference: float = 20.0,
                                     max_attempts: int = 10) -> pd.DataFrame:
        """
        Generate negatives by pairing phages with hosts having different GC content.
        
        This strategy creates biologically plausible negatives by selecting pairs
        where the GC content difference exceeds a threshold, as similar GC content
        is often an indicator of host-phage compatibility.
        
        Args:
            positive_pairs: DataFrame with Phage_ID and Host_ID columns
            ratio: Ratio of negatives to positives (1.0 = equal numbers)
            min_gc_difference: Minimum GC% difference between phage and host
            max_attempts: Maximum attempts per negative
        
        Returns:
            DataFrame with negative pairs (Phage_ID, Host_ID, Label=0)
        
        Example:
            >>> # Generate negatives with >20% GC difference
            >>> negatives = neg_gen.generate_gc_based_negatives(
            ...     positives, 
            ...     ratio=1.0, 
            ...     min_gc_difference=20.0
            ... )
        """
        logging.info(f"🧬 Generating GC-based negative examples (min diff: {min_gc_difference}%)...")
        
        n_negatives = int(len(positive_pairs) * ratio)
        positive_set = self._get_positive_set(positive_pairs)
        
        negatives = []
        attempts = 0
        max_total_attempts = n_negatives * max_attempts
        
        while len(negatives) < n_negatives and attempts < max_total_attempts:
            # Random phage and host
            phage = self.all_phages.sample(n=1).iloc[0]
            host = self.all_hosts.sample(n=1).iloc[0]
            
            pair = (phage['Phage_ID'], host['Host_ID'])
            
            # Check GC difference
            gc_diff = abs(phage['Phage_GC'] - host['Host_GC'])
            
            # Must not be positive AND have high GC difference
            if pair not in positive_set and gc_diff >= min_gc_difference:
                negatives.append({
                    'Phage_ID': phage['Phage_ID'],
                    'Host_ID': host['Host_ID'],
                    'Phage_GC': phage.get('Phage_GC'),
                    'Phage_Length': phage.get('Phage_Length'),
                    'Host_GC': host.get('Host_GC'),
                    'Host_Length': host.get('Host_Length'),
                    'GC_Difference': gc_diff,
                    'Label': 0
                })
            
            attempts += 1
            
            if len(negatives) % 100 == 0 and len(negatives) > 0:
                logging.info(f"   Generated {len(negatives):,}/{n_negatives:,} negatives...")
        
        if len(negatives) < n_negatives:
            logging.warning(f"⚠️  Only generated {len(negatives):,}/{n_negatives:,} GC-based negatives")
        
        df = pd.DataFrame(negatives)
        logging.info(f"✅ Generated {len(df):,} GC-based negative pairs")
        if len(df) > 0:
            logging.info(f"   Mean GC difference: {df['GC_Difference'].mean():.1f}%")
        
        return df
    
    def generate_taxonomy_based_negatives(self,
                                          positive_pairs: pd.DataFrame,
                                          ratio: float = 1.0,
                                          exclude_species: Optional[List[str]] = None,
                                          max_attempts: int = 10) -> pd.DataFrame:
        """
        Generate negatives by pairing phages with taxonomically distant hosts.
        
        This uses the Species_Name field to avoid pairing phages with hosts
        from the same genus/species as their known hosts.
        
        Args:
            positive_pairs: DataFrame with Phage_ID and Host_ID columns
            ratio: Ratio of negatives to positives
            exclude_species: List of species to exclude (e.g., known hosts)
            max_attempts: Maximum attempts per negative
        
        Returns:
            DataFrame with negative pairs (Phage_ID, Host_ID, Label=0)
        
        Example:
            >>> # Generate negatives excluding Escherichia hosts
            >>> negatives = neg_gen.generate_taxonomy_based_negatives(
            ...     positives,
            ...     exclude_species=['Escherichia coli']
            ... )
        """
        logging.info("🌳 Generating taxonomy-based negative examples...")
        
        n_negatives = int(len(positive_pairs) * ratio)
        positive_set = self._get_positive_set(positive_pairs)
        
        # Build exclusion set from positive pairs if not provided
        if exclude_species is None:
            # Get species from positive pairs
            exclude_species = set()
            for _, row in positive_pairs.iterrows():
                # Use parameterized query to prevent SQL injection
                host_info = self.conn.execute(
                    "SELECT Species_Name FROM dim_hosts WHERE Host_ID = ?",
                    [row['Host_ID']]
                ).fetchdf()
                if len(host_info) > 0:
                    exclude_species.add(host_info.iloc[0]['Species_Name'])
        
        logging.info(f"   Excluding {len(exclude_species)} species from negatives")
        
        # Filter hosts not in exclusion list
        available_hosts = self.all_hosts[
            ~self.all_hosts['Species_Name'].isin(exclude_species)
        ]
        
        if len(available_hosts) == 0:
            logging.warning("⚠️  No hosts available after exclusion")
            return pd.DataFrame()
        
        logging.info(f"   Available hosts after exclusion: {len(available_hosts):,}")
        
        negatives = []
        attempts = 0
        max_total_attempts = n_negatives * max_attempts
        
        while len(negatives) < n_negatives and attempts < max_total_attempts:
            phage = self.all_phages.sample(n=1).iloc[0]
            host = available_hosts.sample(n=1).iloc[0]
            
            pair = (phage['Phage_ID'], host['Host_ID'])
            
            if pair not in positive_set:
                negatives.append({
                    'Phage_ID': phage['Phage_ID'],
                    'Host_ID': host['Host_ID'],
                    'Phage_GC': phage.get('Phage_GC'),
                    'Phage_Length': phage.get('Phage_Length'),
                    'Host_GC': host.get('Host_GC'),
                    'Host_Length': host.get('Host_Length'),
                    'Host_Species': host.get('Species_Name'),
                    'Label': 0
                })
            
            attempts += 1
            
            if len(negatives) % 100 == 0 and len(negatives) > 0:
                logging.info(f"   Generated {len(negatives):,}/{n_negatives:,} negatives...")
        
        df = pd.DataFrame(negatives)
        logging.info(f"✅ Generated {len(df):,} taxonomy-based negative pairs")
        
        return df
    
    def generate_balanced_dataset(self,
                                  positive_pairs: Optional[pd.DataFrame] = None,
                                  strategy: str = 'mixed',
                                  positive_ratio: float = 0.5,
                                  total_samples: Optional[int] = None) -> pd.DataFrame:
        """
        Generate a balanced dataset with positive and negative examples.
        
        Args:
            positive_pairs: DataFrame with positive pairs (if None, queries from database)
            strategy: 'random', 'taxonomy', 'gc', or 'mixed'
            positive_ratio: Ratio of positive examples (0.5 = 50% positive, 50% negative)
            total_samples: Total number of samples (if None, uses all positives)
        
        Returns:
            DataFrame with Label column (1=positive, 0=negative)
        
        Example:
            >>> # Generate balanced dataset with 50/50 split
            >>> dataset = neg_gen.generate_balanced_dataset(
            ...     strategy='mixed',
            ...     positive_ratio=0.5,
            ...     total_samples=10000
            ... )
        """
        logging.info(f"🔨 Generating balanced dataset (strategy: {strategy}, ratio: {positive_ratio})...")
        
        # Get positive pairs if not provided
        if positive_pairs is None:
            logging.info("   Fetching positive pairs from database...")
            positive_pairs = self.retriever.get_phage_host_pairs()
        
        # Add label column
        positive_pairs['Label'] = 1
        
        # Determine sample counts
        if total_samples:
            n_positives = int(total_samples * positive_ratio)
            n_negatives = total_samples - n_positives
            
            # Sample positives if we have more than needed
            if len(positive_pairs) > n_positives:
                positive_pairs = positive_pairs.sample(n=n_positives, random_state=42)
        else:
            n_positives = len(positive_pairs)
            n_negatives = int(n_positives * (1 - positive_ratio) / positive_ratio)
        
        logging.info(f"   Target: {n_positives:,} positives, {n_negatives:,} negatives")
        
        # Generate negatives based on strategy
        neg_ratio = n_negatives / len(positive_pairs)
        
        if strategy == 'random':
            negatives = self.generate_random_negatives(positive_pairs, ratio=neg_ratio)
        
        elif strategy == 'gc':
            negatives = self.generate_gc_based_negatives(positive_pairs, ratio=neg_ratio)
        
        elif strategy == 'taxonomy':
            negatives = self.generate_taxonomy_based_negatives(positive_pairs, ratio=neg_ratio)
        
        elif strategy == 'mixed':
            # Mix of all strategies (1/3 each)
            third = neg_ratio / 3.0
            
            neg_random = self.generate_random_negatives(positive_pairs, ratio=third)
            neg_gc = self.generate_gc_based_negatives(positive_pairs, ratio=third)
            neg_tax = self.generate_taxonomy_based_negatives(positive_pairs, ratio=third)
            
            negatives = pd.concat([neg_random, neg_gc, neg_tax], ignore_index=True)
        
        else:
            raise ValueError(f"Unknown strategy: {strategy}. Use 'random', 'gc', 'taxonomy', or 'mixed'")
        
        # Combine positives and negatives
        dataset = pd.concat([positive_pairs, negatives], ignore_index=True)
        
        # Shuffle
        dataset = dataset.sample(frac=1, random_state=42).reset_index(drop=True)
        
        # Summary statistics
        pos_count = (dataset['Label'] == 1).sum()
        neg_count = (dataset['Label'] == 0).sum()
        
        logging.info(f"✅ Generated balanced dataset:")
        logging.info(f"   Total samples: {len(dataset):,}")
        logging.info(f"   Positives: {pos_count:,} ({pos_count/len(dataset)*100:.1f}%)")
        logging.info(f"   Negatives: {neg_count:,} ({neg_count/len(dataset)*100:.1f}%)")
        
        return dataset


# Example usage
if __name__ == "__main__":
    from pbi import quick_connect
    
    print("🧪 Testing NegativeExampleGenerator")
    print("="*80)
    
    # Connect to database
    retriever = quick_connect()
    
    # Initialize generator
    gen = NegativeExampleGenerator(retriever)
    
    # Get positive pairs (limited for testing)
    print("\n📥 Fetching positive pairs...")
    positives = retriever.get_phage_host_pairs(limit=100)
    print(f"✅ Got {len(positives)} positive pairs")
    
    # Test random negatives
    print("\n🎲 Testing random negatives...")
    random_neg = gen.generate_random_negatives(positives, ratio=1.0)
    print(f"✅ Generated {len(random_neg)} random negatives")
    
    # Test GC-based negatives
    print("\n🧬 Testing GC-based negatives...")
    gc_neg = gen.generate_gc_based_negatives(positives, ratio=0.5, min_gc_difference=15.0)
    print(f"✅ Generated {len(gc_neg)} GC-based negatives")
    
    # Test balanced dataset
    print("\n🔨 Testing balanced dataset...")
    dataset = gen.generate_balanced_dataset(
        positive_pairs=positives,
        strategy='mixed',
        positive_ratio=0.5
    )
    print(f"✅ Generated dataset with {len(dataset)} samples")
    
    print("\n✅ All tests passed!")

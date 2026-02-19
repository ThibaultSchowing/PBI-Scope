"""
Host genome download and processing rules

This Snakefile handles:
1. Downloading host bacterial genomes from NCBI
2. Merging individual genomes into single FASTA
3. Indexing the merged FASTA with pyfaidx
"""

import os

rule download_host_genomes:
    """
    Download host bacterial genomes from NCBI RefSeq
    
    This rule extracts unique host species from the phage metadata CSV and downloads
    reference genomes for each using either:
    - Robust downloader (recommended): assembly_resolver.py + download_host_genomes_robust.py
    - Legacy downloader: download_host_genomes.py or download_host_genomes_optimized.py
    
    The robust downloader:
    - Uses NCBI Assembly database as authoritative source
    - Normalizes all identifiers to assembly accessions (GCF_ preferred)
    - Handles ambiguity in species names explicitly
    - Supports metadata-only mode (no downloads)
    - Preserves existing downloads with validation
    - Creates phage-host assembly links
    
    Note: Reads from CSV instead of database to avoid circular dependency
    (database is created after host downloads).
    """
    input:
        phage_csv = config["phage_metadata_merged_output"]
    output:
        metadata = config["host_metadata_output"],
        assembly_metadata = config.get("assembly_metadata_output", 
                                       config["host_metadata_output"].replace('.csv', '_assemblies.csv')),
        phage_host_links = config.get("phage_host_links_output",
                                      config["host_metadata_output"].replace('.csv', '_phage_host_links.csv')),
        phage_host_candidates = config.get("phage_host_candidates_output",
                                           config["host_metadata_output"].replace('.csv', '_host_candidates.csv')),
        phage_host_assemblies = config.get("phage_host_assemblies_output",
                                           config["host_metadata_output"].replace('.csv', '_host_assemblies.csv'))
    params:
        output_dir = config["host_genomes_intermediate"],
        limit = None,  # Set to integer for testing with subset of hosts
        metadata_only = config.get("metadata_only_mode", False),
        skip_existing = config.get("skip_existing_downloads", True),
        validate_checksums = config.get("validate_file_checksums", True),
        use_robust_downloader = config.get("use_robust_downloader", True)  # Use new robust downloader by default
    log:
        config["host_download_log"]
    conda:
        "../envs/sequences.yaml"
    script:
        # Use robust downloader if enabled, otherwise use legacy downloader
        "../scripts/sequences/download_host_genomes_robust.py" if params.use_robust_downloader else "../scripts/sequences/download_host_genomes.py"


rule create_host_mapping:
    """
    Create mapping file from Host_ID to individual FASTA file paths
    
    Instead of merging all host genomes, this creates a JSON mapping that allows
    on-demand loading of individual host genome files for efficient memory usage.
    """
    input:
        metadata = config["host_metadata_output"]
    output:
        mapping = config["host_fasta_mapping"]
    params:
        input_dir = config["host_genomes_intermediate"]
    log:
        "logs/create_host_mapping.log"
    run:
        import json
        from pathlib import Path
        import pandas as pd
        
        # Read metadata to get list of Host_IDs
        metadata_df = pd.read_csv(input.metadata)
        
        output_path = Path(output.mapping)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        input_dir = Path(params.input_dir)
        
        # Create mapping from Host_ID to file path
        host_mapping = {}
        valid_count = 0
        missing_count = 0
        
        for _, row in metadata_df.iterrows():
            host_id = row['Host_ID']
            fasta_file = input_dir / f"{host_id}.fna"
            
            if fasta_file.exists() and fasta_file.stat().st_size > 0:
                host_mapping[host_id] = str(fasta_file)
                valid_count += 1
            else:
                missing_count += 1
                print(f"⚠️ Missing or empty file: {fasta_file}", file=open(log[0], 'a'))
        
        if not host_mapping:
            raise ValueError("❌ No valid host FASTA files found!")
        
        # Write mapping to JSON file
        with open(output.mapping, 'w') as f:
            json.dump(host_mapping, f, indent=2)
        
        print(f"✅ Created mapping for {valid_count} host FASTA files", file=open(log[0], 'a'))
        if missing_count > 0:
            print(f"⚠️ {missing_count} host files were missing or empty", file=open(log[0], 'a'))


rule index_individual_host_sequences:
    """
    Create pyfaidx indexes for individual host genome FASTA files
    
    Generates .fai index files for each host genome to enable fast random access
    without needing to merge all files into one large file.
    """
    input:
        mapping = config["host_fasta_mapping"]
    output:
        touch(config["host_index_complete_flag"])
    log:
        "logs/index_individual_host_sequences.log"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/index_individual_hosts.py"


rule all_hosts:
    """
    Target rule for all host genome processing
    """
    input:
        config["host_index_complete_flag"],
        config["host_fasta_mapping"],
        config["host_metadata_output"],
        config.get("phage_host_candidates_output",
                   config["host_metadata_output"].replace('.csv', '_host_candidates.csv')),
        config.get("phage_host_assemblies_output",
                   config["host_metadata_output"].replace('.csv', '_host_assemblies.csv'))

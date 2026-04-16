"""
Host genome download and processing rules

This Snakefile handles:
1. Downloading host bacterial genomes from NCBI
2. Merging individual genomes into single FASTA
3. Indexing the merged FASTA with pyfaidx
"""

import os

PRIVATE_CONFLICT_EXAMPLE_LIMIT = 20

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
                                           config["host_metadata_output"].replace('.csv', '_host_assemblies.csv')),
        host_resolution_cache = config.get("host_resolution_cache_output",
                                           config["host_metadata_output"].replace('.csv', '_token_resolution_cache.json'))
    params:
        output_dir = config["host_genomes_intermediate"],
        limit = None,  # Set to integer for testing with subset of hosts
        metadata_only = config.get("metadata_only_mode", False),
        skip_existing = config.get("skip_existing_downloads", True),
        validate_checksums = config.get("validate_file_checksums", True),
        reuse_resolution_cache = config.get("reuse_host_resolution_cache", True),
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
        metadata = config["host_metadata_output"],
        private_mapping = config["private_host_mapping"]
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
        
        # Merge private host mapping entries (if any)
        private_mapping_path = Path(input.private_mapping)
        private_added = 0
        private_conflicts = 0
        conflict_ids = []
        if private_mapping_path.exists():
            with private_mapping_path.open("r") as f:
                private_mapping = json.load(f)
            for host_id, fasta_path in private_mapping.items():
                if host_id in host_mapping:
                    private_conflicts += 1
                    if len(conflict_ids) < PRIVATE_CONFLICT_EXAMPLE_LIMIT:
                        conflict_ids.append(host_id)
                    continue
                fasta_file = Path(fasta_path)
                if fasta_file.exists() and fasta_file.stat().st_size > 0:
                    host_mapping[host_id] = str(fasta_file)
                    private_added += 1

        # Write mapping to JSON file
        with open(output.mapping, 'w') as f:
            json.dump(host_mapping, f, indent=2)
        
        print(f"✅ Created mapping for {valid_count} host FASTA files", file=open(log[0], 'a'))
        print(f"✅ Added {private_added} private host FASTA files", file=open(log[0], 'a'))
        if private_conflicts > 0:
            print(f"⚠️ Skipped {private_conflicts} conflicting private Host_ID entries", file=open(log[0], 'a'))
            print(f"   Conflicting Host_ID examples: {', '.join(conflict_ids)}", file=open(log[0], 'a'))
        if missing_count > 0:
            print(f"⚠️ {missing_count} host files were missing or empty", file=open(log[0], 'a'))


rule index_individual_host_sequences:
    """
    Create pyfaidx indexes for individual host genome FASTA files

    FASTA quality-control procedure (non-destructive):
    1. Header audit: duplicate sequence identifiers → file rejected, event logged.
    2. Sequence content audit: identical sequences → warning logged, file still indexed.

    Generates .fai index files for all files that pass the header-uniqueness check.
    Produces a DataFrame-loadable CSV QC log for downstream analysis.
    """
    input:
        mapping = config["host_fasta_mapping"]
    output:
        flag    = touch(config["host_index_complete_flag"]),
        qc_log  = config["host_fasta_qc_log"]
    log:
        "logs/index_individual_host_sequences.log"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/index_individual_hosts.py"


rule create_host_status_report:
    """
    Combined per-phage host status report (DataFrame-loadable CSV)

    Joins phage_host_candidates + phage_host_assemblies + assembly_metadata
    + FASTA QC log into one table with one row per (Phage_ID, Host_Token).

    Enables queries like:
    - For all phages, how many have ≥1 resolved host assembly?
    - Of resolved hosts, how many were downloaded / indexed / rejected?
    """
    input:
        candidates        = config.get("phage_host_candidates_output",
                                       config["host_metadata_output"].replace('.csv', '_host_candidates.csv')),
        assemblies        = config.get("phage_host_assemblies_output",
                                       config["host_metadata_output"].replace('.csv', '_host_assemblies.csv')),
        assembly_metadata = config.get("assembly_metadata_output",
                                       config["host_metadata_output"].replace('.csv', '_assemblies.csv')),
        qc_log            = config["host_fasta_qc_log"]
    output:
        status_report = config["host_status_report"]
    log:
        "logs/create_host_status_report.log"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/create_host_status_report.py"


rule all_hosts:
    """
    Target rule for all host genome processing
    """
    input:
        config["host_index_complete_flag"],
        config["host_fasta_qc_log"],
        config["host_status_report"],
        config["host_fasta_mapping"],
        config["host_metadata_output"],
        config.get("phage_host_candidates_output",
                   config["host_metadata_output"].replace('.csv', '_host_candidates.csv')),
        config.get("phage_host_assemblies_output",
                   config["host_metadata_output"].replace('.csv', '_host_assemblies.csv'))

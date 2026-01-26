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
    
    This rule extracts unique host species from the database and downloads
    reference genomes for each using NCBI datasets CLI (primary) or Entrez API (fallback).
    """
    input:
        db = config["optimized_duckdb_output"]
    output:
        metadata = config["host_metadata_output"]
    params:
        output_dir = config["host_genomes_intermediate"],
        limit = None  # Set to integer for testing with subset of hosts
    log:
        config["host_download_log"]
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/download_host_genomes.py"


rule merge_host_fasta:
    """
    Merge all individual host genome FASTA files into single file
    
    Similar to phage and protein FASTA merging, combines all downloaded
    host genomes into one indexed file for efficient retrieval.
    """
    input:
        metadata = config["host_metadata_output"]
    output:
        fasta = config["all_hosts_fasta"]
    params:
        input_dir = config["host_genomes_intermediate"]
    log:
        "logs/merge_host_fasta.log"
    run:
        import os
        from pathlib import Path
        import pandas as pd
        
        # Read metadata to get list of Host_IDs
        metadata_df = pd.read_csv(input.metadata)
        
        output_path = Path(output.fasta)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        input_dir = Path(params.input_dir)
        
        # Find all FASTA files based on Host_IDs in metadata
        valid_files = []
        for _, row in metadata_df.iterrows():
            host_id = row['Host_ID']
            fasta_file = input_dir / f"{host_id}.fna"
            
            if fasta_file.exists() and fasta_file.stat().st_size > 0:
                valid_files.append(fasta_file)
            else:
                print(f"⚠️ Missing or empty file: {fasta_file}", file=open(log[0], 'a'))
        
        if not valid_files:
            raise ValueError("❌ No valid host FASTA files found!")
        
        # Merge files
        with open(output.fasta, 'w') as outfile:
            for fasta_file in valid_files:
                with open(fasta_file, 'r') as infile:
                    content = infile.read()
                    if content.strip():
                        outfile.write(content)
                        if not content.endswith('\n'):
                            outfile.write('\n')
        
        print(f"✅ Merged {len(valid_files)} host FASTA files", file=open(log[0], 'a'))


rule index_host_sequences:
    """
    Create pyfaidx index for host genome FASTA file
    
    Generates .fai index file for fast random access to host sequences.
    """
    input:
        config["all_hosts_fasta"]
    output:
        config["all_hosts_fasta"] + ".fai"
    log:
        "logs/index_host_sequences.log"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/index_sequences.py"


rule all_hosts:
    """
    Target rule for all host genome processing
    """
    input:
        config["all_hosts_fasta"] + ".fai",
        config["host_metadata_output"]

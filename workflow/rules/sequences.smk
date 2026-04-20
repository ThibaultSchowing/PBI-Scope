import os

# Extract source names from config
PHAGE_FASTA_SOURCES = list(config["phage_fasta_urls"].keys())
PROTEIN_FASTA_SOURCES = list(config["protein_fasta_urls"].keys())

rule prepare_private_sequences:
    """
    Prepare sequence artifacts for private datasets.

    For each valid private source the rule:
      1. Copies (and filters) the source phage.fasta to a writable per-source directory
         so that pyfaidx can create the .fai index file next to it.
      2. Indexes the copied phage FASTA with pyfaidx.
      3. Writes a JSON mapping  source_db → phage.fasta path  (private_phage_mapping).
      4. Writes a JSON mapping  Host_ID → host.fna path  (private_host_mapping),
         pointing directly at each source's hosts/<Host_ID>.fna — no copy needed.

    The private phage FASTA files are intentionally kept separate from all_phages.fasta.
    SequenceRetriever uses private_phage_mapping to look up sequences for private phages
    at retrieval time, routing by source_type from the database.
    """
    input:
        manifest=config["private_manifest_output"]
    output:
        private_phage_mapping=config["private_phage_mapping"],
        private_host_mapping=config["private_host_mapping"]
    params:
        private_phage_dir=config["private_phage_genomes_intermediate"]
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/prepare_private_sequences.py"

rule merge_phage_fasta:
    input:
        expand(
            config["phage_fasta_merged_output"] + "{source}.fasta",
            source=PHAGE_FASTA_SOURCES
        )
    output:
        config["all_phages_fasta"]
    log:
        config["merge_phage_fasta_log"]
    run:
        import os
        from pathlib import Path
        
        output_path = Path(output[0])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if input files exist and are non-empty
        valid_files = []
        for fasta_file in input:
            if os.path.exists(fasta_file) and os.path.getsize(fasta_file) > 0:
                valid_files.append(fasta_file)
            else:
                print(f"⚠️ Skipping empty or missing file: {fasta_file}", file=open(log[0], 'a'))
        
        if not valid_files:
            raise ValueError("❌ No valid FASTA files found for phages!")
        
        # Merge valid files
        with open(output[0], 'w') as outfile:
            for fasta_file in valid_files:
                with open(fasta_file, 'r') as infile:
                    content = infile.read()
                    if content.strip():  # Only write non-empty content
                        outfile.write(content)
                        if not content.endswith('\n'):
                            outfile.write('\n')
        
        print(f"✅ Merged {len(valid_files)}/{len(input)} phage FASTA files", file=open(log[0], 'a'))

rule merge_protein_fasta:
    input:
        expand(
            config["protein_fasta_merged_output"] + "{source}.fasta", 
            source=PROTEIN_FASTA_SOURCES
        )
    output:
        config["all_proteins_fasta"]
    log:
        config["merge_protein_fasta_log"]
    run:
        import os
        from pathlib import Path
        
        output_path = Path(output[0])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if input files exist and are non-empty
        valid_files = []
        for fasta_file in input:
            if os.path.exists(fasta_file) and os.path.getsize(fasta_file) > 0:
                valid_files.append(fasta_file)
            else:
                print(f"⚠️ Skipping empty or missing file: {fasta_file}", file=open(log[0], 'a'))
        
        if not valid_files:
            raise ValueError("❌ No valid FASTA files found for proteins!")
        
        # Merge valid files
        with open(output[0], 'w') as outfile:
            for fasta_file in valid_files:
                with open(fasta_file, 'r') as infile:
                    content = infile.read()
                    if content.strip():  # Only write non-empty content
                        outfile.write(content)
                        if not content.endswith('\n'):
                            outfile.write('\n')
        
        print(f"✅ Merged {len(valid_files)}/{len(input)} protein FASTA files", file=open(log[0], 'a'))

rule index_phage_sequences:
    input:
        config["all_phages_fasta"]
    output:
        config["all_phages_fasta"] + ".fai"
    log:
        config["index_phage_sequences_log"]
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/index_sequences.py"

rule index_protein_sequences:
    input:
        config["all_proteins_fasta"]
    output:
        config["all_proteins_fasta"] + ".fai"
    log:
        config["index_protein_sequences_log"]
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/index_sequences.py"

rule all_sequences:
    input:
        config["all_phages_fasta"] + ".fai",
        config["all_proteins_fasta"] + ".fai"

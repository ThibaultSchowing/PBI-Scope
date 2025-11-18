import os

# Extract source names from config
PHAGE_FASTA_SOURCES = list(config["phage_fasta_urls"].keys())
PROTEIN_FASTA_SOURCES = list(config["protein_fasta_urls"].keys())

rule merge_phage_fasta:
    input:
        expand("../data/phage_fasta_merged/{source}.fasta", source=PHAGE_FASTA_SOURCES)
    output:
        "../data/sequences/all_phages.fasta"
    log:
        "logs/merge_phage_fasta.log"
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
        expand("../data/protein_fasta_merged/{source}.fasta", source=PROTEIN_FASTA_SOURCES)
    output:
        "../data/sequences/all_proteins.fasta"
    log:
        "logs/merge_protein_fasta.log"
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
        "../data/sequences/all_phages.fasta"
    output:
        "../data/sequences/all_phages.fasta.fai"
    log:
        "logs/index_phage_sequences.log"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/index_sequences.py"

rule index_protein_sequences:
    input:
        "../data/sequences/all_proteins.fasta"
    output:
        "../data/sequences/all_proteins.fasta.fai"
    log:
        "logs/index_protein_sequences.log"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/index_sequences.py"

rule all_sequences:
    input:
        "../data/sequences/all_phages.fasta.fai",
        "../data/sequences/all_proteins.fasta.fai"
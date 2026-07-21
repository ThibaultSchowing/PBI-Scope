
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
        fasta=config["all_phages_fasta"],
        per_source_counts=config["per_source_phage_counts"]
    log:
        config["merge_phage_fasta_log"]
    params:
        sequence_type="phage"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/merge_fasta.py"

rule merge_protein_fasta:
    input:
        expand(
            config["protein_fasta_merged_output"] + "{source}.fasta", 
            source=PROTEIN_FASTA_SOURCES
        )
    output:
        fasta=config["all_proteins_fasta"],
        per_source_counts=config["per_source_protein_counts"]
    log:
        config["merge_protein_fasta_log"]
    params:
        sequence_type="protein"
    conda:
        "../envs/sequences.yaml"
    script:
        "../scripts/sequences/merge_fasta.py"

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

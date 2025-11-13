rule create_duckdb:
    input:
        phage_data="../data/merged/merged_phage_metadata.csv", 
        protein_data="../data/merged/merged_annotated_proteins_metadata.csv", 
        terminator_data="../data/merged/merged_transcription_terminator_metadata.csv",
        anti_crispr_data="../data/merged/merged_phage_anti_crispr_metadata.csv", 
        virulent_factor_data="../data/merged/merged_phage_virulent_factor_metadata.csv",
        transmembrane_data="../data/merged/merged_phage_transmembrane_protein_metadata.csv",
        trna_tmrna_data="../data/merged/merged_phage_trna_tmrna_metadata.csv"
    output:
        db="../data/databases/phage_database.duckdb"
    conda:
        "../envs/pixi_base_env.yaml"
    script:
        "../scripts/create_duckdb.py"   

rule optimize_database:
    input:
        db="../data/databases/phage_database.duckdb"
    output:
        optimized_db="../data/databases/phage_database_optimized.duckdb"
    conda:
        "../envs/pixi_base_env.yaml"
    script:
        "../scripts/optimize_db.py"

rule validate_database:
    input:
        db="../data/databases/phage_database_optimized.duckdb"
    output:
        report="reports/database_validation.html"  
    conda:
        "../envs/pixi_base_env.yaml"
    script:
        "../scripts/validate_db.py"
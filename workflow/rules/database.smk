rule create_duckdb:
    input:
        phage_data="../data/merged/merged_phage_metadata.csv", 
        protein_data="../data/merged/merged_annotated_proteins_metadata.csv", 
        terminator_data="../data/merged/merged_transcription_terminator_metadata.csv"
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
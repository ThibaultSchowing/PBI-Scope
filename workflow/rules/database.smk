# Rules are executed from the snakefile in the workflow directory and the paths are relative to this directory
# so, ../data/ points to the data directory at the root of the project

rule create_duckdb:
    input:
        phage_data=config["phage_metadata_merged_output"], 
        protein_data=config["annotated_proteins_metadata_merged_output"], 
        terminator_data=config["transcription_terminator_metadata_merged_output"],
        anti_crispr_data=config["phage_anti_crispr_metadata_merged_output"], 
        virulent_factor_data=config["phage_virulent_factor_metadata_merged_output"],
        transmembrane_data=config["phage_transmembrane_protein_metadata_merged_output"],
        trna_tmrna_data=config["phage_trna_tmrna_metadata_merged_output"]
    output:
        db=config["duckdb_output"]
    conda:
        "../envs/pixi_base_env.yaml"
    script:
        "../scripts/database/create_duckdb.py"   

rule optimize_database:
    input:
        db=config["duckdb_output"]
    output:
        optimized_db=config["optimized_duckdb_output"]
    conda:
        "../envs/pixi_base_env.yaml"
    script:
        "../scripts/database/optimize_db.py"

rule validate_database:
    input:
        db=config["optimized_duckdb_output"]
    output:
        report=config["database_validation_report_output"]  
    conda:
        "../envs/pixi_base_env.yaml"
    script:
        "../scripts/database/validate_db.py"
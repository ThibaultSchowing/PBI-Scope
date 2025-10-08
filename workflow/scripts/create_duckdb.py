#!.pixi/envs/default/bin/python

import duckdb
import pandas as pd
import os
import logging

logging.basicConfig(level=logging.INFO)

def create_star_schema_duckdb():
    """Create DuckDB with star schema from PhageScope data"""
    
    # Get inputs and outputs from Snakemake
    phage_data = snakemake.input.phage_data
    protein_data = snakemake.input.protein_data
    terminator_data = snakemake.input.terminator_data
    db_path = snakemake.output.db
    
    # Create output directory
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    logging.info(f"Creating DuckDB database at {db_path}")
    
    conn = duckdb.connect(db_path)
    
    # Create fact table
    logging.info("Creating fact_phages table")
    conn.execute(f"""
    CREATE TABLE fact_phages AS 
    SELECT 
        Phage_ID,
        Source_DB,                              -- ✅ CHANGED from Phage_source
        TRY_CAST(NULLIF(Length, '-') AS INTEGER) as Length,
        TRY_CAST(NULLIF(GC_content, '-') AS DOUBLE) as GC_content,
        Taxonomy,
        Completeness,
        Host,
        Lifestyle,
        Cluster,
        Subcluster
    FROM read_csv('{phage_data}', 
                  header=true, 
                  all_varchar=true, 
                  ignore_errors=true,
                  null_padding=true)
    WHERE Phage_ID IS NOT NULL
    """)
    
    # Create protein dimension
    logging.info("Creating dim_proteins table")
    conn.execute(f"""
    CREATE TABLE dim_proteins AS
    SELECT 
        Phage_ID,
        Protein_ID,
        Protein_source, 
        Function_prediction_source, 
        TRY_CAST(NULLIF(Start, '-') AS INTEGER) as Start,
        TRY_CAST(NULLIF(Stop, '-') AS INTEGER) as Stop,
        Strand, 
        Product, 
        Protein_classification,
        TRY_CAST(NULLIF(Molecular_weight, '-') AS DOUBLE) as Molecular_weight,
        TRY_CAST(NULLIF(Aromaticity, '-') AS DOUBLE) as Aromaticity,
        TRY_CAST(NULLIF(Instability_index, '-') AS DOUBLE) as Instability_index,
        TRY_CAST(NULLIF(Isoelectric_point, '-') AS DOUBLE) as Isoelectric_point,
        TRY_CAST(NULLIF(Helix_fraction, '-') AS DOUBLE) as Helix_fraction,
        TRY_CAST(NULLIF(Turn_fraction, '-') AS DOUBLE) as Turn_fraction,
        TRY_CAST(NULLIF(Sheet_fraction, '-') AS DOUBLE) as Sheet_fraction,
        TRY_CAST(NULLIF(Reduced_coefficient, '-') AS DOUBLE) as Reduced_coefficient,
        TRY_CAST(NULLIF(Oxidized_coefficient, '-') AS DOUBLE) as Oxidized_coefficient,
        Source_DB                               -- ✅ CHANGED from Phage_source
    FROM read_csv('{protein_data}', 
                  header=true, 
                  all_varchar=true, 
                  ignore_errors=true,
                  null_padding=true)
    WHERE Protein_ID IS NOT NULL AND Phage_ID IS NOT NULL
    """)
    
    # Create terminator dimension
    logging.info("Creating dim_terminators table") 
    conn.execute(f"""
    CREATE TABLE dim_terminators AS
    SELECT 
        Phage_ID,
        Terminator as terminator_type,
        TRY_CAST(NULLIF(Start, '-') AS INTEGER) as terminator_start,
        TRY_CAST(NULLIF(Stop, '-') AS INTEGER) as terminator_end,
        TRY_CAST(NULLIF(Confidence, '-') AS DOUBLE) as confidence_score,
        Sense,
        Loc,
        Source_DB                               -- ✅ CHANGED from Phage_source
    FROM read_csv('{terminator_data}', 
                  header=true, 
                  all_varchar=true, 
                  ignore_errors=true,
                  null_padding=true)
    WHERE Phage_ID IS NOT NULL
    """)
    
    # Create performance indexes - Now consistent with Source_DB
    logging.info("Creating indexes")
    conn.execute("CREATE INDEX idx_Source_DB ON fact_phages(Source_DB)")        # ✅ Now matches!
    conn.execute("CREATE INDEX idx_phages_id ON fact_phages(Phage_ID)")
    conn.execute("CREATE INDEX idx_proteins_phage ON dim_proteins(Phage_ID)")
    conn.execute("CREATE INDEX idx_terminators_phage ON dim_terminators(Phage_ID)")
    
    # Create analytical views - Now consistent with Source_DB
    logging.info("Creating analytical views")
    conn.execute("""
    CREATE VIEW phage_summary AS
    SELECT 
        Source_DB,                              -- ✅ Now matches!
        COUNT(*) as total_phages,
        AVG(Length) as avg_length,
        AVG(GC_content) as avg_gc_content,
        MIN(Length) as min_length,
        MAX(Length) as max_length
    FROM fact_phages
    WHERE Length IS NOT NULL AND GC_content IS NOT NULL
    GROUP BY Source_DB                          -- ✅ Now matches!
    ORDER BY total_phages DESC
    """)
    
    conn.execute("""
    CREATE VIEW phage_size_distribution AS
    SELECT 
        Source_DB,                              -- ✅ Now matches!
        CASE 
            WHEN Length < 10000 THEN 'Small (<10kb)'
            WHEN Length < 100000 THEN 'Medium (10-100kb)'
            ELSE 'Large (>100kb)'
        END as size_category,
        COUNT(*) as count,
        AVG(Length) as avg_length
    FROM fact_phages
    WHERE Length IS NOT NULL
    GROUP BY Source_DB, size_category           -- ✅ Now matches!
    """)
    
    # Get summary statistics
    stats = conn.execute("SELECT COUNT(*) as total_phages FROM fact_phages").fetchone()
    protein_stats = conn.execute("SELECT COUNT(*) as total_proteins FROM dim_proteins").fetchone()
    terminator_stats = conn.execute("SELECT COUNT(*) as total_terminators FROM dim_terminators").fetchone()
    
    conn.close()
    
    logging.info(f"✅ Database created successfully!")
    logging.info(f"   Total phages: {stats[0]:,}")
    logging.info(f"   Total proteins: {protein_stats[0]:,}")
    logging.info(f"   Total terminators: {terminator_stats[0]:,}")

if __name__ == "__main__":
    create_star_schema_duckdb()
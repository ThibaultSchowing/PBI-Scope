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
    anti_crispr_data = snakemake.input.anti_crispr_data
    virulent_factor_data = snakemake.input.virulent_factor_data
    transmembrane_data = snakemake.input.transmembrane_data
    trna_tmrna_data = snakemake.input.trna_tmrna_data
    db_path = snakemake.output.db
    
    # Create output directory
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    logging.info(f"Creating DuckDB database at {db_path}")
    
    conn = duckdb.connect(db_path)
    
    # 1. CREATE FACT TABLE - PHAGES
    logging.info("Creating fact_phages table")
    conn.execute(f"""
    CREATE TABLE fact_phages AS 
    SELECT 
        Phage_ID,
        Source_DB,
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
    
    phage_count = conn.execute("SELECT COUNT(*) FROM fact_phages").fetchone()[0]
    logging.info(f"✅ Created fact_phages: {phage_count:,} rows")
    
    # 2. CREATE DIM_PROTEINS TABLE
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
        Source_DB
    FROM read_csv('{protein_data}', 
                  header=true, 
                  all_varchar=true, 
                  ignore_errors=true,
                  null_padding=true)
    WHERE Protein_ID IS NOT NULL AND Phage_ID IS NOT NULL
    """)
    
    protein_count = conn.execute("SELECT COUNT(*) FROM dim_proteins").fetchone()[0]
    logging.info(f"✅ Created dim_proteins: {protein_count:,} rows")
    
    # 3. CREATE DIM_TERMINATORS TABLE
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
        Source_DB
    FROM read_csv('{terminator_data}', 
                  header=true, 
                  all_varchar=true, 
                  ignore_errors=true,
                  null_padding=true)
    WHERE Phage_ID IS NOT NULL
    """)
    
    terminator_count = conn.execute("SELECT COUNT(*) FROM dim_terminators").fetchone()[0]
    logging.info(f"✅ Created dim_terminators: {terminator_count:,} rows")

    # 4. CREATE DIM_ANTI_CRISPR TABLE
    logging.info("Creating dim_anti_crispr table")
    conn.execute(f"""
    CREATE TABLE dim_anti_crispr AS 
    SELECT 
        Phage_ID,
        Protein_ID,
        Source,
        Phage_source,
        Source_DB
    FROM read_csv_auto('{anti_crispr_data}')
    WHERE Phage_ID IS NOT NULL
    """)
    
    anti_crispr_count = conn.execute("SELECT COUNT(*) FROM dim_anti_crispr").fetchone()[0]
    logging.info(f"✅ Created dim_anti_crispr: {anti_crispr_count:,} rows")
    
    # 5. CREATE DIM_VIRULENT_FACTORS TABLE
    # Columns: Protein_ID, Aligned_Protein_in_VFDB, Phage_ID, Phage_source, Source_DB
    logging.info("Creating dim_virulent_factors table")
    conn.execute(f"""
    CREATE TABLE dim_virulent_factors AS 
    SELECT 
        Phage_ID,
        Protein_ID,
        Aligned_Protein_in_VFDB as aligned_protein_vfdb,
        Phage_source,
        Source_DB
    FROM read_csv_auto('{virulent_factor_data}')
    WHERE Phage_ID IS NOT NULL
    """)
    
    virulent_count = conn.execute("SELECT COUNT(*) FROM dim_virulent_factors").fetchone()[0]
    logging.info(f"✅ Created dim_virulent_factors: {virulent_count:,} rows")
    
    # 6. CREATE DIM_TRANSMEMBRANE_PROTEINS TABLE
    # Columns: Phage_ID, Protein_ID, Length, PredictedTMHsNumber, ExpnumberofAAsinTMHs, 
    #          Expnumberfirst60AAs, TotalprobofNin, POSSIBLENterm, Insidesource, Insidestart, 
    #          Insideend, TMhelixsource, TMhelixstart, TMhelixend, Outsidesource, 
    #          Outsidestart, Outsideend, Source_DB
    logging.info("Creating dim_transmembrane_proteins table")
    conn.execute(f"""
    CREATE TABLE dim_transmembrane_proteins AS 
    SELECT 
        Phage_ID,
        Protein_ID,
        TRY_CAST(NULLIF(Length, '-') AS INTEGER) as protein_length,
        TRY_CAST(NULLIF(PredictedTMHsNumber, '-') AS INTEGER) as predicted_tmhs_number,
        TRY_CAST(NULLIF(ExpnumberofAAsinTMHs, '-') AS DOUBLE) as exp_aa_in_tmhs,
        TRY_CAST(NULLIF(Expnumberfirst60AAs, '-') AS DOUBLE) as exp_first_60_aa,
        TRY_CAST(NULLIF(TotalprobofNin, '-') AS DOUBLE) as total_prob_n_in,
        POSSIBLENterm as possible_n_term,
        Insidesource as inside_source,
        TRY_CAST(NULLIF(Insidestart, '-') AS INTEGER) as inside_start,
        TRY_CAST(NULLIF(Insideend, '-') AS INTEGER) as inside_end,
        TMhelixsource as tm_helix_source,
        TRY_CAST(NULLIF(TMhelixstart, '-') AS INTEGER) as tm_helix_start,
        TRY_CAST(NULLIF(TMhelixend, '-') AS INTEGER) as tm_helix_end,
        Outsidesource as outside_source,
        TRY_CAST(NULLIF(Outsidestart, '-') AS INTEGER) as outside_start,
        TRY_CAST(NULLIF(Outsideend, '-') AS INTEGER) as outside_end,
        Source_DB
    FROM read_csv('{transmembrane_data}',
                  header=true,
                  all_varchar=true,
                  ignore_errors=true,
                  null_padding=true)
    WHERE Phage_ID IS NOT NULL
    """)
    
    transmembrane_count = conn.execute("SELECT COUNT(*) FROM dim_transmembrane_proteins").fetchone()[0]
    logging.info(f"✅ Created dim_transmembrane_proteins: {transmembrane_count:,} rows")
    
    # 7. CREATE DIM_TRNA_TMRNA TABLE
    # Columns: t(m)RNA_ID, Source, t(m)RNA, Start, Stop, Strand, Length, Permuted, 
    #          Sequence, Phage_ID, Phage_source, Source_DB
    logging.info("Creating dim_trna_tmrna table")
    conn.execute(f"""
    CREATE TABLE dim_trna_tmrna AS 
    SELECT 
        Phage_ID,
        "t(m)RNA_ID" as trna_tmrna_id,
        Source as source,
        "t(m)RNA" as trna_type,
        TRY_CAST(NULLIF(Start, '-') AS INTEGER) as start_pos,
        TRY_CAST(NULLIF(Stop, '-') AS INTEGER) as stop_pos,
        Strand,
        TRY_CAST(NULLIF(Length, '-') AS INTEGER) as length,
        Permuted as permuted,
        Sequence as sequence,
        Phage_source,
        Source_DB
    FROM read_csv('{trna_tmrna_data}',
                  header=true,
                  all_varchar=true,
                  ignore_errors=true,
                  null_padding=true)
    WHERE Phage_ID IS NOT NULL
    """)
    
    trna_count = conn.execute("SELECT COUNT(*) FROM dim_trna_tmrna").fetchone()[0]
    logging.info(f"✅ Created dim_trna_tmrna: {trna_count:,} rows")
    
    # CREATE PERFORMANCE INDEXES
    logging.info("Creating indexes")
    conn.execute("CREATE INDEX idx_phages_id ON fact_phages(Phage_ID)")
    conn.execute("CREATE INDEX idx_phages_source ON fact_phages(Source_DB)")
    
    conn.execute("CREATE INDEX idx_proteins_phage ON dim_proteins(Phage_ID)")
    conn.execute("CREATE INDEX idx_proteins_source ON dim_proteins(Source_DB)")
    
    conn.execute("CREATE INDEX idx_terminators_phage ON dim_terminators(Phage_ID)")
    conn.execute("CREATE INDEX idx_terminators_source ON dim_terminators(Source_DB)")
    
    conn.execute("CREATE INDEX idx_anti_crispr_phage ON dim_anti_crispr(Phage_ID)")
    conn.execute("CREATE INDEX idx_anti_crispr_source ON dim_anti_crispr(Source_DB)")
    
    conn.execute("CREATE INDEX idx_virulent_phage ON dim_virulent_factors(Phage_ID)")
    conn.execute("CREATE INDEX idx_virulent_source ON dim_virulent_factors(Source_DB)")
    
    conn.execute("CREATE INDEX idx_transmembrane_phage ON dim_transmembrane_proteins(Phage_ID)")
    conn.execute("CREATE INDEX idx_transmembrane_source ON dim_transmembrane_proteins(Source_DB)")
    
    conn.execute("CREATE INDEX idx_trna_phage ON dim_trna_tmrna(Phage_ID)")
    conn.execute("CREATE INDEX idx_trna_source ON dim_trna_tmrna(Source_DB)")
    
    # CREATE ANALYTICAL VIEWS
    logging.info("Creating analytical views")
    conn.execute("""
    CREATE VIEW phage_summary AS
    SELECT 
        Source_DB,
        COUNT(*) as total_phages,
        AVG(Length) as avg_length,
        AVG(GC_content) as avg_gc_content,
        MIN(Length) as min_length,
        MAX(Length) as max_length
    FROM fact_phages
    WHERE Length IS NOT NULL AND GC_content IS NOT NULL
    GROUP BY Source_DB
    ORDER BY total_phages DESC
    """)
    
    conn.execute("""
    CREATE VIEW phage_size_distribution AS
    SELECT 
        Source_DB,
        CASE 
            WHEN Length < 10000 THEN 'Small (<10kb)'
            WHEN Length < 100000 THEN 'Medium (10-100kb)'
            ELSE 'Large (>100kb)'
        END as size_category,
        COUNT(*) as count,
        AVG(Length) as avg_length
    FROM fact_phages
    WHERE Length IS NOT NULL
    GROUP BY Source_DB, size_category
    """)
    
    # CREATE COMPREHENSIVE PHAGE VIEW
    conn.execute("""
    CREATE VIEW phage_complete_profile AS
    SELECT 
        f.Phage_ID,
        f.Source_DB,
        f.Length,
        f.GC_content,
        f.Host,
        f.Lifestyle,
        COUNT(DISTINCT p.Protein_ID) as protein_count,
        COUNT(DISTINCT t.terminator_type) as terminator_types,
        COUNT(DISTINCT a.Protein_ID) as anti_crispr_count,
        COUNT(DISTINCT v.Protein_ID) as virulent_factor_count,
        COUNT(DISTINCT tm.Protein_ID) as transmembrane_protein_count,
        COUNT(DISTINCT tr.trna_tmrna_id) as trna_tmrna_count
    FROM fact_phages f
    LEFT JOIN dim_proteins p ON f.Phage_ID = p.Phage_ID
    LEFT JOIN dim_terminators t ON f.Phage_ID = t.Phage_ID
    LEFT JOIN dim_anti_crispr a ON f.Phage_ID = a.Phage_ID
    LEFT JOIN dim_virulent_factors v ON f.Phage_ID = v.Phage_ID
    LEFT JOIN dim_transmembrane_proteins tm ON f.Phage_ID = tm.Phage_ID
    LEFT JOIN dim_trna_tmrna tr ON f.Phage_ID = tr.Phage_ID
    GROUP BY f.Phage_ID, f.Source_DB, f.Length, f.GC_content, f.Host, f.Lifestyle
    """)
    
    conn.close()
    
    logging.info(f"✅ Database created successfully!")
    logging.info(f"   📊 Summary Statistics:")
    logging.info(f"   • Phages: {phage_count:,}")
    logging.info(f"   • Proteins: {protein_count:,}")
    logging.info(f"   • Terminators: {terminator_count:,}")
    logging.info(f"   • Anti-CRISPR: {anti_crispr_count:,}")
    logging.info(f"   • Virulent Factors: {virulent_count:,}")
    logging.info(f"   • Transmembrane Proteins: {transmembrane_count:,}")
    logging.info(f"   • tRNA/tmRNA: {trna_count:,}")

if __name__ == "__main__":
    create_star_schema_duckdb()
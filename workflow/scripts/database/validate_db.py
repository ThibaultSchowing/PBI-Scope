#!/usr/bin/env python

import duckdb
import os
import logging
import sys
from datetime import datetime
import json
import html

logging.basicConfig(level=logging.INFO)

def validate_database():
    """Validate the DuckDB database and generate an HTML report"""
    
    # Get inputs and outputs from Snakemake
    db_path = snakemake.input.db
    report_path = snakemake.output.report
    
    # Create output directory
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    logging.info(f"Validating database: {db_path}")
    logging.info(f"Report will be saved to: {report_path}")
    
    # Connect to database
    conn = duckdb.connect(db_path, read_only=True)
    
    # Collect validation results
    validation_results = {
        'timestamp': datetime.now().isoformat(),
        'database_path': db_path,
        'tables': {},
        'data_quality': {},
        'provenance': {},
        'summary': {}
    }
    
    try:
        # 1. Check tables exist
        logging.info("Checking table existence...")
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [table[0] for table in tables]
        
        expected_tables = [
            'fact_phages', 
            'dim_proteins', 
            'dim_terminators', 
            'dim_anti_crispr',
            'dim_virulent_factors',
            'dim_transmembrane_proteins',
            'dim_trna_tmrna',
            'dim_crispr_arrays',
            'dim_antimicrobial_resistance_genes'  # Changed from dim_antimicrobial_resistance
        ]
        
        # Optional tables (may not exist on first run)
        optional_tables = ['dim_hosts', 'dim_assembly_metadata', 'dim_phage_host_links']
        
        missing_tables = [t for t in expected_tables if t not in table_names]
        missing_optional = [t for t in optional_tables if t not in table_names]
        
        validation_results['tables']['existing'] = table_names
        validation_results['tables']['missing'] = missing_tables
        validation_results['tables']['missing_optional'] = missing_optional
        validation_results['tables']['all_present'] = len(missing_tables) == 0
        
        # Log optional tables status
        if missing_optional:
            logging.info(f"⚠️  Optional tables not present (expected on first run): {missing_optional}")
        
        # 2. Check table schemas and row counts
        all_tables_to_check = expected_tables + optional_tables
        for table in all_tables_to_check:
            if table in table_names:
                logging.info(f"Analyzing table: {table}")
                
                # Get schema
                schema = conn.execute(f"DESCRIBE {table}").fetchall()
                
                # Get row count
                row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                
                # Get null counts for each column
                null_counts = {}
                for col_info in schema:
                    col_name = col_info[0]
                    try:
                        null_count = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE "{col_name}" IS NULL').fetchone()[0]
                        null_counts[col_name] = null_count
                    except:
                        null_counts[col_name] = 0
                
                validation_results['tables'][table] = {
                    'schema': schema,
                    'row_count': row_count,
                    'null_counts': null_counts
                }
        
        # 3. Data quality checks
        logging.info("Performing data quality checks...")
        
        # FACT_PHAGES validation
        if 'fact_phages' in table_names:
            duplicate_phages = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Phage_ID, COUNT(*) as cnt 
                    FROM fact_phages 
                    GROUP BY Phage_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            length_stats = conn.execute("""
                SELECT MIN(Length), MAX(Length), AVG(Length), COUNT(Length)
                FROM fact_phages 
                WHERE Length IS NOT NULL
            """).fetchone()
            
            source_distribution = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM fact_phages 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            validation_results['data_quality']['fact_phages'] = {
                'duplicate_phage_ids': duplicate_phages,
                'length_stats': {
                    'min': length_stats[0],
                    'max': length_stats[1], 
                    'avg': round(length_stats[2], 2) if length_stats[2] else None,
                    'count': length_stats[3]
                },
                'source_distribution': dict(source_distribution)
            }
        
        # DIM_PROTEINS validation
        if 'dim_proteins' in table_names:
            orphaned_proteins = conn.execute("""
                SELECT COUNT(*) FROM dim_proteins p
                LEFT JOIN fact_phages f ON p.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            duplicate_proteins = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Protein_ID, COUNT(*) as cnt 
                    FROM dim_proteins 
                    GROUP BY Protein_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            protein_sources = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_proteins 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            validation_results['data_quality']['dim_proteins'] = {
                'orphaned_proteins': orphaned_proteins,
                'duplicate_protein_ids': duplicate_proteins,
                'source_distribution': dict(protein_sources)
            }
        
        # DIM_TERMINATORS validation
        if 'dim_terminators' in table_names:
            orphaned_terminators = conn.execute("""
                SELECT COUNT(*) FROM dim_terminators t
                LEFT JOIN fact_phages f ON t.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            terminator_types = conn.execute("""
                SELECT terminator_type, COUNT(*) as count
                FROM dim_terminators 
                WHERE terminator_type IS NOT NULL
                GROUP BY terminator_type 
                ORDER BY count DESC
            """).fetchall()
            
            terminator_sources = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_terminators 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            validation_results['data_quality']['dim_terminators'] = {
                'orphaned_terminators': orphaned_terminators,
                'terminator_type_distribution': dict(terminator_types),
                'source_distribution': dict(terminator_sources)
            }
        
        # DIM_ANTI_CRISPR validation
        if 'dim_anti_crispr' in table_names:
            orphaned_anti_crispr = conn.execute("""
                SELECT COUNT(*) FROM dim_anti_crispr a
                LEFT JOIN fact_phages f ON a.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            duplicate_acr = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Protein_ID, COUNT(*) as cnt 
                    FROM dim_anti_crispr 
                    WHERE Protein_ID IS NOT NULL
                    GROUP BY Protein_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            acr_source_db = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_anti_crispr 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            acr_source_type = conn.execute("""
                SELECT Source, COUNT(*) as count
                FROM dim_anti_crispr 
                WHERE Source IS NOT NULL
                GROUP BY Source 
                ORDER BY count DESC
            """).fetchall()
            
            validation_results['data_quality']['dim_anti_crispr'] = {
                'orphaned_anti_crispr': orphaned_anti_crispr,
                'duplicate_protein_ids': duplicate_acr,
                'source_db_distribution': dict(acr_source_db),
                'source_type_distribution': dict(acr_source_type)
            }
        
        # DIM_VIRULENT_FACTORS validation
        if 'dim_virulent_factors' in table_names:
            orphaned_virulent = conn.execute("""
                SELECT COUNT(*) FROM dim_virulent_factors v
                LEFT JOIN fact_phages f ON v.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            duplicate_vf = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Protein_ID, COUNT(*) as cnt 
                    FROM dim_virulent_factors 
                    WHERE Protein_ID IS NOT NULL
                    GROUP BY Protein_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            vf_sources = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_virulent_factors 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            # Distribution of aligned proteins
            vf_aligned = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(DISTINCT aligned_protein_vfdb) as unique_vfdb_proteins
                FROM dim_virulent_factors 
                WHERE aligned_protein_vfdb IS NOT NULL
            """).fetchone()
            
            validation_results['data_quality']['dim_virulent_factors'] = {
                'orphaned_virulent_factors': orphaned_virulent,
                'duplicate_protein_ids': duplicate_vf,
                'source_distribution': dict(vf_sources),
                'vfdb_alignment_stats': {
                    'total_aligned': vf_aligned[0],
                    'unique_vfdb_proteins': vf_aligned[1]
                }
            }
        
        # DIM_TRANSMEMBRANE_PROTEINS validation
        if 'dim_transmembrane_proteins' in table_names:
            orphaned_transmembrane = conn.execute("""
                SELECT COUNT(*) FROM dim_transmembrane_proteins tm
                LEFT JOIN fact_phages f ON tm.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            duplicate_tm = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Protein_ID, COUNT(*) as cnt 
                    FROM dim_transmembrane_proteins 
                    WHERE Protein_ID IS NOT NULL
                    GROUP BY Protein_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            tmh_stats = conn.execute("""
                SELECT 
                    AVG(predicted_tmhs_number) as avg_tmhs,
                    MIN(predicted_tmhs_number) as min_tmhs,
                    MAX(predicted_tmhs_number) as max_tmhs,
                    COUNT(predicted_tmhs_number) as count_with_tmhs
                FROM dim_transmembrane_proteins 
                WHERE predicted_tmhs_number IS NOT NULL
            """).fetchone()
            
            tm_sources = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_transmembrane_proteins 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            # Distribution of TMH counts
            tmh_distribution = conn.execute("""
                SELECT predicted_tmhs_number, COUNT(*) as count
                FROM dim_transmembrane_proteins 
                WHERE predicted_tmhs_number IS NOT NULL
                GROUP BY predicted_tmhs_number 
                ORDER BY predicted_tmhs_number
            """).fetchall()
            
            validation_results['data_quality']['dim_transmembrane_proteins'] = {
                'orphaned_transmembrane': orphaned_transmembrane,
                'duplicate_protein_ids': duplicate_tm,
                'tmh_stats': {
                    'avg': round(tmh_stats[0], 2) if tmh_stats[0] else None,
                    'min': tmh_stats[1],
                    'max': tmh_stats[2],
                    'count': tmh_stats[3]
                },
                'source_distribution': dict(tm_sources),
                'tmh_distribution': dict(tmh_distribution)
            }
        
        # DIM_TRNA_TMRNA validation
        if 'dim_trna_tmrna' in table_names:
            orphaned_trna = conn.execute("""
                SELECT COUNT(*) FROM dim_trna_tmrna tr
                LEFT JOIN fact_phages f ON tr.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            duplicate_trna = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT trna_tmrna_id, COUNT(*) as cnt 
                    FROM dim_trna_tmrna 
                    WHERE trna_tmrna_id IS NOT NULL
                    GROUP BY trna_tmrna_id 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            trna_types = conn.execute("""
                SELECT trna_type, COUNT(*) as count
                FROM dim_trna_tmrna 
                WHERE trna_type IS NOT NULL
                GROUP BY trna_type 
                ORDER BY count DESC
                LIMIT 20
            """).fetchall()
            
            trna_sources = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_trna_tmrna 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            # Strand distribution
            strand_distribution = conn.execute("""
                SELECT Strand, COUNT(*) as count
                FROM dim_trna_tmrna 
                WHERE Strand IS NOT NULL
                GROUP BY Strand 
                ORDER BY count DESC
            """).fetchall()
            
            # Permuted status
            permuted_stats = conn.execute("""
                SELECT permuted, COUNT(*) as count
                FROM dim_trna_tmrna 
                WHERE permuted IS NOT NULL
                GROUP BY permuted 
                ORDER BY count DESC
            """).fetchall()
            
            validation_results['data_quality']['dim_trna_tmrna'] = {
                'orphaned_trna': orphaned_trna,
                'duplicate_trna_ids': duplicate_trna,
                'type_distribution': dict(trna_types),
                'source_distribution': dict(trna_sources),
                'strand_distribution': dict(strand_distribution),
                'permuted_distribution': dict(permuted_stats)
            }
        
        # DIM_CRISPR_ARRAYS validation
        if 'dim_crispr_arrays' in table_names:
            orphaned_crispr = conn.execute("""
                SELECT COUNT(*) FROM dim_crispr_arrays ca
                LEFT JOIN fact_phages f ON ca.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            duplicate_crispr = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT crispr_id, COUNT(*) as cnt 
                    FROM dim_crispr_arrays 
                    WHERE crispr_id IS NOT NULL
                    GROUP BY crispr_id 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            crispr_sources = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_crispr_arrays 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            validation_results['data_quality']['dim_crispr_arrays'] = {
                'orphaned_crispr_arrays': orphaned_crispr,
                'duplicate_crispr_ids': duplicate_crispr,
                'source_distribution': dict(crispr_sources)
            }
        
        # DIM_ANTIMICROBIAL_RESISTANCE_GENES validation
        if 'dim_antimicrobial_resistance_genes' in table_names:  # Changed table name
            logging.info("Validating dim_antimicrobial_resistance_genes table...")
            
            # Debug: Check actual row count
            actual_count = conn.execute("SELECT COUNT(*) FROM dim_antimicrobial_resistance_genes").fetchone()[0]
            logging.info(f"dim_antimicrobial_resistance_genes actual row count: {actual_count}")
            
            orphaned_amr = conn.execute("""
                SELECT COUNT(*) FROM dim_antimicrobial_resistance_genes amr
                LEFT JOIN fact_phages f ON amr.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            logging.info(f"Orphaned AMR entries: {orphaned_amr}")
            
            duplicate_amr = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Protein_ID, COUNT(*) as cnt 
                    FROM dim_antimicrobial_resistance_genes 
                    WHERE Protein_ID IS NOT NULL
                    GROUP BY Protein_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            logging.info(f"Duplicate AMR Protein IDs: {duplicate_amr}")
            
            amr_sources = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_antimicrobial_resistance_genes 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            logging.info(f"AMR source distribution: {dict(amr_sources)}")
            
            validation_results['data_quality']['dim_antimicrobial_resistance_genes'] = {
                'orphaned_amr': orphaned_amr,
                'duplicate_protein_ids': duplicate_amr,
                'source_distribution': dict(amr_sources)
            }
        else:
            logging.warning("dim_antimicrobial_resistance_genes table not found in database!")
        
        # DIM_HOSTS validation (optional table)
        if 'dim_hosts' in table_names:
            logging.info("Validating dim_hosts table...")
            
            # Check for duplicate host IDs
            duplicate_hosts = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Host_ID, COUNT(*) as cnt 
                    FROM dim_hosts 
                    WHERE Host_ID IS NOT NULL
                    GROUP BY Host_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            logging.info(f"Duplicate Host IDs: {duplicate_hosts}")
            
            # Check species distribution
            species_distribution = conn.execute("""
                SELECT Species_Name, COUNT(*) as count
                FROM dim_hosts 
                GROUP BY Species_Name 
                ORDER BY count DESC
                LIMIT 10
            """).fetchall()
            logging.info(f"Top 10 host species: {dict(species_distribution)}")
            
            # Assembly level distribution
            assembly_levels = conn.execute("""
                SELECT Assembly_Level, COUNT(*) as count
                FROM dim_hosts 
                WHERE Assembly_Level IS NOT NULL
                GROUP BY Assembly_Level 
                ORDER BY count DESC
            """).fetchall()
            logging.info(f"Assembly level distribution: {dict(assembly_levels)}")
            
            # RefSeq category distribution
            refseq_categories = conn.execute("""
                SELECT RefSeq_Category, COUNT(*) as count
                FROM dim_hosts 
                WHERE RefSeq_Category IS NOT NULL
                GROUP BY RefSeq_Category 
                ORDER BY count DESC
            """).fetchall()
            logging.info(f"RefSeq category distribution: {dict(refseq_categories)}")
            
            # Genome statistics
            genome_stats = conn.execute("""
                SELECT 
                    AVG(Genome_Length) as avg_length,
                    MIN(Genome_Length) as min_length,
                    MAX(Genome_Length) as max_length,
                    AVG(GC_Content) as avg_gc,
                    MIN(GC_Content) as min_gc,
                    MAX(GC_Content) as max_gc
                FROM dim_hosts
                WHERE Genome_Length IS NOT NULL AND GC_Content IS NOT NULL
            """).fetchone()
            
            validation_results['data_quality']['dim_hosts'] = {
                'duplicate_host_ids': duplicate_hosts,
                'species_distribution': dict(species_distribution),
                'assembly_level_distribution': dict(assembly_levels),
                'refseq_category_distribution': dict(refseq_categories),
                'genome_statistics': {
                    'avg_length': genome_stats[0],
                    'min_length': genome_stats[1],
                    'max_length': genome_stats[2],
                    'avg_gc_content': genome_stats[3],
                    'min_gc_content': genome_stats[4],
                    'max_gc_content': genome_stats[5]
                } if genome_stats else {}
            }
        else:
            logging.info("⚠️  dim_hosts table not present (expected if host genomes haven't been downloaded yet)")
        
        # 4. Collect private data statistics (optional tables)
        logging.info("Collecting private data statistics...")
        private_data = {}
        for priv_table in ('private_interactions', 'private_phage_host_associations', 'private_entity_attributes'):
            if priv_table in table_names:
                row_count = conn.execute(f"SELECT COUNT(*) FROM {priv_table}").fetchone()[0]
                private_data[priv_table] = {'row_count': row_count}

        if 'private_interactions' in private_data:
            per_source = conn.execute("""
                SELECT Source_DB, COUNT(*) as cnt
                FROM private_interactions
                GROUP BY Source_DB ORDER BY cnt DESC
            """).fetchall()
            private_data['private_interactions']['per_source'] = dict(per_source)

            lifestyle_dist = conn.execute("""
                SELECT interaction, COUNT(*) as cnt
                FROM private_interactions
                GROUP BY interaction ORDER BY cnt DESC
            """).fetchall()
            private_data['private_interactions']['lifestyle_distribution'] = dict(lifestyle_dist)

        if 'fact_phages' in table_names:
            priv_phage_count = conn.execute(
                "SELECT COUNT(*) FROM fact_phages WHERE source_type = 'private'"
            ).fetchone()[0]
            private_data['private_phage_count'] = priv_phage_count

        if 'dim_hosts' in table_names:
            priv_host_count = conn.execute(
                "SELECT COUNT(*) FROM dim_hosts WHERE source_type = 'private'"
            ).fetchone()[0]
            private_data['private_host_count'] = priv_host_count

        validation_results['private_data'] = private_data

        # 5. Collect provider/version provenance metadata (optional tables)
        logging.info("Collecting provenance/version metadata...")
        provenance = {
            'pipeline_run': {},
            'dataset_provenance': {}
        }

        if 'pipeline_run_provenance' in table_names:
            run_rows = conn.execute(
                """
                SELECT *
                FROM pipeline_run_provenance
                ORDER BY pipeline_run_timestamp DESC
                LIMIT 1
                """
            ).fetchall()
            run_schema = conn.execute("DESCRIBE pipeline_run_provenance").fetchall()
            run_columns = [col[0] for col in run_schema]
            if run_rows:
                provenance['pipeline_run'] = {
                    key: run_rows[0][idx]
                    for idx, key in enumerate(run_columns)
                }

        if 'dataset_provenance' in table_names:
            dataset_count = conn.execute("SELECT COUNT(*) FROM dataset_provenance").fetchone()[0]
            status_distribution = conn.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(status), ''), 'unknown') as status_label, COUNT(*) as cnt
                FROM dataset_provenance
                GROUP BY status_label
                ORDER BY cnt DESC
                """
            ).fetchall()

            failed_rows = conn.execute(
                """
                SELECT COUNT(*)
                FROM dataset_provenance
                WHERE COALESCE(NULLIF(TRIM(status), ''), 'unknown') NOT IN ('success')
                """
            ).fetchone()[0]

            provider_releases = conn.execute(
                """
                SELECT DISTINCT provider_release
                FROM dataset_provenance
                WHERE provider_release IS NOT NULL AND TRIM(provider_release) <> ''
                ORDER BY provider_release
                """
            ).fetchall()

            provider_snapshots = conn.execute(
                """
                SELECT DISTINCT provider_snapshot_date
                FROM dataset_provenance
                WHERE provider_snapshot_date IS NOT NULL AND TRIM(provider_snapshot_date) <> ''
                ORDER BY provider_snapshot_date
                """
            ).fetchall()

            provider_schemas = conn.execute(
                """
                SELECT DISTINCT provider_schema_profile
                FROM dataset_provenance
                WHERE provider_schema_profile IS NOT NULL AND TRIM(provider_schema_profile) <> ''
                ORDER BY provider_schema_profile
                """
            ).fetchall()

            provenance['dataset_provenance'] = {
                'row_count': dataset_count,
                'status_distribution': dict(status_distribution),
                'non_success_rows': failed_rows,
                'provider_releases': [row[0] for row in provider_releases],
                'provider_snapshot_dates': [row[0] for row in provider_snapshots],
                'provider_schema_profiles': [row[0] for row in provider_schemas],
            }

        validation_results['provenance'] = provenance

        # 6. Check indexes exist
        logging.info("Checking indexes...")
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        validation_results['indexes'] = [idx[0] for idx in indexes]
        
        # 7. Check views exist
        logging.info("Checking views...")
        views = conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
        validation_results['views'] = [view[0] for view in views]
        
        # 8. Overall summary
        total_phages = validation_results['tables'].get('fact_phages', {}).get('row_count', 0)
        total_proteins = validation_results['tables'].get('dim_proteins', {}).get('row_count', 0)
        total_terminators = validation_results['tables'].get('dim_terminators', {}).get('row_count', 0)
        total_anti_crispr = validation_results['tables'].get('dim_anti_crispr', {}).get('row_count', 0)
        total_virulent = validation_results['tables'].get('dim_virulent_factors', {}).get('row_count', 0)
        total_transmembrane = validation_results['tables'].get('dim_transmembrane_proteins', {}).get('row_count', 0)
        total_trna = validation_results['tables'].get('dim_trna_tmrna', {}).get('row_count', 0)
        total_crispr = validation_results['tables'].get('dim_crispr_arrays', {}).get('row_count', 0)
        total_amr = validation_results['tables'].get('dim_antimicrobial_resistance_genes', {}).get('row_count', 0)
        total_hosts = validation_results['tables'].get('dim_hosts', {}).get('row_count', 0)
        
        # Debug logging
        logging.info(f"Summary - AMR count from validation_results: {total_amr}")

        # Calculate overall data quality
        data_quality_passed = True
        if 'fact_phages' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['fact_phages'].get('duplicate_phage_ids', 0) == 0
        if 'dim_proteins' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_proteins'].get('orphaned_proteins', 0) == 0
        if 'dim_terminators' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_terminators'].get('orphaned_terminators', 0) == 0
        if 'dim_anti_crispr' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_anti_crispr'].get('orphaned_anti_crispr', 0) == 0
        if 'dim_virulent_factors' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_virulent_factors'].get('orphaned_virulent_factors', 0) == 0
        if 'dim_transmembrane_proteins' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_transmembrane_proteins'].get('orphaned_transmembrane', 0) == 0
        if 'dim_trna_tmrna' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_trna_tmrna'].get('orphaned_trna', 0) == 0
        if 'dim_crispr_arrays' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_crispr_arrays'].get('orphaned_crispr_arrays', 0) == 0
        if 'dim_antimicrobial_resistance_genes' in validation_results['data_quality']:
            data_quality_passed &= validation_results['data_quality']['dim_antimicrobial_resistance_genes'].get('orphaned_amr', 0) == 0
        
        validation_results['summary'] = {
            'total_phages': total_phages,
            'total_proteins': total_proteins,
            'total_terminators': total_terminators,
            'total_anti_crispr': total_anti_crispr,
            'total_virulent_factors': total_virulent,
            'total_transmembrane_proteins': total_transmembrane,
            'total_trna_tmrna': total_trna,
            'total_crispr_arrays': total_crispr,
            'total_amr': total_amr,
            'total_hosts': total_hosts,
            'all_tables_present': validation_results['tables']['all_present'],
            'data_quality_passed': data_quality_passed
        }
        
    except Exception as e:
        logging.error(f"Error during validation: {str(e)}")
        validation_results['error'] = str(e)
        raise
    
    finally:
        conn.close()
    
    # Generate HTML report
    generate_html_report(validation_results, report_path)
    
    logging.info(f"✅ Validation complete! Report saved to: {report_path}")

def generate_html_report(results, report_path):
    """Generate an HTML validation report with visual database overview"""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PhageScope Database Validation Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f9f9f9; }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; }}
            .section {{ margin: 20px 0; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .success {{ color: #28a745; font-weight: bold; }}
            .warning {{ color: #ffc107; font-weight: bold; }}
            .error {{ color: #dc3545; font-weight: bold; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f8f9fa; font-weight: bold; }}
            .metric {{ font-size: 24px; font-weight: bold; text-align: center; color: #495057; }}
            .metric-label {{ font-size: 12px; color: #6c757d; margin-top: 5px; }}
            
            /* Database Schema Visualization */
            .schema-container {{ 
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin: 20px 0;
            }}
            .schema-center {{ 
                grid-column: 2;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 15px;
            }}
            .schema-left {{ 
                display: flex;
                flex-direction: column;
                gap: 15px;
            }}
            .schema-right {{ 
                display: flex;
                flex-direction: column;
                gap: 15px;
            }}
            .table-box {{ 
                border: 2px solid #007bff; 
                border-radius: 8px; 
                padding: 15px; 
                background: #f8f9ff; 
                text-align: center; 
                min-width: 180px;
            }}
            .table-box.central {{ 
                border-color: #28a745; 
                background: #f0fff4;
                font-size: 1.1em;
                min-width: 200px;
            }}
            .table-name {{ font-weight: bold; color: #007bff; font-size: 16px; margin-bottom: 10px; }}
            .table-name.central {{ color: #28a745; }}
            .table-info {{ font-size: 12px; color: #6c757d; }}
            
            /* Statistics Cards */
            .stats-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                gap: 15px; 
            }}
            .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #007bff; }}
            .stat-title {{ font-weight: bold; color: #495057; margin-bottom: 10px; }}
            .stat-value {{ font-size: 24px; color: #007bff; }}
            
            /* Source Distribution Chart */
            .chart-container {{ margin: 20px 0; }}
            .bar {{ display: flex; align-items: center; margin: 5px 0; }}
            .bar-label {{ min-width: 120px; font-size: 12px; }}
            .bar-fill {{ height: 20px; background: #007bff; margin: 0 10px; border-radius: 3px; }}
            .bar-value {{ font-size: 12px; color: #495057; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🧬 PhageScope Database Validation Report</h1>
            <p><strong>Generated:</strong> {results['timestamp']}</p>
            <p><strong>Database:</strong> {results['database_path']}</p>
        </div>
        
        <div class="section">
            <h2>📊 Database Overview</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-title">Phages</div>
                    <div class="stat-value">{results['summary']['total_phages']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Proteins</div>
                    <div class="stat-value">{results['summary']['total_proteins']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Terminators</div>
                    <div class="stat-value">{results['summary']['total_terminators']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Anti-CRISPR</div>
                    <div class="stat-value">{results['summary']['total_anti_crispr']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Virulent Factors</div>
                    <div class="stat-value">{results['summary']['total_virulent_factors']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Transmembrane</div>
                    <div class="stat-value">{results['summary']['total_transmembrane_proteins']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">tRNA/tmRNA</div>
                    <div class="stat-value">{results['summary']['total_trna_tmrna']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">CRISPR Arrays</div>
                    <div class="stat-value">{results['summary']['total_crispr_arrays']:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">AMR Genes</div>
                    <div class="stat-value">{results['summary']['total_amr']:,}</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>🗂️ Database Schema & Relationships</h2>
            <p style="text-align: center; color: #6c757d; margin-bottom: 20px;">
                All dimension tables are linked to fact_phages via <strong>Phage_ID</strong>
            </p>
            <div class="schema-container">
                <div class="schema-left">
                    <div class="table-box">
                        <div class="table-name">dim_proteins</div>
                        <div class="table-info">
                            {results['tables'].get('dim_proteins', {}).get('row_count', 0):,} rows<br>
                            FK: Phage_ID
                        </div>
                    </div>
                    <div class="table-box">
                        <div class="table-name">dim_terminators</div>
                        <div class="table-info">
                            {results['tables'].get('dim_terminators', {}).get('row_count', 0):,} rows<br>
                            FK: Phage_ID
                        </div>
                    </div>
                </div>
                
                <div class="schema-center">
                    <div class="table-box central">
                        <div class="table-name central">fact_phages</div>
                        <div class="table-info">
                            {results['tables'].get('fact_phages', {}).get('row_count', 0):,} rows<br>
                            PK: Phage_ID
                        </div>
                    </div>
                </div>
                
                <div class="schema-right">
                    <div class="table-box">
                        <div class="table-name">dim_anti_crispr</div>
                        <div class="table-info">
                            {results['tables'].get('dim_anti_crispr', {}).get('row_count', 0):,} rows<br>
                            FK: Phage_ID
                        </div>
                    </div>
                    <div class="table-box">
                        <div class="table-name">dim_virulent_factors</div>
                        <div class="table-info">
                            {results['tables'].get('dim_virulent_factors', {}).get('row_count', 0):,} rows<br>
                            FK: Phage_ID
                        </div>
                    </div>
                    <div class="table-box">
                        <div class="table-name">dim_crispr_arrays</div>
                        <div class="table-info">
                            {results['tables'].get('dim_crispr_arrays', {}).get('row_count', 0):,} rows<br>
                            FK: Phage_ID
                        </div>
                    </div>
                </div>
            </div>
            <div class="stats-grid" style="margin-top: 20px;">
                <div class="table-box">
                    <div class="table-name">dim_transmembrane_proteins</div>
                    <div class="table-info">
                        {results['tables'].get('dim_transmembrane_proteins', {}).get('row_count', 0):,} rows<br>
                        FK: Phage_ID
                    </div>
                </div>
                <div class="table-box">
                    <div class="table-name">dim_trna_tmrna</div>
                    <div class="table-info">
                        {results['tables'].get('dim_trna_tmrna', {}).get('row_count', 0):,} rows<br>
                        FK: Phage_ID
                    </div>
                </div>
                <div class="table-box">
                    <div class="table-name">dim_antimicrobial_resistance_genes</div>
                    <div class="table-info">
                        {results['tables'].get('dim_antimicrobial_resistance_genes', {}).get('row_count', 0):,} rows<br>
                        FK: Phage_ID
                    </div>
                </div>
            </div>
        </div>
    """

    # Add provenance/version section
    provenance = results.get('provenance', {})
    run_provenance = provenance.get('pipeline_run', {}) or {}
    dataset_provenance = provenance.get('dataset_provenance', {}) or {}
    has_provenance = bool(run_provenance) or bool(dataset_provenance)

    if has_provenance:
        release_values = dataset_provenance.get('provider_releases', []) or []
        snapshot_values = dataset_provenance.get('provider_snapshot_dates', []) or []
        schema_values = dataset_provenance.get('provider_schema_profiles', []) or []
        status_distribution = dataset_provenance.get('status_distribution', {}) or {}
        non_success_rows = dataset_provenance.get('non_success_rows', 0) or 0

        html_content += f"""
        <div class="section">
            <h2>🏷️ Provider Version & Provenance</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-title">Provider Name</div>
                    <div class="stat-value" style="font-size: 20px;">{html.escape(str(run_provenance.get('provider_name', 'N/A')))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Pinned Release</div>
                    <div class="stat-value" style="font-size: 20px;">{html.escape(str(run_provenance.get('provider_release', ', '.join(release_values) if release_values else 'N/A')))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Pinned Snapshot Date</div>
                    <div class="stat-value" style="font-size: 20px;">{html.escape(str(run_provenance.get('provider_snapshot_date', ', '.join(snapshot_values) if snapshot_values else 'N/A')))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Schema Profile</div>
                    <div class="stat-value" style="font-size: 20px;">{html.escape(str(run_provenance.get('provider_schema_profile', ', '.join(schema_values) if schema_values else 'N/A')))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Provenance Mode</div>
                    <div class="stat-value" style="font-size: 20px;">{html.escape(str(run_provenance.get('provider_provenance_mode', 'N/A')))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">PBI Version</div>
                    <div class="stat-value" style="font-size: 20px;">{html.escape(str(run_provenance.get('pbi_version', 'N/A')))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Git Commit</div>
                    <div class="stat-value" style="font-size: 14px;">{html.escape(str(run_provenance.get('git_commit', 'N/A')))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Provenance Rows</div>
                    <div class="stat-value">{int(dataset_provenance.get('row_count', 0)):,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Non-success Provenance Rows</div>
                    <div class="stat-value">{int(non_success_rows):,}</div>
                </div>
            </div>
        """

        if status_distribution:
            html_content += """
            <h3 style="margin-top: 20px;">Public Data Provenance Status Distribution</h3>
            <table>
                <tr><th>Status</th><th>Count</th></tr>
            """
            for status_label, count in sorted(status_distribution.items(), key=lambda x: -x[1]):
                html_content += f"<tr><td>{html.escape(str(status_label))}</td><td>{count:,}</td></tr>"
            html_content += "</table>"

        html_content += "</div>"
    
    # Add detailed table statistics
    if results['tables']:
        html_content += """
        <div class="section">
            <h2>📋 Table Details</h2>
            <div class="stats-grid">
        """
        
        for table_name, table_data in results['tables'].items():
            if isinstance(table_data, dict) and 'row_count' in table_data:
                schema = table_data.get('schema', [])
                null_counts = table_data.get('null_counts', {})
                
                total_rows = table_data['row_count']
                columns_with_nulls = sum(1 for count in null_counts.values() if count > 0)
                
                html_content += f"""
                <div class="stat-card">
                    <div class="stat-title">{table_name}</div>
                    <div class="stat-value">{total_rows:,}</div>
                    <div style="margin-top: 10px;">
                        <strong>Columns:</strong> {len(schema)}<br>
                        <strong>Columns with NULLs:</strong> {columns_with_nulls}<br>
                        <strong>Data Types:</strong>
                        <ul style="margin: 5px 0; padding-left: 20px;">
                """
                
                type_counts = {}
                for col_info in schema:
                    col_type = col_info[1] if len(col_info) > 1 else 'UNKNOWN'
                    type_counts[col_type] = type_counts.get(col_type, 0) + 1
                
                for dtype, count in type_counts.items():
                    html_content += f"<li>{dtype}: {count}</li>"
                
                html_content += """
                        </ul>
                        <strong>Column Names:</strong>
                        <ul style="margin: 5px 0; padding-left: 20px; font-size: 11px;">
                """
                
                for col_info in schema:
                    col_name = col_info[0]
                    col_type = col_info[1] if len(col_info) > 1 else 'UNKNOWN'
                    html_content += f"<li><code>{col_name}</code> ({col_type})</li>"
                
                html_content += """
                        </ul>
                    </div>
                </div>
                """
        
        html_content += "</div></div>"
    
    # Add data quality section
    all_present = results['tables']['all_present']
    status_class = 'success' if all_present else 'error'
    status_text = '✅ PASS' if all_present else '❌ FAIL'
    details_text = 'All 9 tables found' if all_present else f"Missing: {', '.join(results['tables']['missing'])}"
    
    html_content += f"""
        <div class="section">
            <h2>✅ Data Quality Checks</h2>
            <table>
                <tr><th>Check</th><th>Status</th><th>Details</th></tr>
                <tr>
                    <td>All expected tables present</td>
                    <td class="{status_class}">
                        {status_text}
                    </td>
                    <td>{details_text}</td>
                </tr>
    """
    
    # Add specific data quality results for each table
    if 'fact_phages' in results['data_quality']:
        phage_data = results['data_quality']['fact_phages']
        html_content += f"""
                <tr>
                    <td>Duplicate Phage IDs</td>
                    <td class="{'success' if phage_data['duplicate_phage_ids'] == 0 else 'error'}">
                        {'✅ PASS' if phage_data['duplicate_phage_ids'] == 0 else '❌ FAIL'}
                    </td>
                    <td>{phage_data['duplicate_phage_ids']} duplicates found</td>
                </tr>
        """
    
    if 'dim_proteins' in results['data_quality']:
        protein_data = results['data_quality']['dim_proteins']
        html_content += f"""
                <tr>
                    <td>Orphaned Proteins</td>
                    <td class="{'success' if protein_data['orphaned_proteins'] == 0 else 'warning'}">
                        {'✅ PASS' if protein_data['orphaned_proteins'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{protein_data['orphaned_proteins']} proteins without matching phages</td>
                </tr>
                <tr>
                    <td>Duplicate Protein IDs</td>
                    <td class="{'success' if protein_data['duplicate_protein_ids'] == 0 else 'warning'}">
                        {'✅ PASS' if protein_data['duplicate_protein_ids'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{protein_data['duplicate_protein_ids']} duplicate protein IDs</td>
                </tr>
        """
    
    if 'dim_terminators' in results['data_quality']:
        term_data = results['data_quality']['dim_terminators']
        html_content += f"""
                <tr>
                    <td>Orphaned Terminators</td>
                    <td class="{'success' if term_data['orphaned_terminators'] == 0 else 'warning'}">
                        {'✅ PASS' if term_data['orphaned_terminators'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{term_data['orphaned_terminators']} terminators without matching phages</td>
                </tr>
        """
    
    if 'dim_anti_crispr' in results['data_quality']:
        acr_data = results['data_quality']['dim_anti_crispr']
        html_content += f"""
                <tr>
                    <td>Orphaned Anti-CRISPR</td>
                    <td class="{'success' if acr_data['orphaned_anti_crispr'] == 0 else 'warning'}">
                        {'✅ PASS' if acr_data['orphaned_anti_crispr'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{acr_data['orphaned_anti_crispr']} anti-CRISPR entries without matching phages</td>
                </tr>
                <tr>
                    <td>Duplicate Protein IDs (Anti-CRISPR)</td>
                    <td class="{'success' if acr_data['duplicate_protein_ids'] == 0 else 'warning'}">
                        {'✅ PASS' if acr_data['duplicate_protein_ids'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{acr_data['duplicate_protein_ids']} duplicate protein IDs</td>
                </tr>
        """
    
    if 'dim_virulent_factors' in results['data_quality']:
        vf_data = results['data_quality']['dim_virulent_factors']
        html_content += f"""
                <tr>
                    <td>Orphaned Virulent Factors</td>
                    <td class="{'success' if vf_data['orphaned_virulent_factors'] == 0 else 'warning'}">
                        {'✅ PASS' if vf_data['orphaned_virulent_factors'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{vf_data['orphaned_virulent_factors']} virulent factors without matching phages</td>
                </tr>
                <tr>
                    <td>Duplicate Protein IDs (Virulent Factors)</td>
                    <td class="{'success' if vf_data['duplicate_protein_ids'] == 0 else 'warning'}">
                        {'✅ PASS' if vf_data['duplicate_protein_ids'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{vf_data['duplicate_protein_ids']} duplicate protein IDs</td>
                </tr>
        """
    
    if 'dim_transmembrane_proteins' in results['data_quality']:
        tm_data = results['data_quality']['dim_transmembrane_proteins']
        html_content += f"""
                <tr>
                    <td>Orphaned Transmembrane Proteins</td>
                    <td class="{'success' if tm_data['orphaned_transmembrane'] == 0 else 'warning'}">
                        {'✅ PASS' if tm_data['orphaned_transmembrane'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{tm_data['orphaned_transmembrane']} transmembrane proteins without matching phages</td>
                </tr>
                <tr>
                    <td>Duplicate Protein IDs (Transmembrane)</td>
                    <td class="{'success' if tm_data['duplicate_protein_ids'] == 0 else 'warning'}">
                        {'✅ PASS' if tm_data['duplicate_protein_ids'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{tm_data['duplicate_protein_ids']} duplicate protein IDs</td>
                </tr>
                <tr>
                    <td>TMH Statistics</td>
                    <td class="success">ℹ️ INFO</td>
                    <td>Avg TMHs: {tm_data['tmh_stats']['avg']}, Range: {tm_data['tmh_stats']['min']}-{tm_data['tmh_stats']['max']}</td>
                </tr>
        """
    
    if 'dim_trna_tmrna' in results['data_quality']:
        trna_data = results['data_quality']['dim_trna_tmrna']
        html_content += f"""
                <tr>
                    <td>Orphaned tRNA/tmRNA</td>
                    <td class="{'success' if trna_data['orphaned_trna'] == 0 else 'warning'}">
                        {'✅ PASS' if trna_data['orphaned_trna'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{trna_data['orphaned_trna']} tRNA/tmRNA entries without matching phages</td>
                </tr>
                <tr>
                    <td>Duplicate tRNA IDs</td>
                    <td class="{'success' if trna_data['duplicate_trna_ids'] == 0 else 'warning'}">
                        {'✅ PASS' if trna_data['duplicate_trna_ids'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{trna_data['duplicate_trna_ids']} duplicate tRNA IDs</td>
                </tr>
        """
    
    if 'dim_crispr_arrays' in results['data_quality']:
        crispr_data = results['data_quality']['dim_crispr_arrays']
        html_content += f"""
                <tr>
                    <td>Orphaned CRISPR Arrays</td>
                    <td class="{'success' if crispr_data['orphaned_crispr_arrays'] == 0 else 'warning'}">
                        {'✅ PASS' if crispr_data['orphaned_crispr_arrays'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{crispr_data['orphaned_crispr_arrays']} CRISPR arrays without matching phages</td>
                </tr>
                <tr>
                    <td>Duplicate CRISPR IDs</td>
                    <td class="{'success' if crispr_data['duplicate_crispr_ids'] == 0 else 'warning'}">
                        {'✅ PASS' if crispr_data['duplicate_crispr_ids'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{crispr_data['duplicate_crispr_ids']} duplicate CRISPR IDs</td>
                </tr>
        """
    
    if 'dim_antimicrobial_resistance_genes' in results['data_quality']:
        amr_data = results['data_quality']['dim_antimicrobial_resistance_genes']
        html_content += f"""
                <tr>
                    <td>Orphaned AMR Genes</td>
                    <td class="{'success' if amr_data['orphaned_amr'] == 0 else 'warning'}">
                        {'✅ PASS' if amr_data['orphaned_amr'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{amr_data['orphaned_amr']} AMR genes without matching phages</td>
                </tr>
                <tr>
                    <td>Duplicate Protein IDs (AMR)</td>
                    <td class="{'success' if amr_data['duplicate_protein_ids'] == 0 else 'warning'}">
                        {'✅ PASS' if amr_data['duplicate_protein_ids'] == 0 else '⚠️ WARNING'}
                    </td>
                    <td>{amr_data['duplicate_protein_ids']} duplicate protein IDs</td>
                </tr>
        """

    html_content += """
            </table>
        </div>
        
        <div class="section">
            <h2>🔧 Database Objects</h2>
            <p><strong>Indexes:</strong> """ + ', '.join(results.get('indexes', ['None found'])) + """</p>
            <p><strong>Views:</strong> """ + ', '.join(results.get('views', ['None found'])) + """</p>
        </div>
    """

    # Private data section
    private_data = results.get('private_data', {})
    priv_phage_count = private_data.get('private_phage_count', 0)
    priv_host_count = private_data.get('private_host_count', 0)
    priv_interactions = private_data.get('private_interactions', {})
    priv_interaction_count = priv_interactions.get('row_count', 0)
    priv_per_source = priv_interactions.get('per_source', {})
    priv_lifestyle = priv_interactions.get('lifestyle_distribution', {})

    if priv_phage_count or priv_interaction_count:
        html_content += f"""
        <div class="section">
            <h2>🔒 Private Data Overview</h2>
            <p style="color: #6c757d;">Private data is ingested from local sources and merged with the public PhageScope database.</p>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-title">Private Phages</div>
                    <div class="stat-value">{priv_phage_count:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Private Hosts</div>
                    <div class="stat-value">{priv_host_count:,}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-title">Private Interactions</div>
                    <div class="stat-value">{priv_interaction_count:,}</div>
                </div>
            </div>
        """

        if priv_per_source:
            max_count = max(priv_per_source.values(), default=1)
            html_content += """
            <h3 style="margin-top: 20px;">Interactions per Private Source</h3>
            <div class="chart-container">
            """
            for source_db, count in sorted(priv_per_source.items(), key=lambda x: -x[1]):
                bar_width = max(4, int(count / max_count * 300))
                html_content += f"""
                <div class="bar">
                    <span class="bar-label">{source_db}</span>
                    <div class="bar-fill" style="width: {bar_width}px;"></div>
                    <span class="bar-value">{count:,}</span>
                </div>
                """
            html_content += "</div>"

        if priv_lifestyle:
            html_content += """
            <h3 style="margin-top: 20px;">Lifestyle / Interaction Distribution</h3>
            <table>
                <tr><th>Interaction Type</th><th>Count</th></tr>
            """
            for lifestyle, count in sorted(priv_lifestyle.items(), key=lambda x: -x[1]):
                html_content += f"<tr><td>{lifestyle}</td><td>{count:,}</td></tr>"
            html_content += "</table>"

        html_content += "</div>"
    else:
        html_content += """
        <div class="section">
            <h2>🔒 Private Data Overview</h2>
            <p style="color: #6c757d;">No private data was ingested for this database build.</p>
        </div>
        """

    html_content += """
    </body>
    </html>
    """
    
    with open(report_path, 'w') as f:
        f.write(html_content)

if __name__ == "__main__":
    validate_database()

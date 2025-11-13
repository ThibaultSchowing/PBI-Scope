#!.pixi/envs/default/bin/python

import duckdb
import os
import logging
import sys
from datetime import datetime
import json

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
        'summary': {}
    }
    
    try:
        # 1. Check tables exist
        logging.info("Checking table existence...")
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [table[0] for table in tables]
        
        expected_tables = ['fact_phages', 'dim_proteins', 'dim_terminators', 'dim_anti_crispr']
        missing_tables = [t for t in expected_tables if t not in table_names]
        
        validation_results['tables']['existing'] = table_names
        validation_results['tables']['missing'] = missing_tables
        validation_results['tables']['all_present'] = len(missing_tables) == 0
        
        # 2. Check table schemas and row counts
        for table in expected_tables:
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
            # Check for duplicate Phage_IDs
            duplicate_phages = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Phage_ID, COUNT(*) as cnt 
                    FROM fact_phages 
                    GROUP BY Phage_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            # Check data range for Length
            length_stats = conn.execute("""
                SELECT MIN(Length), MAX(Length), AVG(Length), COUNT(Length)
                FROM fact_phages 
                WHERE Length IS NOT NULL
            """).fetchone()
            
            # Check Source_DB distribution
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
            # Check protein-phage relationships
            orphaned_proteins = conn.execute("""
                SELECT COUNT(*) FROM dim_proteins p
                LEFT JOIN fact_phages f ON p.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            # Check for duplicate Protein_IDs
            duplicate_proteins = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Protein_ID, COUNT(*) as cnt 
                    FROM dim_proteins 
                    GROUP BY Protein_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            # Check Source_DB distribution
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
            # Check terminator-phage relationships
            orphaned_terminators = conn.execute("""
                SELECT COUNT(*) FROM dim_terminators t
                LEFT JOIN fact_phages f ON t.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            # Check terminator type distribution
            terminator_types = conn.execute("""
                SELECT terminator_type, COUNT(*) as count
                FROM dim_terminators 
                WHERE terminator_type IS NOT NULL
                GROUP BY terminator_type 
                ORDER BY count DESC
            """).fetchall()
            
            # Check Source_DB distribution
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
        
        # DIM_ANTI_CRISPR validation - ✅ FIXED
        if 'dim_anti_crispr' in table_names:
            # Check anti-CRISPR-phage relationships
            orphaned_anti_crispr = conn.execute("""
                SELECT COUNT(*) FROM dim_anti_crispr a
                LEFT JOIN fact_phages f ON a.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            # ✅ FIXED: Check for duplicate Protein_IDs (not Anti_CRISPR_ID)
            duplicate_acr = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT Protein_ID, COUNT(*) as cnt 
                    FROM dim_anti_crispr 
                    WHERE Protein_ID IS NOT NULL
                    GROUP BY Protein_ID 
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            
            # ✅ ADDED: Check Source_DB distribution
            acr_source_db = conn.execute("""
                SELECT Source_DB, COUNT(*) as count
                FROM dim_anti_crispr 
                GROUP BY Source_DB 
                ORDER BY count DESC
            """).fetchall()
            
            # ✅ ADDED: Check Source type distribution
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
        
        # 4. Check indexes exist
        logging.info("Checking indexes...")
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        validation_results['indexes'] = [idx[0] for idx in indexes]
        
        # 5. Check views exist
        logging.info("Checking views...")
        views = conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
        validation_results['views'] = [view[0] for view in views]
        
        # 6. Overall summary - ✅ ADDED anti_crispr
        total_phages = validation_results['tables'].get('fact_phages', {}).get('row_count', 0)
        total_proteins = validation_results['tables'].get('dim_proteins', {}).get('row_count', 0)
        total_terminators = validation_results['tables'].get('dim_terminators', {}).get('row_count', 0)
        total_anti_crispr = validation_results['tables'].get('dim_anti_crispr', {}).get('row_count', 0)
        
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
        
        validation_results['summary'] = {
            'total_phages': total_phages,
            'total_proteins': total_proteins,
            'total_terminators': total_terminators,
            'total_anti_crispr': total_anti_crispr,  # ✅ ADDED
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
            .metric {{ font-size: 28px; font-weight: bold; text-align: center; color: #495057; }}
            .metric-label {{ font-size: 14px; color: #6c757d; margin-top: 5px; }}
            
            /* Database Schema Visualization */
            .schema-container {{ display: flex; justify-content: center; align-items: center; margin: 20px 0; flex-wrap: wrap; gap: 20px; }}
            .schema-vertical {{ display: flex; flex-direction: column; align-items: center; gap: 15px; }}
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
            }}
            .table-name {{ font-weight: bold; color: #007bff; font-size: 16px; margin-bottom: 10px; }}
            .table-name.central {{ color: #28a745; }}
            .table-info {{ font-size: 12px; color: #6c757d; }}
            .relationship-vertical {{ 
                width: 2px;
                height: 40px; 
                background: #28a745; 
                margin: 0 auto;
            }}
            
            /* Statistics Cards */
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }}
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
            <div style="display: flex; justify-content: space-around; margin: 30px 0; flex-wrap: wrap;">
                <div class="metric">
                    <div>{results['summary']['total_phages']:,}</div>
                    <div class="metric-label">Phages</div>
                </div>
                <div class="metric">
                    <div>{results['summary']['total_proteins']:,}</div>
                    <div class="metric-label">Proteins</div>
                </div>
                <div class="metric">
                    <div>{results['summary']['total_terminators']:,}</div>
                    <div class="metric-label">Terminators</div>
                </div>
                <div class="metric">
                    <div>{results['summary']['total_anti_crispr']:,}</div>
                    <div class="metric-label">Anti-CRISPR</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>🗂️ Database Schema & Relationships</h2>
            <p style="text-align: center; color: #6c757d; margin-bottom: 20px;">
                All dimension tables are linked to fact_phages via <strong>Phage_ID</strong>
            </p>
            <div class="schema-container">
                <div class="schema-vertical">
                    <div class="table-box">
                        <div class="table-name">dim_proteins</div>
                        <div class="table-info">
                            {results['tables'].get('dim_proteins', {}).get('row_count', 0):,} rows<br>
                            Foreign: Phage_ID
                        </div>
                    </div>
                    <div class="relationship-vertical"></div>
                </div>
                
                <div class="table-box central">
                    <div class="table-name central">fact_phages</div>
                    <div class="table-info">
                        {results['tables'].get('fact_phages', {}).get('row_count', 0):,} rows<br>
                        Primary: Phage_ID
                    </div>
                </div>
                
                <div class="schema-vertical">
                    <div class="table-box">
                        <div class="table-name">dim_terminators</div>
                        <div class="table-info">
                            {results['tables'].get('dim_terminators', {}).get('row_count', 0):,} rows<br>
                            Foreign: Phage_ID
                        </div>
                    </div>
                    <div class="relationship-vertical"></div>
                </div>
                
                <div class="schema-vertical">
                    <div class="table-box">
                        <div class="table-name">dim_anti_crispr</div>
                        <div class="table-info">
                            {results['tables'].get('dim_anti_crispr', {}).get('row_count', 0):,} rows<br>
                            Foreign: Phage_ID
                        </div>
                    </div>
                    <div class="relationship-vertical"></div>
                </div>
            </div>
        </div>
    """
    
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
                
                # Calculate completeness
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
                
                # Group columns by data type
                type_counts = {}
                for col_info in schema:
                    col_type = col_info[1] if len(col_info) > 1 else 'UNKNOWN'
                    type_counts[col_type] = type_counts.get(col_type, 0) + 1
                
                for dtype, count in type_counts.items():
                    html_content += f"<li>{dtype}: {count}</li>"
                
                html_content += """
                        </ul>
                    </div>
                </div>
                """
        
        html_content += "</div></div>"
    
    # Add source distribution visualization
    if 'fact_phages' in results['data_quality']:
        source_dist = results['data_quality']['fact_phages'].get('source_distribution', {})
        if source_dist:
            max_count = max(source_dist.values()) if source_dist.values() else 1
            total = sum(source_dist.values())
            
            html_content += """
            <div class="section">
                <h2>📈 Source Database Distribution (fact_phages)</h2>
                <div class="chart-container">
            """
            
            for source, count in sorted(source_dist.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / max_count) * 100
                html_content += f"""
                <div class="bar">
                    <div class="bar-label">{source}:</div>
                    <div class="bar-fill" style="width: {percentage}%;"></div>
                    <div class="bar-value">{count:,} ({count/total*100:.1f}%)</div>
                </div>
                """
            
            html_content += "</div></div>"
    
    # Add data quality section
    html_content += """
        <div class="section">
            <h2>✅ Data Quality Checks</h2>
            <table>
                <tr><th>Check</th><th>Status</th><th>Details</th></tr>
                <tr>
                    <td>All expected tables present</td>
                    <td class="{'success' if results['tables']['all_present'] else 'error'}">
                        {'✅ PASS' if results['tables']['all_present'] else '❌ FAIL'}
                    </td>
                    <td>{'All 4 tables found' if results['tables']['all_present'] else f"Missing: {', '.join(results['tables']['missing'])}"}</td>
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
                    <td>{protein_data['duplicate_protein_ids']} duplicate protein IDs found</td>
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
    
    # ✅ ADDED: Anti-CRISPR quality checks
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
                    <td>{acr_data['duplicate_protein_ids']} duplicate protein IDs in anti-CRISPR table</td>
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
    </body>
    </html>
    """
    
    with open(report_path, 'w') as f:
        f.write(html_content)

if __name__ == "__main__":
    validate_database()
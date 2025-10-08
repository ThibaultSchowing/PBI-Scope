#!.pixi/envs/default/bin/python
# filepath: /home/twg/workplace/PBI/workflow/scripts/validate_database.py

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
    conn = duckdb.connect(db_path)
    
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
        
        expected_tables = ['fact_phages', 'dim_proteins', 'dim_terminators']
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
                    null_count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col_name} IS NULL").fetchone()[0]
                    null_counts[col_name] = null_count
                
                validation_results['tables'][table] = {
                    'schema': schema,
                    'row_count': row_count,
                    'null_counts': null_counts
                }
        
        # 3. Data quality checks
        logging.info("Performing data quality checks...")
        
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
        
        if 'dim_proteins' in table_names:
            # Check protein-phage relationships
            orphaned_proteins = conn.execute("""
                SELECT COUNT(*) FROM dim_proteins p
                LEFT JOIN fact_phages f ON p.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            validation_results['data_quality']['dim_proteins'] = {
                'orphaned_proteins': orphaned_proteins
            }
        
        if 'dim_terminators' in table_names:
            # Check terminator-phage relationships
            orphaned_terminators = conn.execute("""
                SELECT COUNT(*) FROM dim_terminators t
                LEFT JOIN fact_phages f ON t.Phage_ID = f.Phage_ID
                WHERE f.Phage_ID IS NULL
            """).fetchone()[0]
            
            validation_results['data_quality']['dim_terminators'] = {
                'orphaned_terminators': orphaned_terminators
            }
        
        # 4. Check indexes exist
        logging.info("Checking indexes...")
        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        validation_results['indexes'] = [idx[0] for idx in indexes]
        
        # 5. Check views exist
        logging.info("Checking views...")
        views = conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
        validation_results['views'] = [view[0] for view in views]
        
        # 6. Overall summary
        total_phages = validation_results['tables'].get('fact_phages', {}).get('row_count', 0)
        total_proteins = validation_results['tables'].get('dim_proteins', {}).get('row_count', 0)
        total_terminators = validation_results['tables'].get('dim_terminators', {}).get('row_count', 0)
        
        validation_results['summary'] = {
            'total_phages': total_phages,
            'total_proteins': total_proteins,
            'total_terminators': total_terminators,
            'all_tables_present': validation_results['tables']['all_present'],
            'data_quality_passed': (
                validation_results['data_quality'].get('fact_phages', {}).get('duplicate_phage_ids', 0) == 0 and
                validation_results['data_quality'].get('dim_proteins', {}).get('orphaned_proteins', 0) == 0 and
                validation_results['data_quality'].get('dim_terminators', {}).get('orphaned_terminators', 0) == 0
            )
        }
        
    except Exception as e:
        logging.error(f"Error during validation: {str(e)}")
        validation_results['error'] = str(e)
    
    finally:
        conn.close()
    
    # Generate HTML report
    generate_html_report(validation_results, report_path)
    
    logging.info(f"✅ Validation complete! Report saved to: {report_path}")

def generate_html_report(results, report_path):
    """Generate an HTML validation report"""
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PhageScope Database Validation Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 8px; }}
            .section {{ margin: 20px 0; }}
            .success {{ color: green; font-weight: bold; }}
            .warning {{ color: orange; font-weight: bold; }}
            .error {{ color: red; font-weight: bold; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .metric {{ font-size: 24px; font-weight: bold; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🧬 PhageScope Database Validation Report</h1>
            <p><strong>Generated:</strong> {results['timestamp']}</p>
            <p><strong>Database:</strong> {results['database_path']}</p>
        </div>
        
        <div class="section">
            <h2>📊 Summary</h2>
            <div style="display: flex; justify-content: space-around;">
                <div class="metric">
                    <div>{results['summary']['total_phages']:,}</div>
                    <div style="font-size: 16px;">Phages</div>
                </div>
                <div class="metric">
                    <div>{results['summary']['total_proteins']:,}</div>
                    <div style="font-size: 16px;">Proteins</div>
                </div>
                <div class="metric">
                    <div>{results['summary']['total_terminators']:,}</div>
                    <div style="font-size: 16px;">Terminators</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>🗃️ Table Status</h2>
            <table>
                <tr><th>Check</th><th>Status</th><th>Details</th></tr>
                <tr>
                    <td>All tables present</td>
                    <td class="{'success' if results['tables']['all_present'] else 'error'}">
                        {'✅ PASS' if results['tables']['all_present'] else '❌ FAIL'}
                    </td>
                    <td>
                        Present: {', '.join(results['tables']['existing'])}<br>
                        {'Missing: ' + ', '.join(results['tables']['missing']) if results['tables']['missing'] else ''}
                    </td>
                </tr>
            </table>
        </div>
        
        <div class="section">
            <h2>📈 Data Quality</h2>
            <table>
                <tr><th>Check</th><th>Status</th><th>Details</th></tr>
    """
    
    # Add data quality checks
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
        """
    
    html_content += """
            </table>
        </div>
        
        <div class="section">
            <h2>🔧 Database Objects</h2>
            <p><strong>Indexes:</strong> """ + ', '.join(results.get('indexes', [])) + """</p>
            <p><strong>Views:</strong> """ + ', '.join(results.get('views', [])) + """</p>
        </div>
        
        <div class="section">
            <h2>📋 Detailed Statistics</h2>
            <pre style="background-color: #f0f0f0; padding: 15px; border-radius: 5px; overflow-x: auto;">""" + json.dumps(results, indent=2) + """</pre>
        </div>
    </body>
    </html>
    """
    
    with open(report_path, 'w') as f:
        f.write(html_content)

if __name__ == "__main__":
    validate_database()
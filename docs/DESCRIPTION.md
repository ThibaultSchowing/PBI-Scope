



## Next Steps

- Add data
- Prepare to add data
- Database update module
- ML integration
- Docker







### Available Views

The database includes pre-built analytical views:

- **`phage_summary`**: Aggregated statistics by data source
- **`phage_size_distribution`**: Genome size categorization analysis
- **`phage_complete_profile`**: Comprehensive phage characterization with all dimension counts

```sql
-- Use pre-built views
SELECT * FROM phage_summary;
SELECT * FROM phage_size_distribution;
SELECT * FROM phage_complete_profile WHERE protein_count > 100;
```

### Database Indexes

All tables include optimized indexes on:
- **Primary keys**: `Phage_ID`, `Protein_ID`, `trna_tmrna_id`
- **Foreign keys**: All `Phage_ID` columns in dimension tables
- **Source tracking**: `Source_DB` columns for source-based filtering

## 📊 Data Quality & Validation

### Automated Validation Checks

The pipeline performs comprehensive quality control:

1. **Schema Validation**
   - Table existence verification (all 7 tables)
   - Column presence and data type checks
   - Index verification

2. **Data Integrity**
   - Duplicate detection (Phage_ID, Protein_ID, etc.)
   - Orphaned record detection (foreign key consistency)
   - NULL value distribution analysis

3. **Statistical Validation**
   - Row count summaries
   - Source distribution analysis
   - Numerical range validation (genome sizes, GC content, TMH counts)

4. **Relationship Verification**
   - Foreign key consistency across all dimension tables
   - Source database alignment (e.g., proteins matching their phages)

### Validation Reports

HTML reports are generated with:
- ✅ **Visual database schema** diagram
- 📊 **Row count statistics** for all tables
- 🔍 **Data quality metrics** with pass/fail indicators
- 📈 **Distribution charts** for key metrics
- ⚠️ **Warning flags** for data quality issues

Access reports at: `reports/database_validation.html`

## 🔧 Pipeline Development

### Adding New Data Sources

1. **Update configuration**: Add URLs to source lists in merge scripts
2. **Extend merge scripts**: Modify scripts in `workflow/scripts/mergers/`
3. **Update schema**: Modify `workflow/scripts/create_duckdb.py` if needed
4. **Update validation**: Add checks to `workflow/scripts/validate_db.py`
5. **Test thoroughly**: Run on subset before full integration

### Customizing Data Processing

- **Column mapping**: Edit `workflow/scripts/utils.py`
- **Data cleaning**: Modify merge scripts for source-specific processing
- **Type conversion**: Update `convert_numerical_columns()` in utils
- **Schema changes**: Update `workflow/scripts/create_duckdb.py`

### Quality Control

The pipeline includes comprehensive validation:

- **Data integrity checks**: Duplicate detection, orphaned records
- **Schema validation**: Column presence, data types
- **Relationship verification**: Foreign key consistency across 7 tables
- **Performance monitoring**: Index effectiveness, query optimization
- **Distribution analysis**: TMH counts, tRNA types, virulence factors

## 📈 Performance Considerations

### Database Optimization

- **Star schema design** for fast analytical queries
- **Columnar storage** (DuckDB) for aggregation performance
- **14 targeted indexes** on join and filter columns (Phage_ID, Source_DB)
- **Materialized views** for common query patterns
- **Type-safe conversions** with NULL handling

### Pipeline Efficiency

- **Parallel processing** with configurable core count
- **Incremental updates** via Snakemake dependency tracking
- **Temporary file management** for space efficiency
- **Error handling** with graceful degradation
- **Consistent CSV loading** with `all_varchar=true` for safe type conversion

### Optimization Tips

```python
# Use the optimized database for better query performance
conn = duckdb.connect('data/databases/phage_database_optimized.duckdb')

# Leverage indexes by filtering on Phage_ID or Source_DB
query = """
    SELECT * FROM dim_proteins 
    WHERE Phage_ID IN (SELECT Phage_ID FROM fact_phages WHERE Source_DB = 'GenBank')
"""

# Use pre-built views for common aggregations
df = conn.execute("SELECT * FROM phage_complete_profile").df()
```

## 📚 Data Sources

The pipeline integrates data from **14 major phage databases** via PhageScope:

| Database | Type | Approximate Records |
|----------|------|---------------------|
| GenBank | General | ~200,000 phages |
| RefSeq | Curated | ~15,000 phages |
| PhagesDB | Mycobacteriophages | ~2,000 phages |
| EMBL | European | ~50,000 phages |
| DDBJ | Japanese | ~30,000 phages |
| GOV2 | Viral genomes | ~100,000 phages |
| MGV | Gut viromes | ~50,000 phages |
| GVD | Global virome | ~40,000 phages |
| IMGVR | IMG/VR | ~30,000 phages |
| GPD | Gut phages | ~20,000 phages |
| CHVD | Chicken viromes | ~5,000 phages |
| STV | Soil/plant phages | ~3,000 phages |
| TemPhD | Temperate phages | ~2,000 phages |
| IGVD | Insect gut phages | ~1,000 phages |

## 🤝 Contributing

### Development Workflow

1. **Fork and clone** the repository
2. **Create feature branch**: `git checkout -b feature/new-dimension-table`
3. **Test changes**: Run pipeline on subset of data
4. **Validate output**: Check database integrity and reports
5. **Update documentation**: Modify DESCRIPTION.md for new features
6. **Submit pull request** with clear description

### Code Standards

- **Python**: Follow PEP 8 style guidelines
- **SQL**: Use uppercase keywords, meaningful aliases
- **Documentation**: Update README and inline comments for new features
- **Testing**: Validate with known datasets before merging
- **Consistency**: Use `all_varchar=true` for CSV loading, `TRY_CAST` for type conversion

## 📚 Dependencies

### Core Dependencies
- **Snakemake**: Workflow management and DAG execution
- **DuckDB**: High-performance analytical database engine
- **Pandas**: Data manipulation and analysis
- **NumPy**: Numerical operations
- **Requests**: HTTP library for data downloads

### Analysis Dependencies
- **Matplotlib**: Static plotting
- **Seaborn**: Statistical visualizations
- **Plotly**: Interactive visualizations
- **Jupyter**: Notebook interface for exploration

See `workflow/envs/` for complete environment specifications.

## 📄 License

[TBD]

## 🆘 Support

For questions, issues, or contributions:

- **Issues**: Use GitHub issue tracker
- **Documentation**: Check inline code comments and DESCRIPTION.md
- **Examples**: See `workflow/notebooks/expl_5_TestDB.ipynb` for database usage
- **Validation**: Review HTML reports in `reports/` directory

---

## 📋 Quick Reference

### Key Files
- **Database**: `data/databases/phage_database_optimized.duckdb`
- **Validation**: `reports/database_validation.html`
- **Exploration**: `workflow/notebooks/expl_5_TestDB.ipynb`

### Database Tables (7 total)
1. `fact_phages` - Central fact table
2. `dim_proteins` - Protein annotations
3. `dim_terminators` - Terminator predictions
4. `dim_anti_crispr` - Anti-CRISPR systems
5. `dim_virulent_factors` - Virulence factors
6. `dim_transmembrane_proteins` - Membrane proteins
7. `dim_trna_tmrna` - tRNA/tmRNA features

### System Requirements
- **Disk**: >15GB free space
- **RAM**: >8GB recommended (>16GB for full analysis)
- **CPU**: Multi-core recommended (4+ cores optimal)
- **OS**: Linux/macOS (Windows via WSL)

---

**Note**: This pipeline processes large genomic datasets. Ensure adequate system resources for smooth execution. The complete pipeline typically runs in 30-60 minutes on a modern workstation with 4+ cores.

## 4.3 Sequence Retrieval

### Design Decisions

**FASTA Header Indexing:**
- Protein FASTA uses full header as ID: `Phage_ID Protein_ID [description]`
- pyfaidx configured with `split_char='\x00'` to preserve full headers
- Critical for distinguishing multiple proteins from same phage

**Query Interface:**
- SQL-based retrieval for flexibility
- Supports both query-based and direct ID lookup
- Fuzzy matching fallback for ID format variations

### Usage Examples

```python
from pbi.retrieval import SequenceRetriever

# Initialize
retriever = SequenceRetriever(
    db_path="data/processed/databases/phage_database.duckdb",
    phage_fasta="data/processed/sequences/all_phages.fasta",
    protein_fasta="data/processed/sequences/all_proteins.fasta"
)

# Query-based retrieval
query = "SELECT Phage_ID FROM fact_phages WHERE Length > 50000"
phages = retriever.get_phage_sequences(query, limit=1000)

# Export to FASTA
retriever.export_fasta(phages, "output/large_phages.fasta")
```
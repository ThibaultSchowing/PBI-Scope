# 🧬 PhageScope Bioinformatics Integration (PBI)

A comprehensive bioinformatics pipeline for integrating, processing, and analyzing phage genomic data from multiple public databases. This pipeline creates a unified, queryable database from diverse phage data sources including GenBank, RefSeq, and PhagesDB, all already unified within PhageScope. 

## 🎯 Project Goals

The PBI pipeline addresses key challenges in phage genomics research:

- **Data Integration**: Harmonizes phage data from multiple heterogeneous sources
- **Standardization**: Creates consistent data schemas across different databases
- **Performance**: Builds optimized analytical databases for large-scale queries
- **Reproducibility**: Provides a fully automated, version-controlled pipeline
- **Accessibility**: Generates easy-to-use databases for downstream analysis

## 📊 Pipeline Overview

```
Raw Data Sources → Download → Merge → Validate → Optimized Database
     ↓               ↓        ↓        ↓            ↓
  GenBank         TSV Files  Clean    Quality    DuckDB Star
  RefSeq          PhagesDB   Unified  Checks     Schema
  PhagesDB        NCBI       CSVs     Reports    
```

### 🏗️ Architecture

The pipeline implements a **star schema** database design optimized for analytical queries:

- **`fact_phages`**: Central table with phage metadata (genome size, GC content, taxonomy, etc.)
- **`dim_proteins`**: Protein annotations and functional predictions
- **`dim_terminators`**: Transcription terminator predictions

All tables are linked via `Phage_ID`, enabling efficient multi-dimensional analysis.

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **Pixi package manager** ([installation guide](https://pixi.sh/latest/))
- **Internet connection** (for data downloads)

### Installation

```bash
git clone <repository-url>
cd PBI
pixi install
```

### Running the Pipeline

```bash
# Full pipeline execution
`pixi run snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --cores 4 `

# Run specific components
`pixi run snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --cores 4  ../data/databases/phage_database.duckdb `

# Generate validation report
`pixi run snakemake --directory workflow --snakefile workflow/Snakefile --cache --use-conda --printshellcmds --cores 4   reports/database_validation.html`
```

### Development Mode

For testing and development, preserve intermediate files:

```bash
# Keep temporary files during development
pixi run snakemake --directory workflow --cores 4 --notemp
```

## 📁 Project Structure

```
PBI/
├── workflow/
│   ├── Snakefile                    # Main pipeline definition
│   ├── rules/                       # Modular pipeline rules
│   │   ├── phagescope.smk          # Data download & merging
│   │   └── database.smk            # Database creation & validation
│   ├── scripts/                     # Processing scripts
│   │   ├── create_duckdb.py        # Database creation
│   │   ├── validate_db.py          # Quality validation
│   │   ├── mergers/                # Data integration scripts
│   │   └── utils.py                # Shared utilities
│   ├── notebooks/                  # Exploratory analysis notebooks
│   └── envs/                       # Conda environments
├── data/                           # Generated data
│   ├── intermediate_csv/           # Downloaded raw data
│   ├── merged/                     # Integrated datasets
│   └── databases/                  # Final databases
└── reports/                        # Validation reports
```

## 🗄️ Using the Database

The pipeline generates a **DuckDB** database optimized for analytical queries.

### Python Integration

```python
import duckdb

# Connect to database
conn = duckdb.connect('data/databases/phage_database_optimized.duckdb')

# Query as pandas DataFrame
df = conn.execute("""
    SELECT Source_DB, COUNT(*) as count 
    FROM fact_phages 
    GROUP BY Source_DB
""").df()

# Complex analytical query
results = conn.execute("""
    SELECT 
        f.Source_DB,
        COUNT(DISTINCT f.Phage_ID) as phage_count,
        COUNT(p.Protein_ID) as protein_count,
        AVG(f.Length) as avg_genome_size
    FROM fact_phages f
    LEFT JOIN dim_proteins p ON f.Phage_ID = p.Phage_ID
    GROUP BY f.Source_DB
""").fetchall()

conn.close()
```

### Available Views

The database includes pre-built analytical views:

- **`phage_summary`**: Aggregated statistics by data source
- **`phage_size_distribution`**: Genome size categorization analysis

```sql
-- Use pre-built views
SELECT * FROM phage_summary;
SELECT * FROM phage_size_distribution;
```

## 🔧 Pipeline Development

### Adding New Data Sources

1. **Update configuration**: Add URLs to `config/config.yaml`
2. **Extend merge scripts**: Modify scripts in `workflow/scripts/mergers/`
3. **Update validation**: Add checks to `workflow/scripts/validate_db.py`

### Customizing Data Processing

- **Column mapping**: Edit `workflow/scripts/utils.py`
- **Data cleaning**: Modify merge scripts for source-specific processing
- **Schema changes**: Update `workflow/scripts/create_duckdb.py`

### Quality Control

The pipeline includes comprehensive validation:

- **Data integrity checks**: Duplicate detection, orphaned records
- **Schema validation**: Column presence, data types
- **Relationship verification**: Foreign key consistency
- **Performance monitoring**: Index effectiveness, query optimization

## 📈 Performance Considerations

### Database Optimization

- **Star schema design** for fast analytical queries
- **Columnar storage** (DuckDB) for aggregation performance
- **Targeted indexes** on join and filter columns
- **Materialized views** for common query patterns

### Pipeline Efficiency

- **Parallel processing** with configurable core count
- **Incremental updates** via Snakemake dependency tracking
- **Temporary file management** for space efficiency
- **Error handling** with graceful degradation

## 🤝 Contributing

### Development Workflow

1. **Fork and clone** the repository
2. **Create feature branch**: `git checkout -b feature/new-data-source`
3. **Test changes**: Run pipeline on subset of data
4. **Validate output**: Check database integrity and reports
5. **Submit pull request** with clear description

### Code Standards

- **Python**: Follow PEP 8 style guidelines
- **SQL**: Use uppercase keywords, meaningful aliases
- **Documentation**: Update README for new features
- **Testing**: Validate with known datasets

## 📚 Dependencies

- **Snakemake**: Workflow management
- **DuckDB**: Analytical database engine
- **Pandas**: Data manipulation
- **NumPy**: Numerical operations
- **Requests/wget**: Data downloading

## 📄 License

[TBD]

## 🆘 Support

For questions, issues, or contributions:

- **Issues**: Use GitHub issue tracker
- **Documentation**: Check inline code comments
- **Examples**: See `workflow/scripts/` for usage patterns

---

**Note**: This pipeline processes large genomic datasets. Ensure adequate disk space (>10GB) and memory (>8GB RAM recommended) for full execution.
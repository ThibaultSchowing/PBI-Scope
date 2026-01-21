# Code Structure

Overview of the PBI project architecture and code organization.

## Project Layout

```
PBI/
├── workflow/              # Snakemake pipeline
│   ├── Snakefile         # Main pipeline definition
│   ├── rules/            # Modular pipeline rules
│   ├── scripts/          # Processing scripts
│   ├── config/           # Configuration files
│   ├── envs/             # Conda environments
│   ├── notebooks/        # Analysis notebooks
│   └── reports/          # Generated reports
│
├── src/pbi/              # Python package
│   ├── __init__.py       # Package initialization
│   ├── database.py       # Database utilities
│   ├── sequence_retrieval.py  # FASTA retrieval API
│   └── utils.py          # Helper functions
│
├── api/                  # REST API
│   ├── app.py            # FastAPI application
│   └── models.py         # Data models
│
├── docs/                 # Documentation (MkDocs)
│   ├── index.md          # Homepage
│   ├── guides/           # Installation and usage guides
│   ├── database/         # Database documentation
│   ├── api/              # API documentation
│   ├── reference/        # Command reference
│   └── archive/          # Archived documentation
│
├── data/                 # Data directory (gitignored)
│   ├── raw/              # Downloaded data
│   ├── intermediate/     # Processing intermediates
│   └── processed/        # Final outputs
│
├── tests/                # Unit tests (in development)
├── notebooks/            # User-facing notebooks
├── docker-compose.yml    # Docker orchestration
├── Dockerfile.api        # API container
├── setup.py              # Package configuration
└── mkdocs.yml            # Documentation configuration
```

## Key Components

### Snakemake Pipeline

**Location**: `workflow/`

The pipeline orchestrates data download, processing, and database creation:

- **`Snakefile`**: Main workflow definition
- **`rules/`**: Modular rules for different pipeline stages
  - `phagescope.smk`: Data download and preprocessing
  - `database.smk`: Database creation and validation
  - `sequences.smk`: FASTA processing and indexing
- **`scripts/`**: Python scripts for data processing
  - `database/`: Database creation and optimization
  - `preprocessing/mergers/`: Data integration scripts
  - `sequences/`: FASTA handling
  - `utils/`: Shared utilities

### Python Package

**Location**: `src/pbi/`

The PBI package provides utilities for working with the database:

- **`database.py`**: Database connection and query utilities
- **`sequence_retrieval.py`**: FASTA sequence retrieval API
- **`utils.py`**: Helper functions and utilities

### REST API

**Location**: `api/`

FastAPI-based REST interface for database queries:

- **`app.py`**: Main API application with endpoints
- **`models.py`**: Pydantic data models (if applicable)

### Documentation

**Location**: `docs/`

MkDocs-based documentation:

- **`guides/`**: Installation and usage guides
- **`database/`**: Database schema and documentation
- **`api/`**: API reference and examples
- **`reference/`**: Command reference and cheatsheet
- **`archive/`**: Historical documentation

## Data Flow

```
PhageScope APIs
      ↓
  Download (Snakemake rules)
      ↓
Raw Data (TSV, FASTA)
      ↓
 Merge & Process (Python scripts)
      ↓
Intermediate Data (Merged CSV/FASTA)
      ↓
Database Creation (DuckDB)
      ↓
Validation & Optimization
      ↓
Final Database + Sequences
      ↓
      ├─→ Python Package (local access)
      └─→ REST API (remote access)
```

## Module Dependencies

```
workflow/
    ↓ uses
src/pbi/
    ↑ provides utilities
api/
    ↓ uses
src/pbi/ + data/
```

## Development Workflow

1. **Data Pipeline**: Modify `workflow/` for data processing changes
2. **Python Package**: Update `src/pbi/` for new utilities
3. **API**: Extend `api/app.py` for new endpoints
4. **Documentation**: Update `docs/` for user-facing changes
5. **Testing**: Add tests to `tests/` (in development)

## Configuration Files

- **`workflow/config/config.yaml`**: Pipeline configuration
- **`workflow/envs/*.yaml`**: Conda environment specifications
- **`setup.py`**: Python package metadata
- **`mkdocs.yml`**: Documentation configuration
- **`docker-compose.yml`**: Container orchestration
- **`.gitignore`**: Version control exclusions

## Adding Features

### New Data Source
1. Add download rules to `workflow/rules/phagescope.smk`
2. Create merger script in `workflow/scripts/preprocessing/mergers/`
3. Update database schema in `workflow/scripts/database/create_duckdb.py`
4. Add validation in `workflow/scripts/database/validate_db.py`

### New API Endpoint
1. Add endpoint to `api/app.py`
2. Update `docs/api/overview.md`
3. Test with `curl` or Swagger UI

### New Utility Function
1. Add function to `src/pbi/utils.py` or create new module
2. Update `src/pbi/__init__.py` if needed
3. Document in docstrings
4. Add tests to `tests/`

## Best Practices

- **Code Style**: Follow PEP 8 for Python code
- **Documentation**: Update docs for user-facing changes
- **Testing**: Add tests for new features (when test framework is ready)
- **Git**: Use descriptive commit messages
- **Snakemake**: Keep rules modular and well-documented
- **Configuration**: Use config files instead of hardcoded values

## Resources

- [Snakemake Documentation](https://snakemake.readthedocs.io/)
- [DuckDB Documentation](https://duckdb.org/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [MkDocs Documentation](https://www.mkdocs.org/)

---

For contributing guidelines, see the project README or open an issue on GitHub.

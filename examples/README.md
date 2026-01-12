# PBI API Examples

This directory contains example scripts demonstrating how to use the PBI API.

## Prerequisites

- The PBI API must be running (see `DOCKER.md` in the root directory)
- Python 3.8+ with `requests` library installed

## Installation

```bash
pip install requests
```

## Usage

### API Usage Example

The `api_usage.py` script demonstrates common API operations:

```bash
python examples/api_usage.py
```

This script shows how to:
- Check API health
- Get database statistics
- List available tables
- Query phage data with filters
- Execute custom SQL queries
- Get data sources

## API Endpoints

The PBI API provides the following main endpoints:

- `GET /health` - Health check
- `GET /stats` - Database statistics
- `GET /tables` - List all tables
- `GET /tables/{table}/schema` - Get table schema
- `GET /phages` - Query phages with filters
- `GET /phages/{id}` - Get specific phage
- `GET /proteins` - Query proteins with filters
- `GET /sources` - List data sources
- `POST /query` - Execute custom SQL query

For full API documentation, visit:
- http://localhost:8000/docs (Swagger UI)
- http://localhost:8000/redoc (ReDoc)

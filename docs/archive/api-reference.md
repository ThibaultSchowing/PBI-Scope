# API Reference

The PBI API provides a REST interface for querying the phage database and retrieving sequences.

## Base URL

When running locally with Docker:
```
http://localhost:8000
```

## Authentication

Currently, the API does not require authentication. For production deployments, consider adding authentication.

## Interactive Documentation

The API provides interactive Swagger UI documentation at:
```
http://localhost:8000/docs
```

Visit this URL in your browser to explore all endpoints interactively.

## Endpoints

### Health & Status

#### `GET /`
Returns API information and list of available endpoints.

#### `GET /health`
Health check endpoint. Returns 200 if the database is connected.

#### `GET /stats`
Returns database statistics including counts for all tables.

### Data Querying

#### `POST /query`
Execute a custom SQL query against the database.

**⚠️ Warning:** Use with caution. In production, consider limiting to read-only queries.

#### `POST /phages`
Retrieve phage sequences and metadata.

#### `POST /proteins`
Retrieve protein sequences and metadata.

### FASTA Export

#### `POST /phages/fasta`
Export phage sequences in FASTA format.

#### `POST /proteins/fasta`
Export protein sequences in FASTA format.

## Database Schema

The database uses a star schema with:
- `fact_phages` - Main phage metadata table
- Dimension tables for proteins, terminators, CRISPR, AMR genes, etc.
- All tables include `Source_DB` column tracking the origin database

For complete API documentation with examples, visit the interactive docs at `http://localhost:8000/docs`

## Docker Volume Access

All data is stored in the `pbi-data` Docker volume.

### Accessing Reports

```bash
# Copy reports to host
docker run --rm -v pbi-data:/data -v $(pwd):/backup alpine \
  cp -r /data/processed/reports /backup/
```

## Support

For detailed endpoint documentation, examples, and database schema, visit the interactive API docs or see [DOCKER.md](../DOCKER.md).

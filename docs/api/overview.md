# API Reference

**Version: 0.4.0**

The PBI REST API provides a lightweight interface for querying the phage-host database without loading the full `pbi` package locally. It runs as a separate Docker service (`api`) and communicates with the same data volume as the analysis container.

## Starting the API

```bash
docker compose up api
```

The API is available at `http://localhost:8000`.

## Endpoints

### Health & Stats

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/stats` | Database statistics (row counts for all tables) |
| GET | `/tables` | List all tables and views |

### Metadata Queries

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/phage-metadata` | Phage metadata with optional WHERE clause |
| GET | `/host-metadata` | Host metadata with optional WHERE clause |
| GET | `/phage-host-metadata` | Combined phage-host metadata |
| GET | `/phage-host-pairs` | Phage-host pair IDs |
| GET | `/protein-metadata` | Protein metadata |

### Sequence Retrieval

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/phage/{id}/sequence` | Single phage DNA sequence |
| GET | `/phage/{id}/genome` | Phage genome (concat or list) |
| GET | `/host/{id}/genome` | Host genome with contig options |
| GET | `/host/{id}/genome-stats` | Host genome statistics |

### SQL Queries

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/query` | Arbitrary SQL (SELECT only) |

## Usage Examples

### cURL

```bash
# Health check
curl http://localhost:8000/health

# Database stats
curl http://localhost:8000/stats

# Get phage metadata (limited)
curl "http://localhost:8000/phage-metadata?limit=10"

# Filtered phage metadata
curl "http://localhost:8000/phage-metadata?where=Source_DB%20%3D%20%27RefSeq%27&limit=50"

# Single phage sequence
curl http://localhost:8000/phage/NC_001330.1/sequence

# Phage genome (concatenated)
curl "http://localhost:8000/phage/NC_001330.1/genome?mode=concat"

# Host genome stats
curl http://localhost:8000/host/GCF_000005845/genome-stats

# SQL query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT Source_DB, COUNT(*) FROM fact_phages GROUP BY Source_DB"}'
```

### Python (APIClient)

```python
from pbi import APIClient

client = APIClient("http://localhost:8000")

# Health and stats
client.health()
client.get_stats()

# Metadata queries
phages = client.get_phage_metadata(where_clause="Source_DB = 'RefSeq'", limit=50)
hosts = client.get_host_metadata(limit=100)
pairs = client.get_phage_host_metadata(limit=100)

# Sequence retrieval
seq = client.get_phage_sequence("NC_001330.1")
genome = client.get_phage_genome("NC_001330.1", mode="concat")
host_genome = client.get_host_genome("GCF_000005845", mode="concat")

# SQL query
df = client.query("SELECT Source_DB, COUNT(*) as cnt FROM fact_phages GROUP BY Source_DB")

client.close()
```

## Query Parameters

### Metadata Endpoints

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `where` | string | — | SQL WHERE clause (validated for safety) |
| `limit` | int | 100 | Maximum rows returned |

### Genome Endpoints

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | string | `concat` | `concat` (single string), `list` (array), `dict` (contig→seq) |
| `gap` | int | 100 | Ns between contigs in `concat` mode |
| `order` | string | `length` | Contig sort: `length`, `name`, or `file` |

## Security

- All queries are read-only (SELECT only)
- WHERE clauses are validated against injection patterns
- The API runs inside the Docker network; expose only if needed

## Recommended Use Cases

- **API**: Quick exploration, metadata lookups, single-sequence retrieval from notebooks
- **Analysis container + `pbi` package**: Bulk downloads, ML dataset preparation, complex multi-step workflows

See the [Installation Guide](../guides/installation.md) for Docker setup, and the [PBI Package Guide](../guides/pbi-package.md) for the full Python API.

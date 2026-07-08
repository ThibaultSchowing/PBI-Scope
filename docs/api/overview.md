# API Reference

**Version: 0.4.0**

The PBI-Scope REST API provides a lightweight interface for querying the phage-host database without loading the full `pbi` package locally. It runs as a separate Docker service (`api`) and communicates with the same data volume as the analysis container.

## Quick Start

```bash
# Start the API
docker compose up api

# Test connection
curl http://localhost:8000/health
```

```python
from pbi import APIClient

client = APIClient("http://localhost:8000")

# Get database stats
stats = client.get_stats()
print(f"Phages: {stats['database']['phages']:,}")

# Query metadata
phages = client.get_phage_metadata(limit=10)
print(phages.head())

client.close()
```

## When to Use API vs Package

| Task | API (`APIClient`) | Package (`SequenceRetriever`) |
|------|-------------------|------------------------------|
| Quick metadata lookup | ✅ Recommended | ✅ Works |
| Filtered queries | ✅ Recommended | ✅ Works |
| Single sequence retrieval | ✅ Works | ✅ Works |
| Bulk downloads | ❌ Not supported | ✅ Recommended |
| ML dataset preparation | ❌ Not supported | ✅ Recommended |
| Host genome streaming | ❌ Not supported | ✅ Required |
| SQL exploration | ✅ Recommended | ✅ Works |
| Shared access (multiple users) | ✅ Recommended | ❌ Single instance |

**Recommendation**: Use the API for quick exploration and metadata lookups. Use the `pbi` package for bulk operations, ML workflows, and when you need full control over data access.

---

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

---

## Common Workflows

### Explore phages by source

```python
from pbi import APIClient

client = APIClient("http://localhost:8000")

# Get phages from RefSeq
phages = client.get_phage_metadata(
    where_clause="Source_DB = 'RefSeq'",
    limit=100
)
print(f"Found {len(phages)} RefSeq phages")

# Get phages longer than 50kb
large_phages = client.get_phage_metadata(
    where_clause="Length > 50000",
    limit=50
)
print(f"Found {len(large_phages)} large phages")
```

### Get host genome for a phage

```python
# First get phage metadata
phages = client.get_phage_metadata(limit=1)
phage_id = phages['Phage_ID'].iloc[0]

# Then get host associations
pairs = client.get_phage_host_metadata(
    where_clause=f"Phage_ID = '{phage_id}'"
)
print(pairs[['Host_Species', 'Host_Assembly_Level']])
```

### SQL exploration

```python
# Source database distribution
source_dist = client.query("""
    SELECT
        Source_DB,
        COUNT(*) AS phage_count,
        ROUND(AVG(Length), 0) AS avg_length
    FROM fact_phages
    GROUP BY Source_DB
    ORDER BY phage_count DESC
""")
print(source_dist)
```

### Get phage sequence

```python
# Get a single phage sequence
seq = client.get_phage_sequence("NC_001330.1")
print(f"Sequence length: {len(seq):,} bp")

# Get genome (concatenated contigs)
genome = client.get_phage_genome("NC_001330.1", mode="concat")
print(f"Genome length: {len(genome):,} bp")
```

---

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

---

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

---

## Security

- All queries are read-only (SELECT only)
- WHERE clauses are validated against injection patterns
- The API runs inside the Docker network; expose only if needed

---

## See Also

- [Installation Guide](../guides/installation.md) — Docker setup
- [PBI-Scope Python Package](../guides/pbi-package.md) — Full Python API
- [Analysis Container Guide](../guides/analysis-guide.md) — Notebooks and IDE workflow

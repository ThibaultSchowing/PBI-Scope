# Docker Architecture - Before and After

## Before (Problem)

```
❌ No Docker infrastructure existed
❌ User manually created docker files
❌ Path mismatch between services

Pipeline Container               API Container
├─ Writes to: ???               ├─ Reads from: /data/processed/databases/
└─ No volume mount              └─ ERROR: Database not found!
```

## After (Solution)

```
✅ Complete Docker infrastructure
✅ Shared volume ensures path consistency
✅ API successfully finds database

┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose                          │
│                                                             │
│  ┌───────────────────┐         ┌──────────────────┐       │
│  │ Pipeline Service  │         │   API Service     │       │
│  │  (Snakemake)      │         │   (FastAPI)       │       │
│  │                   │         │                   │       │
│  │  Builds database  │         │  Serves queries   │       │
│  │  Processes data   │         │  Read-only access │       │
│  └─────────┬─────────┘         └────────┬──────────┘       │
│            │                            │                   │
│            │     ┌──────────────────┐   │                   │
│            └────▶│  Shared Volume   │◀──┘                   │
│                  │   pbi-data:/data │                       │
│                  │                  │                       │
│                  │  /data/processed/│                       │
│                  │    ├─ databases/ │                       │
│                  │    │  └─ phage_  │                       │
│                  │    │     database_│                       │
│                  │    │     optimized│                       │
│                  │    │     .duckdb  │                       │
│                  │    └─ sequences/ │                       │
│                  │       ├─ all_    │                       │
│                  │       │  phages. │                       │
│                  │       │  fasta   │                       │
│                  │       └─ all_    │                       │
│                  │          proteins│                       │
│                  │          .fasta  │                       │
│                  └──────────────────┘                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Path Resolution

### Pipeline Service (Writer)
```yaml
volumes:
  - pbi-data:/data
```
Writes to: `/data/processed/databases/phage_database_optimized.duckdb`

### API Service (Reader)
```yaml
volumes:
  - pbi-data:/data:ro  # Read-only for safety
environment:
  - DATA_PATH=/data/processed
```
Reads from: `${DATA_PATH}/databases/phage_database_optimized.duckdb`
           = `/data/processed/databases/phage_database_optimized.duckdb`

### Result
✅ Both paths resolve to the same file on the shared volume
✅ API can successfully access database built by pipeline
✅ Original error "Database not found" is resolved

## API Endpoints

The API provides comprehensive access to the database:

- `GET /health` - Health check
- `GET /stats` - Database statistics
- `POST /query` - Custom SQL queries
- `POST /phages` - Get phage sequences
- `POST /proteins` - Get protein sequences
- `POST /phages/fasta` - Export phages to FASTA
- `POST /proteins/fasta` - Export proteins to FASTA

## Usage Example

```bash
# Build and run pipeline
docker compose build pipeline
docker compose run --rm pipeline

# Start API
docker compose build api
docker compose up -d api

# Test API
curl http://localhost:8000/health
# {"status":"healthy","database":"connected"}

curl http://localhost:8000/stats
# {"database":{"phages":X,"proteins":Y},"fasta":{"phages":X,"proteins":Y}}

# Query database
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT * FROM fact_phages LIMIT 5"}'

# Get sequences in FASTA format
curl -X POST http://localhost:8000/phages/fasta \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT Phage_ID FROM fact_phages WHERE Length > 100000 LIMIT 10"}' \
  > large_phages.fasta
```

## Documentation

- `DOCKER.md` - Comprehensive Docker guide
- `README.md` - Quick start with Docker option
- `SOLUTION_SUMMARY.md` - Detailed solution explanation
- `test_docker_setup.sh` - Integration test script
- `tests/test_docker_paths.py` - Path verification

# Docker Guide

PBI-Scope uses Docker Compose to orchestrate three core services (`pipeline`, `analysis`, `api`) plus an optional `n8n` example container.

## Quick Start

```bash
# Clone and configure
git clone https://github.com/ThibaultSchowing/PBI-Scope.git
cd PBI-Scope
cp .env.example .env
# Edit .env: set NCBI_EMAIL, UID, GID, PBI_API_KEY, N8N_ENCRYPTION_KEY

# Build and run pipeline
docker compose build pipeline
docker compose run --rm pipeline

# Start analysis container
docker compose build analysis
docker compose up -d analysis

# Start the API
docker compose build api
docker compose up -d api

# Optional: n8n example (the API is n8n-compatible for custom workflows)
docker compose up -d n8n
```

See the [Installation Guide](installation.md) for detailed setup instructions.

## Services

| Service | Purpose | Port |
|---------|---------|------|
| `pipeline` | Builds/updates the database | — |
| `analysis` | Jupyter Lab + VS Code Dev Containers | 8886 (host) → 8888 (container) |
| `api` | REST API for metadata queries | 8000 |

Optional example (not part of the core stack):

| Service | Purpose | Port |
|---------|---------|------|
| `n8n` | Quick n8n workflow example calling the API (BLAST screening, alerts) | 5678 |

Connect to all three user-facing services from your laptop:

```bash
ssh -L 8888:localhost:8886 -L 8000:localhost:8000 -L 5678:localhost:5678 user@your-server
```

## Security

The `analysis` container runs Jupyter Lab with authentication disabled for local development. The optional `n8n` example requires you to create an admin account on first login. Jupyter and n8n should be accessed via an SSH tunnel, not exposed directly to the internet; the API can also be forwarded over SSH and should be protected with `PBI_API_KEY` when used beyond a trusted network. See [Analysis Container Guide](analysis-guide.md#security-notice), [n8n Workflows](n8n-integration.md#security), and [API Reference](../api/overview.md#authentication) for details.

## UID/GID Setup

Both `pipeline` and `analysis` services run as your host user to prevent root-owned files. Set `UID` and `GID` in `.env` after cloning:

```bash
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env
```

See [Installation Guide](installation.md) for full explanation.

## API Service

The API provides metadata queries and SQL exploration without the full `pbi` package:

```bash
docker compose up api
# Available at http://localhost:8000
```

See [API Reference](../api/overview.md) for endpoint documentation.

# Docker Guide

PBI-Scope uses Docker Compose to orchestrate four services: `pipeline`, `analysis`, `api`, and `n8n`.

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

# Start API + n8n workflow automation
docker compose build api
docker compose up -d api n8n
```

See the [Installation Guide](installation.md) for detailed setup instructions.

## Services

| Service | Purpose | Port |
|---------|---------|------|
| `pipeline` | Builds/updates the database | — |
| `analysis` | Jupyter Lab + VS Code Dev Containers | 8889 |
| `api` | REST API for metadata queries | 8000 |
| `n8n` | Workflow automation (BLAST screening, alerts) | 5678 |

## Security

The `analysis` container runs Jupyter Lab with authentication disabled for local development. The `n8n` container requires you to create an admin account on first login. Both are meant to be accessed via SSH tunnel, not exposed directly to the internet. See [Analysis Container Guide](analysis-guide.md#security-notice) and [n8n Workflows](n8n-integration.md#security) for details and hardening steps.

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


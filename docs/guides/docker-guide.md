# Docker Guide

PBI uses Docker Compose to orchestrate three services: `pipeline`, `analysis`, and `api`.

## Quick Start

```bash
# Clone and configure
git clone https://github.com/ThibaultSchowing/PBI.git
cd PBI
cp .env.example .env
# Edit .env: set NCBI_EMAIL, UID, GID

# Build and run pipeline
docker compose build pipeline
docker compose run --rm pipeline

# Start analysis container
docker compose build analysis
docker compose up -d analysis
```

See the [Installation Guide](installation.md) for detailed setup instructions.

## Services

| Service | Purpose | Port |
|---------|---------|------|
| `pipeline` | Builds/updates the database | — |
| `analysis` | Jupyter Lab + VS Code Dev Containers | 8889 |
| `api` | REST API for metadata queries | 8000 |

## Security

The `analysis` container runs Jupyter Lab with authentication disabled for local development. See [Analysis Container Guide](analysis-guide.md#️-security-notice) for details and hardening steps.

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

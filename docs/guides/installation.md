# Installation Guide

PBI-Scope is designed to run with Docker.

## Requirements

- Docker 20.10+
- Docker Compose 2+
- 225+ GB free disk
- 16 GB RAM minimum (32 GB recommended)

## 1) Clone and configure

```bash
git clone https://github.com/ThibaultSchowing/PBI.git
cd PBI

# Copy the example env file and open it to fill in NCBI credentials:
cp .env.example .env
# Set NCBI_EMAIL=your.email@example.com (and NCBI_API_KEY if you have one)

# Append your host UID and GID so containers write files as your user (not root):
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env
```

> **Why UID/GID?** Docker containers run as root by default. Without this, files
> written to bind-mounted directories (`./notebooks`, `./outputs`,
> `./pipeline_logs`) are owned by root and require `sudo` to delete or edit.
> Setting `UID`/`GID` makes containers run as your host user so all output files
> belong to you.
>
> On macOS with Docker Desktop this is handled transparently — setting the values
> is still safe and recommended for portability.

## 2) Run pipeline

```bash
docker compose build pipeline
docker compose run --rm pipeline
```

Pipeline order:

1. public phage download + merge
2. private source validation/ingestion (if present)
3. host resolution/download from NCBI
4. database + indexes + reports

## 3) Start analysis container

```bash
docker compose build analysis
docker compose up -d analysis
```

> ⚠️ **Security note**: The analysis container starts Jupyter Lab with authentication
> and XSRF protection **disabled** — this is intentional for local/SSH-tunnelled
> development. See the [Analysis Container Guide](analysis-guide.md#️-security-notice)
> for a full explanation and hardening steps before exposing the service to a network.

If remote, use an SSH tunnel (safe because traffic stays inside the encrypted SSH connection):

```bash
ssh -L 8887:localhost:8888 user@server
```

Then open `http://localhost:8887`.

## 4) Start API container (optional)

The REST API provides a lightweight interface for querying the database without the full `pbi` package. It supports metadata queries, single sequence retrieval, and SQL exploration.

```bash
docker compose build api
docker compose up -d api
```

API is available at `http://localhost:8000`. See [API Reference](../api/overview.md) for endpoints.

---

## Preferred analysis access

- **Preferred**: VS Code + **Dev Containers** attached to the running `analysis` service — provides a full IDE workflow.
  See [Analysis Container Guide](analysis-guide.md) for local and remote connection instructions.
- **Stable fallback**: Jupyter Lab on `http://localhost:8887` (via SSH tunnel if remote).
- **API**: Quick exploration and metadata lookups without loading the full package.

## OOM caution

For large joins/sequence retrieval, use chunked queries and avoid loading very large tables into memory in a single cell.

## Private data note

If you use `private_data/` sources, each source must include host FASTA files (`hosts/<Host_ID>.fna`) matching metadata Host_ID values.
See [Private Data Ingestion](private-data-ingestion.md).

---

## Docker Services

PBI-Scope runs three Docker services:

| Service | Purpose | Port |
|---------|---------|------|
| `pipeline` | Builds/updates the database | — |
| `analysis` | Read-only data access for users (preferred) | 8889 |
| `api` | REST API for metadata queries, sequence retrieval, and SQL exploration | 8000 |

## Volumes and Mounts

```text
+--------------------------- docker-compose ---------------------------+
|                                                                     |
|  named volume: pbi-data  -> mounted at /data in all services        |
|  named volume: pbi-cache -> mounted at /cache in pipeline           |
|                                                                     |
|  bind mount: ./private_data  -> /private-data (rw pipeline, ro analysis)
|  bind mount: ./pipeline_logs -> /pipeline-logs (rw pipeline, ro analysis)
|  bind mount: ./notebooks     -> /workspace (analysis)
|  bind mount: ./outputs -> /results (analysis)
+---------------------------------------------------------------------+
```

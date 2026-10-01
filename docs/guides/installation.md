# Installation Guide

PBI-Scope is designed to run with Docker.

## Requirements

- Docker 20.10+
- Docker Compose 2+
- 225+ GB free disk
- 16 GB RAM minimum (32 GB recommended)

## 1) Clone and configure

```bash
git clone https://github.com/ThibaultSchowing/PBI-Scope.git
cd PBI-Scope

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

!!! warning "First run takes hours"
    On the first execution, downloading public data, resolving/downloading host genomes, merging files, and building BLAST databases are **time-consuming operations** (often 10+ hours depending on data size and network). The pipeline is not stalled — it is processing large genomic files. Subsequent runs are much faster as they reuse cached data.

Pipeline order:

1. public phage download + merge
2. private source validation/ingestion (if present)
3. host resolution/download from NCBI
4. database + indexes + GFF3 + reports
5. BLAST database build (phages, proteins, hosts, private, combined)

## 3) Start analysis container

```bash
docker compose build analysis
docker compose up -d analysis
```

> **Port mapping — quick reference**
> | Scope | Port | Where it is defined |
> |-------|------|---------------------|
> | Inside container | `8888` | `Dockerfile.analysis:57` (`EXPOSE 8888`) · `Dockerfile.analysis:100` (`--port=8888`) · `entrypoint.analysis.sh:33` (`--port=8888`) · healthcheck `Dockerfile.analysis:88` (`curl http://localhost:8888/api`) |
> | On host (mapped) | `8886` | `docker-compose.yml:69` (`"8886:8888"` → `host:container`) |
> Host `8886` → container `8888`. If `8886` is already in use on the host, change the left side in `docker-compose.yml:69` (e.g. `"8887:8888"`) and use that host port in the URL/tunnel below. Jupyter is always `8888` inside the container.

> ⚠️ **Security note**: The analysis container starts Jupyter Lab with authentication
> and XSRF protection **disabled** — this is intentional for local/SSH-tunnelled
> development. See the [Analysis Container Guide](analysis-guide.md#security-notice)
> for a full explanation and hardening steps before exposing the service to a network.

If remote, use an SSH tunnel (safe because traffic stays inside the encrypted SSH connection):

```bash
# host 8886 (docker-compose.yml:69) → container 8888 (Dockerfile.analysis:57)
# forward remote host:8886 to local 8888:
ssh -L 8888:localhost:8886 user@server
# if you changed the host port to 8887 in docker-compose.yml:69, use instead:
# ssh -L 8888:localhost:8887 user@server
```

Then open `http://localhost:8888` (or `http://localhost:8887` if you used the `8887:8888` mapping / `8887:localhost:8887` tunnel).

## 4) Start API container (optional)

The REST API provides a lightweight interface for querying the database without the full `pbi` package. It supports metadata queries, single sequence retrieval, and SQL exploration.

```bash
docker compose build api
docker compose up api
```

API is available at `http://localhost:8000`. See [API Reference](../api/overview.md) for endpoints.

---

## Preferred analysis access

- **Preferred**: VS Code + **Dev Containers** attached to the running `analysis` service — provides a full IDE workflow.
  See [Analysis Container Guide](analysis-guide.md) for local and remote connection instructions.
- **Stable fallback**: Jupyter Lab on `http://localhost:8888` locally (`http://localhost:8886` on the server host via `docker-compose.yml:69` `8886:8888` → `ssh -L 8888:localhost:8886 user@server`). If you remapped the host port to `8887`, use `http://localhost:8887` / `ssh -L 8887:localhost:8887`.
- **API**: Quick exploration and metadata lookups without loading the full package.

## OOM caution

For large joins/sequence retrieval, use chunked queries and avoid loading very large tables into memory in a single cell.

## Private data note

If you use `private_data/` sources, see [Private Data Ingestion](private-data-ingestion.md) for the required layout. Host FASTA files (`hosts/<Host_ID>.fna`) are only required when your metadata uses real `Host_ID` values — sources with `Host_ID`/`Host_name` set to `unknown` run in phage-only mode without a `hosts/` directory.

!!! danger "Example data is ingested — remove it before running"
    The repository ships a synthetic example dataset (`private_data/test_private/`). Use it to observe the expected folder structure, then **rename the folder, empty it, or delete it before running the pipeline** — anything left in `private_data/` WILL be ingested into your database.

    ```bash
    # Inspect the example structure, then remove it (keep the directory)
    ls -la private_data/
    rm -rf private_data/test_private
    ```

---

## Docker Services

PBI-Scope runs three Docker services:

| Service | Purpose | Host → Container Port |
|---------|---------|-----------------------|
| `pipeline` | Builds/updates the database | — |
| `analysis` | Read-only data access for users (preferred) — Jupyter Lab | `8886` → `8888` (`docker-compose.yml:69` `8886:8888`; container `8888` defined in `Dockerfile.analysis:57` `EXPOSE 8888` / `Dockerfile.analysis:100` `--port=8888`) |
| `api` | REST API for metadata queries, sequence retrieval, and SQL exploration | `8000` → `8000` (`docker-compose.yml:44`) |

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



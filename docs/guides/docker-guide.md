# Docker Guide

This guide explains the current PBI container layout.

## Services

- `pipeline`: builds/updates data
- `analysis`: read-only data access for users (preferred)
- `api`: legacy REST layer (limited support)

> ⚠️ **Security notice**: The `analysis` container runs Jupyter Lab with
> authentication and XSRF protection disabled. This is intentional for
> local/SSH-tunnelled development. **Do not expose port 8888 to untrusted
> networks.** See [Analysis Container Guide](analysis-guide.md#-security-notice)
> for details and hardening steps.

## Non-root execution (required setup)

Both the `pipeline` and `analysis` services run as your host user (`UID:GID`) to
prevent Docker from creating root-owned files in bind-mounted directories.

The `user:` field in `docker-compose.yml` reads `UID` and `GID` from the `.env`
file.  **You must set these once after cloning:**

```bash
cp .env.example .env
# Edit .env: fill in NCBI_EMAIL (and NCBI_API_KEY if you have one)

# Append your host UID and GID:
echo "UID=$(id -u)" >> .env
echo "GID=$(id -g)" >> .env
```

Without this, every file the containers write to `./notebooks`, `./outputs`, and
`./pipeline_logs` will be owned by `root` and require `sudo` to edit or delete.

> **macOS note**: Docker Desktop on macOS translates file ownership via a built-in
> shim, so root-owned files are less common there.  Setting `UID`/`GID` is still
> recommended for portability and consistency.

## Volumes and mounts

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

## Minimal run order

```bash
docker compose build pipeline
docker compose run --rm pipeline

docker compose build analysis
docker compose up -d analysis
```

## API note

The API container exists but is not currently supported for sequence-heavy workflows.
Use the analysis container + `pbi` package for production usage.

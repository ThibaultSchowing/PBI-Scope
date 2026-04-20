# Docker Guide

This guide explains the current PBI container layout.

## Services

- `pipeline`: builds/updates data
- `analysis`: read-only data access for users (preferred)
- `api`: legacy REST layer (limited support)

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
|  bind mount: ./analysis_results -> /results (analysis)
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

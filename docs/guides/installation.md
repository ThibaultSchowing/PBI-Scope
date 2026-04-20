# Installation Guide

PBI is designed to run with Docker.

## Requirements

- Docker 20.10+
- Docker Compose 2+
- 225+ GB free disk
- 16 GB RAM minimum (32 GB recommended)

## 1) Clone and configure

```bash
git clone https://github.com/ThibaultSchowing/PBI.git
cd PBI

export NCBI_EMAIL="your.email@example.com"
export NCBI_API_KEY="YOUR_KEY"
```

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

If remote:

```bash
ssh -L 8888:localhost:8888 user@server
```

Then open `http://localhost:8888`.

## Preferred analysis access

- **Preferred**: VS Code + **Dev Containers / VS Code Remote – Containers** attached to the running `analysis` service.
- **Stable fallback**: Jupyter Lab on `http://localhost:8888`.

Jupyter works well, but VS Code is preferred because it provides a full IDE workflow.

## OOM caution

For large joins/sequence retrieval, use chunked queries and avoid loading very large tables into memory in a single cell.

## Private data note

If you use `private_data/` sources, each source must include host FASTA files (`hosts/<Host_ID>.fna`) matching metadata Host_ID values.
See [Private Data Ingestion](private-data-ingestion.md).

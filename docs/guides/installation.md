# Installation Guide

This guide explains how to install and configure PBI using Docker, which is the **primary and recommended execution method**. Docker is required to run the full pipeline, as the host genome download step requires significant disk space and benefits from containerization.

> **Note on local execution**: It is technically possible to run the pipeline locally without Docker (using Snakemake directly), but this is not recommended for the full pipeline due to the large disk space requirements (~225 GB) and complex dependency management. See the [Pipeline Execution Guide](pipeline-execution.md) for local execution details.

## System Requirements

- **Operating System**: Linux/macOS (Windows via WSL2)
- **Docker**: Version 20.10 or later
- **Docker Compose**: Version 2.0 or later
- **Disk Space**: At least **225 GB** of free disk space (for data, cache, and Docker volumes)
- **RAM**: 16 GB minimum (32 GB recommended)
- **Internet**: Stable connection for initial data downloads
- **Time**:
  - First pipeline run (phage metadata only): **~4 hours**
  - Full pipeline (including host genome resolution + download): **~12–18 hours**

> **Tip**: Use `tmux` or another terminal multiplexer to keep your session alive during long pipeline runs, especially when connecting via SSH.

## Step 1: Install Docker

### On Linux (Ubuntu/Debian)

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

### On macOS

Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/). Docker Compose is included.

### On Windows (WSL2)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL2 backend enabled. Run all commands from within your WSL2 terminal.

## Step 2: Clone the Repository

```bash
git clone https://github.com/ThibaultSchowing/PBI.git
cd PBI
```

## Step 3: Configure the Pipeline

Before running, set your NCBI credentials as environment variables (required for host genome downloads). Using environment variables keeps sensitive credentials out of version-controlled config files.

```bash
export NCBI_EMAIL="your.email@example.com"   # Required by NCBI Terms of Service
export NCBI_API_KEY="YOUR_NCBI_API_KEY"      # Optional but strongly recommended (10x faster)
```

Alternatively, copy the provided example and create a `.env` file in the project root (Docker Compose reads it automatically):

```bash
cp .env.example .env
# Edit .env and fill in your credentials
```

> **NCBI API Key**: Get a free API key at https://www.ncbi.nlm.nih.gov/account/ — it increases the download rate limit from 3 to 10 requests/second, significantly speeding up the host genome download stage.

## Step 4: Build and Run the Pipeline Container

### 4.1 Build the Pipeline Image

```bash
docker compose build pipeline
```

### 4.2 Run the Pipeline

```bash
# Run in a tmux session to survive SSH disconnections
tmux new -s pbi-pipeline

docker compose run --rm pipeline
```

**What happens:**

1. **Stage 1 — Phage data** (~4 hours): Downloads and processes phage metadata and FASTA sequences from 14+ databases via PhageScope
2. **Stage 2 — Host resolution** (~12–18 hours): Parses host fields from phage metadata, resolves them to NCBI assemblies, downloads reference genomes

**Output** (stored in the `pbi-data` Docker volume):
- `/data/processed/databases/phage_database_optimized.duckdb` — Main database
- `/data/processed/sequences/all_phages.fasta` (+ `.fai` index)
- `/data/processed/sequences/all_proteins.fasta` (+ `.fai` index)
- `/data/processed/sequences/host_fasta_mapping.json` — Maps host IDs to FASTA file paths
- `/data/processed/reports/` — HTML validation and statistics reports

## Step 5: Connect to the Analysis Container

The analysis container provides a Jupyter Lab environment with direct access to the database and sequences.

### 5.1 Set Up SSH Port Forwarding (for Remote Servers)

If PBI is running on a remote server, forward port 8888 **before** you start the container:

```bash
# On your local machine
ssh -L 8888:localhost:8888 username@your-server-address
```

This maps port 8888 on the remote server to your local machine so you can open Jupyter Lab in your browser at `http://localhost:8888`.

### 5.2 Build and Start the Analysis Container

```bash
# Build the analysis image
docker compose build analysis

# Start in detached mode
docker compose up -d analysis
```

### 5.3 Access Jupyter Lab

Open your browser and navigate to:

```
http://localhost:8888
```

No password is required (local development mode). Start with the demo notebooks in the `notebooks/` directory.

> ⚠️ **Security Warning**: Do not expose port 8888 to untrusted networks. Always use SSH tunneling for remote access.

## Environment Variables

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `DATA_PATH` | Path for API/analysis to find processed data | `/data/processed` | Set automatically in Docker |
| `NCBI_EMAIL` | Your email for NCBI API | — | Yes, for genome downloads |
| `NCBI_API_KEY` | NCBI API key (increases rate limit) | — | Optional but recommended |

`NCBI_EMAIL` and `NCBI_API_KEY` must be set in your shell **before** running Docker Compose, or placed in a `.env` file at the project root. Docker Compose reads the `.env` file automatically and passes both variables into the container. `DATA_PATH` and other internal variables are configured in `docker-compose.yml` and set automatically.

```bash
# Option A: export in your current shell session
export NCBI_EMAIL="your.email@example.com"
export NCBI_API_KEY="your-api-key"

# Option B: .env file in the project root (persists across sessions)
cp .env.example .env
# then edit .env with your values
```

## Troubleshooting

### "No space left on device"

```bash
# Check disk space
df -h

# Clean Docker system (careful: removes unused images and volumes)
docker system prune

# Clean only the Snakemake cache volume (preserves data)
./cleanup_cache.sh
```

### Pipeline Fails Mid-Run

The pipeline uses Snakemake's file-based checkpointing. If it fails, simply re-run:

```bash
docker compose run --rm pipeline
```

Already-completed steps and downloaded files will be reused. You can also use:

```bash
docker compose run --rm pipeline snakemake --cores 4 --use-conda --rerun-incomplete
```

### Jupyter Lab Not Loading

```bash
# Check container status
docker ps | grep analysis

# Check logs
docker compose logs analysis

# Restart
docker compose restart analysis
```

### Pipeline Runs Again After Completion

Ensure that the `pbi-data` volume is intact:

```bash
docker run --rm -v pbi-data:/data alpine ls -lh /data/processed/databases/
```

If the database file is missing, the pipeline needs to re-run.

## Next Steps

- Read [How It Works](how-it-works.md) to understand the pipeline and `pbi` package
- Explore the database with [Analysis Container Usage](analysis-guide.md)
- Check the [Docker Guide](docker-guide.md) for advanced Docker operations


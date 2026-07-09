# Analysis Container Guide

The analysis container is the recommended way to consume PBI-Scope data.

---

## ⚠️ Security notice

The analysis container starts Jupyter Lab with **all authentication disabled**:

- No token (`--ServerApp.token=`)
- No password (`--ServerApp.password=`)
- No XSRF protection (`--ServerApp.disable_check_xsrf=True`)

XSRF (Cross-Site Request Forgery) protection is the browser-level safeguard that
prevents malicious web pages from silently executing code in your Jupyter kernels.
Disabling it means **any page that can reach port 8888 can run arbitrary code**.

This configuration is intentional for **local or SSH-tunnelled development only**.

| Scenario | Safe? |
|---|---|
| Localhost only (port not exposed) | ✅ Safe |
| SSH tunnel from your laptop to the server | ✅ Safe |
| Server port 8888 open to the internet | ❌ **Dangerous** |
| Server on a shared/untrusted LAN | ❌ **Risky** |

**Before exposing the container to a shared or internet-facing network:**

1. Set a real token and/or password:
   - `--ServerApp.token=<your-secret>` (token-based access), **or**
   - `--ServerApp.password=<hashed-password>` (use `jupyter server password` to generate the hash).
2. Remove `--ServerApp.disable_check_xsrf=True`.
3. Place the service behind a reverse proxy (nginx, Caddy, …) with TLS.

The broader infrastructure (no HTTPS, no network isolation by default) is not production-hardened.
Treat it as a researcher workstation tool, not a public service.

---

## Access options

### Preferred: VS Code Dev Containers (local server)

If the container is running **on your local machine**, use
**VS Code Remote – Containers / Dev Containers** to attach directly to the
`analysis` service. This gives you a full IDE (editor, terminal, debugger,
extensions) inside the container.

Requirements: VS Code, the
[Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).

```bash
# Start the container (from your repo root)
docker compose up -d analysis

# In VS Code: open the Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
# → "Dev Containers: Attach to Running Container…"
# → select pbi-analysis
```

Once attached, open `/workspace` — this is the bind-mounted `./notebooks` directory.

---

### Remote server — VS Code via SSH + Dev Containers

If the analysis container is running on a **remote server**, follow these steps.

#### Requirements

- VS Code with two extensions installed locally:
  - [Remote – SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh)
  - [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
- SSH access to the remote server
- The `pbi-analysis` container already running on the remote server
  (`docker compose up -d analysis`)

#### Step 1 — Connect to the remote server via SSH

1. Open the Command Palette → **"Remote-SSH: Connect to Host…"**.
2. Enter `user@your-server` (or pick a pre-configured host from `~/.ssh/config`).
3. VS Code opens a new window connected to the remote server.

#### Step 2 — Attach to the running container

1. In the Remote-SSH window, open the Command Palette →
   **"Dev Containers: Attach to Running Container…"**.
2. Select **`/pbi-analysis`** from the list.
3. VS Code opens another window that is now **inside the container**.

#### Step 3 — Open your notebooks

- Open the folder `/workspace` — this is the bind-mounted `./notebooks` directory
  on the **remote server**.
- If you have a **local clone** of the repository on the server, the `./notebooks`
  directory is already in place and bind-mounted into the container. Edit notebooks
  from within the attached VS Code window (which runs inside the container) and
  commit/push via git on the server as usual.
- If you only have a **copy of the notebooks** (not a full server-side clone),
  copy them to the `./notebooks` directory on the server first — that directory
  is what the container sees as `/workspace`.

#### Step 4 — Install extensions inside the container (optional)

After attaching, VS Code may prompt you to install your usual extensions inside
the container (Python, Jupyter, Pylance, etc.). These installs persist in the
container image layer; reinstalling after a container rebuild is normal.

#### Tip — Working with a local copy of the notebooks

If you do not have SSH access to push files directly, use `scp` or `rsync`:

```bash
# Copy a local notebook to the server's notebooks directory
scp my_analysis.ipynb user@your-server:/path/to/PBI/notebooks/

# Sync the entire local notebooks folder to the server
rsync -avz ./notebooks/ user@your-server:/path/to/PBI/notebooks/
```

---

### Stable fallback: Jupyter Lab via SSH tunnel

Start the container and open an SSH tunnel:

```bash
# On the remote server
docker compose up -d analysis

# On your local machine
ssh -L 8888:localhost:8888 user@your-server
```

Then open `http://localhost:8888` in your local browser.

> The SSH tunnel forwards local port 8888 to the server's port 8888.
> Traffic never leaves the encrypted SSH connection, so this is safe even though
> Jupyter authentication is disabled.

!!! tip "API Access"
    You can also access the REST API remotely via SSH tunnel (`ssh -L 8000:localhost:8000 ...`).
    See [Remote Access](../api/overview.md#remote-access) in the API Reference.

---

## OOM warning

Large joins and sequence materialization can trigger out-of-memory errors.
Use filtering, limits, and batch/iterator patterns.

## Quick Python start

```python
from pbi import quick_connect

retriever = quick_connect()
stats = retriever.get_stats()
print(stats['database'])
```

## Recommended notebooks

- `01_database_exploration.ipynb`
- `02_sequence_retrieval.ipynb`
- `03_ml_streaming.ipynb`
- `08_api_client.ipynb`

---

## Local Execution (Without Docker)

You can run the pipeline locally without Docker. This requires managing conda environments and disk space manually.

```bash
# 1. Install dependencies
conda env create -f workflow/envs/base_environment.yaml
conda activate pbi-env

# Install PBI package
pip install -e .

# 2. Configure NCBI credentials
# Edit workflow/config/config.yaml and set your email and API key

# 3. Run the pipeline
./run_local.sh
# or directly:
snakemake --directory workflow --snakefile workflow/Snakefile \
  --cores 4 --use-conda --printshellcmds
```

**Note**: The first run downloads ~50 GB of phage data and then attempts to download ~5,500 bacterial host genomes. Total runtime is similar to Docker (~4h for phages, ~12–18h for hosts).

---

## Docker: force-rerun examples

Use `docker compose run --rm pipeline` and pass a Snakemake command override:

```bash
# Force re-run CSV download/merge related rule(s) by rule name
docker compose run --rm pipeline \
  snakemake --cores all --use-conda --printshellcmds \
  --directory /app/workflow --snakefile /app/workflow/Snakefile \
  --forcerun download_all_tsvs merge_phage_metadata_tsvs

# Force host resolution/download rule
docker compose run --rm pipeline \
  snakemake --cores all --use-conda --printshellcmds \
  --directory /app/workflow --snakefile /app/workflow/Snakefile \
  --forcerun download_host_genomes

# Force host resolution and ignore persisted token-resolution cache
docker compose run --rm pipeline \
  snakemake --cores all --use-conda --printshellcmds \
  --directory /app/workflow --snakefile /app/workflow/Snakefile \
  --forcerun download_host_genomes \
  --config reuse_host_resolution_cache=false
```

---

## Re-executing the Pipeline

Snakemake re-runs a task when:

- One or more output files are missing
- An input file is newer than an output file
- The rule implementation changed
- You explicitly force it (`--forcerun`, `--forceall`)

If none of the above happens, Snakemake skips the rule.

### Host resolution cache

Host token resolution persists a cache file (`pipeline_logs/csv/host_token_resolution_cache.json`). When `reuse_host_resolution_cache: true` (default), already-resolved host tokens are reused on later runs.

To force a full refresh:

```bash
snakemake --cores 4 --use-conda \
  --forcerun download_host_genomes \
  --config reuse_host_resolution_cache=false
```

---

## Tracking Download Progress

During execution, you'll see progress updates:

```
🚀 Starting optimized host genome download pipeline
📥 Starting downloads for 5,529 species

Progress: ████████░░░░░░░░░░ 1,234/5,529 (22.3%)
✅ Success: 1,100 | ❌ Failed: 89 | 📦 Cached: 45
ETA: 1.2 hours | Rate: 15.3 genomes/min
```

**Key Metrics:**

- **Success**: Downloaded successfully
- **Failed**: Could not download (see failure log)
- **Cached**: Already in cache (no re-download needed)
- **Rate**: Current download speed

---

## Troubleshooting

### High Failure Rate

**Symptoms**: >20% failures in download

```bash
# Check failure categories
cat data/logs/failed_downloads.txt | grep "Category:"
```

**Solutions:**

- If "No assembly found": Normal for some species, may need manual curation
- If "Download failed": Check network, increase retries in config
- If "GTDB identifiers": Expected, these are filtered out automatically

### Slow Download Speed

**Symptoms**: <5 genomes/minute

```bash
# Check rate limiting
grep "Rate limiter" logs/host_download.log
```

**Solutions:**

1. Add NCBI API key to config (increases from 3 to 10 req/sec)
2. Increase `max_concurrent` in config
3. Check network bandwidth

### Incomplete Download

```bash
# Resume from checkpoint (cache prevents re-downloads)
snakemake --cores 4 --use-conda --rerun-incomplete
```

The cache system ensures completed downloads aren't repeated.

---

## Best Practices

### For Production Runs

1. **Set NCBI Email**: Required by NCBI Terms of Service
2. **Use API Key**: Significantly faster (3x-10x)
3. **Enable Cache**: Avoid re-downloading on failures
4. **Monitor Progress**: Use `--verbose` flag for detailed logs

```bash
# Production execution with logging
snakemake --cores 8 --use-conda \
    --config ncbi_email=your@email.com ncbi_api_key=YOUR_KEY \
    2>&1 | tee logs/pipeline_$(date +%Y%m%d).log
```

### For Development/Testing

```bash
# Test run with 100 species
snakemake --cores 4 --use-conda --config limit=100
```

See [Pipeline Logs](logging.md) for detailed log file reference.

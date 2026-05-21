# Analysis Container Guide

The analysis container is the recommended way to consume PBI data.

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

1. Set a real token: replace `--ServerApp.token=` with `--ServerApp.token=<your-secret>`.
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
  on the remote server.
- If you have a **local clone** of the repository, the `./notebooks` directory on
  the server and your local clone share the same content via bind mount. You can
  edit notebooks locally and they appear instantly inside the container, or edit
  them inside the container and push/pull via git on the server.
- If you only have a **copy of the notebooks** (not a full clone), copy them to
  the `./notebooks` directory on the server — that directory is the container's
  `/workspace`.

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
- `00_pipeline_logs.ipynb`

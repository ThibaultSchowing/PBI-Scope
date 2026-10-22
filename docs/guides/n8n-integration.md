# n8n Workflows

PBI-Scope includes an optional **n8n** workflow automation container. n8n lets you build visual workflows on top of the PBI REST API without writing code — for example, screening an unknown sequence with BLAST and alerting on the result, running a daily data digest, or watching the API health.

> **Important:** n8n runs **only on the remote server** — it is not part of local development. It talks to the API over the internal Docker network at `http://api:8000`. You reach it from your laptop through an SSH tunnel.

## What it enables

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| **BLAST screening** | Webhook receives a sequence | Queues a BLAST job (`POST /blast/jobs`), polls until done, annotates top hits via `/phage-metadata`, sends a Slack/email report |
| **API watchdog** | Schedule (hourly) | Polls `GET /health`, alerts when the API is degraded or BLAST is unavailable |

Workflows are committed to the repo under `n8n/workflows/` and imported into the n8n UI:
- `blast-screening.json` — webhook-driven BLAST screening + alerts
- `api-watchdog.json` — hourly health watchdog

## Prerequisites

On the remote server, copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Required new variables:

| Variable | Purpose | How to generate |
|----------|---------|-----------------|
| `PBI_API_KEY` | API key required to call authenticated endpoints | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `N8N_ENCRYPTION_KEY` | n8n credential encryption key | `python -c "import secrets; print(secrets.token_hex(24))"` |

See `.env.example` for the full list (also `NCBI_EMAIL`, `UID`, `GID`).

## 1) Start the API and n8n

Build and start both services (run on the **server**):

```bash
# Build the API image (done once, or after API changes)
docker compose build api

# Start API + n8n in the background
docker compose up -d api n8n
```

Check they are running:

```bash
docker compose ps
```

You should see `pbi-api` and `pbi-n8n` both `Up`.

## 2) Connect to n8n from your laptop (SSH port forwarding)

Because n8n only runs on the server, forward its port through SSH. From your **laptop**:

```bash
# Forward local 5678 → server host 5678 → container 5678
ssh -L 5678:localhost:5678 user@your-server
```

Keep that SSH session open. Then open in your browser:

```
http://localhost:5678
```

n8n will prompt you to create an admin account on first login. After logging in, import the workflows:

1. Go to **Workflows** → **Import**
2. Select `n8n/workflows/blast-screening.json` (and/or `api-watchdog.json`) from a local clone of the repo
3. In each workflow, configure the **Slack** (or Email) credential node and set your notify channel (e.g. `#phage-alerts`)
4. Save and toggle **Active**

> The n8n HTTP Request nodes already target `http://api:8000` (internal network) and send `X-API-Key` from the `PBI_API_KEY` env var, so no further config is needed once the env is set.

## 3) Test the API endpoints directly

You can test the new BLAST job endpoints from your laptop through the same SSH tunnel (forward port 8000 as well):

```bash
# In a second terminal on your laptop:
ssh -L 8000:localhost:8000 user@your-server
```

### Without auth (PBI_API_KEY set) — expect 401

```bash
curl -X POST http://localhost:8000/blast/jobs \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ACGT", "program": "blastn"}'
# → 401 {"detail": "Missing or invalid API key"}
```

### With auth — queue a job (202)

```bash
curl -X POST http://localhost:8000/blast/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-PBI_API_KEY>" \
  -d '{"sequence": "ACGT", "program": "blastn", "max_hits": 5}'
# → 202 {"job_id": "<uuid>", "status": "queued"}
```

### Poll the job

```bash
curl -H "X-API-Key: <your-PBI_API_KEY>" \
  "http://localhost:8000/blast/jobs/<job_id>"
# → {"job_id": "...", "status": "done", "hits": 3, "results": [...]}
```

Health (no key required):

```bash
curl http://localhost:8000/health
# → {"status": "healthy", ...}
```

The interactive API docs (with the `X-API-Key` Authorize button) are at:

```
http://localhost:8000/docs
```

## 4) Test the n8n screening workflow

1. Make sure `blast-screening.json` is imported and **Active** in n8n.
2. Copy the webhook URL shown on the workflow's Webhook node (e.g. `http://localhost:5678/webhook/blast-screening` through your tunnel).
3. POST a sequence to it:

```bash
curl -X POST http://localhost:5678/webhook/blast-screening \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ACGT...", "program": "blastn", "db": "phages", "notify_to": "#phage-alerts"}'
```

n8n queues the BLAST job, polls until completion, annotates the top hit, and posts a summary to Slack.

## Architecture

```text
+----------------+      internal network      +----------------+
|   Your laptop  | <---------- SSH ---------> |   Server host  |
|  (browser,     |   -L 5678:localhost:5678   |  docker-compose|
|   curl, ssh)   |   -L 8000:localhost:8000   +----------------+
+----------------+                                       |
                                                         v
                                          +-------------+-------------+
                                          |      n8n container        |
                                          |  port 5678 → 5678         |
                                          |  workflows (imported JSON) |
                                          +-------------+-------------+
                                                         |
                                                         | http://api:8000 + X-API-Key
                                                         v
                                          +-------------+-------------+
                                          |      api container        |
                                          |  port 8000 → 8000         |
                                          |  /blast/jobs, /health ... |
                                          +---------------------------+
```

## Security

- n8n is **not exposed to the internet**. Access it only via the SSH tunnel (`ssh -L 5678:localhost:5678`).
- The API requires `X-API-Key` on all routes except `/`, `/health`, and the OpenAPI docs (`/docs`, `/openapi.json`). n8n sends the key automatically from `PBI_API_KEY`.
- If you ever expose n8n or the API beyond the tunnel, put them behind a reverse proxy with HTTPS and authentication first.

## See also

- [API Reference](../api/overview.md) — all endpoints including `/blast/jobs`
- [Docker Guide](docker-guide.md) — service table and port mapping
- [Installation Guide](installation.md) — `.env`, UID/GID, first run
- `n8n/README.md` — repo-level notes on the committed workflow JSON files

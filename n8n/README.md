# n8n + PBI-Scope API

Workflow automation on top of the PBI REST API. **n8n runs only on the remote
server** (it is not part of local development). It talks to the API over the
internal Docker network at `http://api:8000`.

## Deploy

1. Copy `.env.example` to `.env` on the server and fill in:
   - `PBI_API_KEY` — random string (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
   - `N8N_ENCRYPTION_KEY` — random string (e.g. `python -c "import secrets; print(secrets.token_hex(24))"`)

2. Bring up the stack (server only):
   ```bash
   docker compose up -d api n8n
   ```

3. Open n8n at `http://<server>:5678`, create your admin account, then import
   the workflows under `n8n/workflows/`:
   - `blast-screening.json` — webhook-driven BLAST screening + Telegram alert
   - `api-watchdog.json` — hourly `/health` poll + degraded alert

4. **Create the API key credential** (one-time setup):
   - In n8n, go to **Credentials** → **New** → **Header Auth**
   - **Name**: `X-API-Key`
   - **Value**: your `PBI_API_KEY` from `.env`
   - Save as "PBI API Key"
   - Open each HTTP Request node in the imported workflows and select
     this credential under **Authentication → Header Auth**

5. In each imported workflow, configure the **Telegram credentials** node
   (bot token from @BotFather) and set `notify_to` to your chat ID.

## How a screening run works

1. POST a JSON body to the webhook URL (shown in n8n after saving the
   `blast-screening` workflow):
   ```json
   {
     "sequence": "ACGT...",
     "program": "blastn",
     "db": "phages",
     "notify_to": "<your-telegram-chat-id>"
   }
   ```
2. n8n calls `POST /blast/jobs` with `X-API-Key`, gets a `job_id` (202).
3. After 5s it polls `GET /blast/jobs/{id}` until `done`/`failed`.
4. On `done`: fetches metadata for the top hit via `GET /phage-metadata`,
   formats a report, and sends it to Telegram.
5. On `failed`: sends the error to Telegram.

## API changes (see `api/app.py`)

- `X-API-Key` auth (env `PBI_API_KEY`); exempts `/`, `/health`, docs/OpenAPI so
  Docker HEALTHCHECK and n8n spec import keep working.
- `POST /blast/jobs` → `202 {job_id}`; `GET /blast/jobs/{id}` → polling;
  `GET /blast/jobs` → list. Jobs run in a threadpool (no event-loop blocking),
  TTL-evicted after 1h.
- `POST /blast/search` remains for synchronous/small queries.
- OpenAPI exposes an `ApiKeyHeader` scheme at `/openapi.json` for spec import.

## Local development

These changes are unit-testable locally without Docker or n8n:

```bash
python -m pytest tests/ -v
```

The `n8n/` directory itself is not exercised locally; validate the workflows
by importing them into a running n8n instance on the server.

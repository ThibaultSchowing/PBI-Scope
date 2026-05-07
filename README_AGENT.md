# PBI Agentic Architecture

This document explains how the agentic architecture works and can be used as a base for a future documentation page.

## Scope

The agentic service is implemented in `agent/` and exposes a chat API over PBI data and pipeline artifacts.

- Runtime entrypoint: `agent/app.py`
- Tool implementations: `agent/tools/*.py`
- System prompt: `agent/prompts/system_prompt.txt`
- Container image: `agent/Dockerfile.agent`

## High-level architecture

The service is a FastAPI application that builds a LangGraph ReAct agent at startup.

1. FastAPI receives user messages on `POST /chat/stream`.
2. A LangChain/Ollama chat model is initialized.
3. The model is bound to a curated toolset.
4. Responses are streamed to the UI through Server-Sent Events (SSE).
5. Tool calls are surfaced as `tool_start` / `tool_end` events.

The system prompt is loaded from `system_prompt.txt` and enriched with the live DuckDB schema (`{schema}` placeholder replacement), so the agent can write valid SQL immediately.

## Startup lifecycle

At startup, the service:

- Builds the agent and registers tools.
- Loads the DB schema for prompt/tool context.
- Starts asynchronous warm-up for:
  - DuckDB SQL connection (`duckdb_query` tool path)
  - PBI retriever connection (`pbi_retriever` tool path)

This reduces first-query latency and gives clearer loading/error states to users.

## Tooling model

The agent uses **four tools** to keep tool selection simple for the LLM:

1. `duckdb_query`  
   Read-only SQL over the PBI DuckDB.
2. `pipeline_logs`  
   Browse **all** pipeline artifacts under `/pipeline-logs/`: log files, HTML/CSV reports,
   and intermediate CSVs. This single tool replaces the previous `log_explorer`,
   `pipeline_report`, and `host_retrieval_log` tools to eliminate routing confusion.
3. `pbi_retriever`  
   Curated helper actions (`get_stats`, `get_*_by_id`, host listing).
4. `query_router`  
   Fallback router when the model is uncertain about the right tool.

### Why one tool for all pipeline files?

Previously three separate tools (`log_explorer`, `pipeline_report`, `host_retrieval_log`)
handled pipeline artifacts, causing the LLM to route incorrectly or hallucinate report
lists instead of calling the tool. Merging them into `pipeline_logs` means there is
only one obvious choice for any question about pipeline output files.

**For reports**, the LLM must always start with:
```json
{"action": "list"}
```
This lists all available files. Then it can display a specific report with:
```json
{"action": "show", "path": "reports/host_status_report.csv"}
```

## Information retrieval flow

### Normal flow

The model emits a tool call through LangGraph. Tool output is returned to the model, and the final response is streamed to the user.

### Recovery flow for malformed output

If the model prints a raw JSON object instead of making a proper framework tool call, the app detects this and executes the tool directly.

Recovery logic:

1. Parse the model output (bare JSON, code-fenced JSON, Python dict literal, or echoed `tool_name({...})`).
2. Detect tool intent from explicit tool name, action field, or query field.
3. Translate legacy field names (e.g. `name` → `path` for old `pipeline_report` echoes).
4. Execute the tool and stream its result.

This prevents dead-end assistant replies and improves retrieval reliability.

## Action-to-tool resolution

All log/report/host actions now map unambiguously to `pipeline_logs`. There are no
overlapping tool candidates to disambiguate.

| Action | Tool |
|--------|------|
| `list`, `show`, `read`, `head`, `tail`, `search`, `filter_level`, `summary` | `pipeline_logs` |
| `list_failures`, `get_status`, `get_fasta_qc`, `get_download_log`, `get_host_mapping_log` | `pipeline_logs` |
| `get_stats`, `get_phage_by_id`, `get_protein_by_id`, `list_hosts`, `list_failed_hosts` | `pbi_retriever` |

## Security and guardrails

Key protections in the tool layer:

- SQL tool is read-only and action-restricted.
- File tools validate paths stay under configured roots (path-traversal safe).
- Log/report reads are size-capped (`AGENT_MAX_LOG_SIZE_KB`, default 512 KB).
- Errors are returned as user-safe messages without leaking internal stack traces.

## Streaming protocol

`/chat/stream` emits SSE events:

- `token` for model/tool text
- `tool_start` when a tool begins
- `tool_end` when a tool ends
- `error` for recoverable internal failures
- `[DONE]` terminator

This provides transparent UI feedback during retrieval and reasoning.

## Configuration

Primary environment variables:

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `DATA_PATH`
- `PBI_LOGS_DIR`
- `AGENT_MAX_LOG_SIZE_KB`
- `AGENT_SQL_ROW_LIMIT`
- `AGENT_API_KEY` (optional auth for `/chat/stream`)

## How to evolve this architecture

When adding or modifying tools:

1. Keep the tool count low — fewer choices reduce LLM routing errors.
2. Update the system prompt to reflect new tool names and actions.
3. Update `_ACTION_TO_TOOLS` in `app.py` for new actions.
4. Preserve SSE observability (`tool_start` / `tool_end`).
5. Prefer deterministic behavior over heuristic-only routing.

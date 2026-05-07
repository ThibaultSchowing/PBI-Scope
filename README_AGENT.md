# PBI Agentic Architecture (agentic branch)

This document explains how the agentic architecture works in this branch and can be used as a base for a future documentation page.

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

The agent uses six tools, each with a narrow responsibility:

1. `duckdb_query`  
   Read-only SQL over the PBI DuckDB.
2. `log_explorer`  
   Generic pipeline log browsing/search/filtering/summaries under `/pipeline-logs`.
3. `pbi_retriever`  
   Curated helper actions (`get_stats`, `get_*_by_id`, host listing).
4. `host_retrieval_log`  
   Specialized host retrieval diagnostics (status/failures/QC/mapping log).
5. `pipeline_report`  
   Access to pipeline report files (`/pipeline-logs/reports`) for list/summary/read.
6. `query_router`  
   Fallback router when the model is uncertain about the right tool.

## Information retrieval flow

### Normal flow

The model emits a tool call through LangGraph. Tool output is returned to the model, and the final response is streamed to the user.

### Recovery flow for malformed output

If the model prints a raw JSON object instead of making a proper framework tool call, the app detects this and executes the tool directly.

Recovery logic:

1. Parse bare JSON output.
2. Detect tool intent from action/query fields.
3. Resolve the target tool.
4. Execute the tool and stream its result.

This prevents dead-end assistant replies and improves retrieval reliability.

## Action-to-tool resolution and overlap handling

Some actions overlap across tools (`list`, `read`, `summary` in `log_explorer` and `pipeline_report`).

Resolution strategy:

- Prefer explicit argument shape:
  - log-focused arguments (`path`, `pattern`, `context_lines`, `start_line`, `end_line`, `level`) → `log_explorer`
  - report-focused arguments (`name`, `n_rows`) → `pipeline_report`
- Use path/file hints when present:
  - `logs/...` or `*.log` → `log_explorer`
  - `*.csv`, `*.html`, `*.htm` → `pipeline_report`
- Keep deterministic default fallback for ambiguous bare actions.

This improves retrieval precision without changing external API contracts.

## Security and guardrails

Key protections in the tool layer:

- SQL tool is read-only and action-restricted.
- File tools validate paths stay under configured roots.
- Log/report reads are size-capped.
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

1. Keep each tool domain-focused and read-only where possible.
2. Update prompt instructions so tool selection stays accurate.
3. Update recovery action-resolution logic for new actions or overlaps.
4. Preserve SSE observability (`tool_start` / `tool_end`).
5. Prefer deterministic behavior over heuristic-only routing.

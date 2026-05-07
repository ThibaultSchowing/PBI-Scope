# PBI Agent Architecture (Clean Start)

This service is intentionally minimal and pedagogic.

## Scope

- Runtime entrypoint: `agent/app.py`
- Tool implementations: `agent/tools/sql_tool.py`
- System prompt: `agent/prompts/system_prompt.txt`
- Container image: `agent/Dockerfile.agent`

## Architecture

The agent is a LangGraph ReAct workflow with:

- One model: Ollama `llama3.1:8b`
- One tool: `duckdb_query`

No routing tool, no log/report tools, and no tool-recovery fallback layer are used.

## Request flow

1. FastAPI receives `POST /chat/stream`
2. Conversation is passed to the LangGraph agent
3. Agent can call only `duckdb_query`
4. SSE stream returns `token`, `tool_start`, `tool_end`, and `[DONE]`

## Why this reset

The previous architecture introduced too many tool choices and recovery heuristics,
which made behavior harder to reason about and teach.

This clean start keeps one deterministic retrieval path and is ready for gradual,
pedagogic improvements later.

## Configuration

Main environment variables:

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `DATA_PATH`
- `AGENT_SQL_ROW_LIMIT`
- `AGENT_API_KEY`

## Keep unchanged

- The Ollama service/container remains in place
- The default model remains `llama3.1:8b`

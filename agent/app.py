"""
app.py
======

FastAPI application for the PBI agentic chat service.

Endpoints
---------
GET  /          → serve the chat UI (static/index.html)
GET  /health    → liveness check
POST /chat/stream → SSE stream of agent tokens / tool events

The agent is built with LangChain's tool-calling API around a local
Ollama-hosted Llama 3.1 model.  The system prompt is loaded from
``prompts/system_prompt.txt`` and the DuckDB schema is injected at
startup so the LLM has full context from the first message.

Server-Sent Events (SSE) format
--------------------------------
Each event is a JSON-encoded line prefixed with ``data: ``.

  data: {"type": "token",      "content": "..."}
  data: {"type": "tool_start", "tool": "duckdb_query", "input": "..."}
  data: {"type": "tool_end",   "tool": "duckdb_query"}
  data: {"type": "error",      "content": "..."}
  data: [DONE]

Environment variables
---------------------
OLLAMA_BASE_URL         Ollama HTTP base URL (default: http://ollama:11434)
OLLAMA_MODEL            Model tag to use      (default: llama3.1:8b)
DATA_PATH               Base path for DuckDB  (default: /data/processed)
PBI_LOGS_DIR            Log directory root    (default: /pipeline-logs)
AGENT_MAX_LOG_SIZE_KB   Max log read in KB    (default: 512)
AGENT_SQL_ROW_LIMIT     Max SQL result rows   (default: 500)
AGENT_API_KEY           Optional bearer token for the /chat/stream endpoint.
                        When set, requests without a matching Authorization header
                        are rejected with 401.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("agent.app")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
AGENT_API_KEY: Optional[str] = os.environ.get("AGENT_API_KEY") or None

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_system_prompt(schema: str) -> str:
    """Load system_prompt.txt and interpolate the DB schema."""
    prompt_path = _PROMPTS_DIR / "system_prompt.txt"
    try:
        template = prompt_path.read_text(encoding="utf-8")
        return template.format(schema=schema or "(database not yet available)")
    except FileNotFoundError:
        logger.warning("system_prompt.txt not found at %s", prompt_path)
        return (
            "You are a helpful assistant for the PBI phage-bacteria interactions project."
        )


def _build_agent():
    """
    Build and return a LangGraph ReAct agent (CompiledGraph).

    This is called once at startup.  Errors are logged but do not prevent
    the FastAPI app from starting — the /health endpoint will report
    the agent as unavailable, and /chat/stream will return an error
    message to the client.

    Uses ``langgraph.prebuilt.create_react_agent`` — the successor to the
    removed ``langchain.agents.AgentExecutor`` — together with
    ``langchain-core >=1.2.22`` which contains the security fix for path
    traversal in legacy ``load_prompt`` functions.
    """
    try:
        from langgraph.prebuilt import create_react_agent
        from langchain_ollama import ChatOllama

        from agent.tools.log_tool import LogExplorerTool
        from agent.tools.pbi_tool import PBIRetrieverTool
        from agent.tools.sql_tool import DuckDBQueryTool, get_db_schema

        schema = get_db_schema()
        system_prompt = _load_system_prompt(schema)

        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0,
        )

        tools = [DuckDBQueryTool(), LogExplorerTool(), PBIRetrieverTool()]

        # prompt injects the system prompt as the first system message.
        agent = create_react_agent(llm, tools, prompt=system_prompt)

        logger.info("Agent initialised with model '%s' at %s", OLLAMA_MODEL, OLLAMA_BASE_URL)
        return agent

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to build agent: %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

_agent_executor = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Build the agent at startup and clean up on shutdown."""
    global _agent_executor  # noqa: PLW0603
    _agent_executor = _build_agent()
    yield
    # Nothing to clean up currently; add retriever.close() here if needed.


app = FastAPI(
    title="PBI Agent",
    description="Agentic chat over the PBI phage-bacteria interactions database",
    version="0.1.0",
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _check_auth(request: Request) -> None:
    if AGENT_API_KEY is None:
        return
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or auth_header[7:] != AGENT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_agent(
    executor, message: str, chat_history: list
) -> AsyncIterator[str]:
    """
    Yield SSE-formatted strings produced by the LangGraph agent.

    Uses ``astream_events`` (LangChain ≥ 0.2) to emit token-level and
    tool-level events.  LangGraph agents expect the full conversation as a
    ``messages`` list; the current user turn is appended here.
    """
    from langchain_core.messages import HumanMessage

    try:
        messages = list(chat_history) + [HumanMessage(content=message)]
        async for event in executor.astream_events(
            {"messages": messages},
            version="v2",
        ):
            kind = event.get("event", "")
            name = event.get("name", "")

            # LLM token chunks
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    token = ""
                    if hasattr(chunk, "content"):
                        token = chunk.content
                    elif isinstance(chunk, dict):
                        token = chunk.get("content", "")
                    if token:
                        yield _sse({"type": "token", "content": token})

            # Tool start
            elif kind == "on_tool_start":
                tool_input = event.get("data", {}).get("input", "")
                yield _sse(
                    {
                        "type": "tool_start",
                        "tool": name,
                        "input": str(tool_input)[:300],
                    }
                )

            # Tool end
            elif kind == "on_tool_end":
                yield _sse({"type": "tool_end", "tool": name})

    except Exception as exc:  # noqa: BLE001
        logger.error("Agent stream error: %s", exc, exc_info=True)
        # Return a generic message to the client; do not expose the stack trace.
        yield _sse({"type": "error", "content": "An internal error occurred. Please try again."})

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Serve the chat UI."""
    html_path = _STATIC_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Chat UI not found</h1>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "agent": "ready" if _agent_executor is not None else "unavailable",
        "model": OLLAMA_MODEL,
        "ollama_url": OLLAMA_BASE_URL,
    }


@app.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """
    Stream agent responses as Server-Sent Events.

    The client sends the current message and the conversation history.
    The server streams token chunks and tool-call notifications back.
    """
    _check_auth(request)

    if _agent_executor is None:
        async def _err():
            yield _sse(
                {
                    "type": "error",
                    "content": (
                        "Agent is not available. "
                        "Check that the Ollama service is running and the model is pulled."
                    ),
                }
            )
            yield "data: [DONE]\n\n"

        return StreamingResponse(_err(), media_type="text/event-stream")

    # Convert client history to LangChain message objects
    from langchain_core.messages import AIMessage, HumanMessage

    lc_history = []
    for msg in (body.history or []):
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc_history.append(AIMessage(content=msg.content))

    return StreamingResponse(
        _stream_agent(_agent_executor, body.message, lc_history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

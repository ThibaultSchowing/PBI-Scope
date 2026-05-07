"""FastAPI app for a minimal LangGraph + LangChain PBI agent."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("agent.app")

OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
AGENT_API_KEY: Optional[str] = os.environ.get("AGENT_API_KEY") or None

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_STATIC_DIR = Path(__file__).parent / "static"

_agent_executor = None
_agent_tools: list = []
_db_preload_status = "pending"


def _load_system_prompt(schema: str) -> str:
    """Load system prompt and inject database schema."""
    prompt_path = _PROMPTS_DIR / "system_prompt.txt"
    try:
        template = prompt_path.read_text(encoding="utf-8")
        return template.replace("{schema}", schema or "(database not yet available)")
    except FileNotFoundError:
        logger.warning("system_prompt.txt not found at %s", prompt_path)
        return "You are a helpful assistant for the PBI project."


def _build_agent():
    """Build and return ``(agent, tools)`` for a basic one-tool LangGraph agent."""
    try:
        from langchain_ollama import ChatOllama
        from langgraph.prebuilt import create_react_agent

        from agent.tools.sql_tool import DuckDBQueryTool, get_db_schema

        schema = get_db_schema()
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0,
        )
        tools = [DuckDBQueryTool(db_schema=schema)]
        agent = create_react_agent(llm, tools, prompt=_load_system_prompt(schema))
        logger.info("Agent initialised with model '%s' at %s", OLLAMA_MODEL, OLLAMA_BASE_URL)
        return agent, tools
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to build agent: %s", exc, exc_info=True)
        return None, []


async def _preload_database() -> None:
    """Warm up the DuckDB connection in the background."""
    global _db_preload_status  # noqa: PLW0603
    _db_preload_status = "loading"
    try:
        from agent.tools.sql_tool import preload_db_conn

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, preload_db_conn)
        _db_preload_status = "ready"
    except Exception as exc:  # noqa: BLE001
        _db_preload_status = "error"
        logger.error("Database preload failed: %s", exc, exc_info=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Build the agent at startup."""
    global _agent_executor, _agent_tools  # noqa: PLW0603
    _agent_executor, _agent_tools = _build_agent()
    asyncio.create_task(_preload_database())
    yield


app = FastAPI(
    title="PBI Agent",
    description="Minimal agentic chat over the PBI DuckDB database",
    version="0.1.0",
    lifespan=_lifespan,
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None


def _check_auth(request: Request) -> None:
    if AGENT_API_KEY is None:
        return
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or auth_header[7:] != AGENT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_agent(executor, message: str, chat_history: list) -> AsyncIterator[str]:
    """Stream model tokens and tool events as SSE."""
    from langchain_core.messages import AIMessage, HumanMessage

    try:
        messages = list(chat_history) + [HumanMessage(content=message)]
        async for event in executor.astream_events({"messages": messages}, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                token = getattr(chunk, "content", "") if chunk is not None else ""
                if isinstance(token, str) and token:
                    yield _sse({"type": "token", "content": token})

            elif kind == "on_tool_start":
                tool_input = event.get("data", {}).get("input", "")
                yield _sse({"type": "tool_start", "tool": name, "input": str(tool_input)[:300]})

            elif kind == "on_tool_end":
                yield _sse({"type": "tool_end", "tool": name})

            elif kind == "on_chain_end" and not event.get("parent_ids"):
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    final_msgs = output.get("messages", [])
                    for msg in reversed(final_msgs):
                        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                            content = msg.content
                            if isinstance(content, str) and content.strip():
                                yield _sse({"type": "token", "content": content})
                            break
    except Exception as exc:  # noqa: BLE001
        logger.error("Agent stream error: %s", exc, exc_info=True)
        yield _sse({"type": "error", "content": "An internal error occurred. Please try again."})

    yield "data: [DONE]\n\n"


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
        "database": _db_preload_status,
        "model": OLLAMA_MODEL,
        "ollama_url": OLLAMA_BASE_URL,
        "tools": [getattr(tool, "name", "unknown") for tool in _agent_tools],
    }


@app.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """Stream agent responses as SSE."""
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

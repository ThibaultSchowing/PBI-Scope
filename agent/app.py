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
        return template.replace("{schema}", schema or "(database not yet available)")
    except FileNotFoundError:
        logger.warning("system_prompt.txt not found at %s", prompt_path)
        return (
            "You are a helpful assistant for the PBI phage-bacteria interactions project."
        )


def _build_agent():
    """
    Build and return ``(agent, tools)`` — a LangGraph ReAct agent (CompiledGraph)
    and the list of registered LangChain tools.

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
        from agent.tools.host_log_tool import HostRetrievalLogTool
        from agent.tools.report_tool import PipelineReportTool
        from agent.tools.routing_tool import QueryRouterTool

        schema = get_db_schema()
        system_prompt = _load_system_prompt(schema)

        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0,
        )

        tools = [
            DuckDBQueryTool(db_schema=schema),
            LogExplorerTool(),
            PBIRetrieverTool(),
            HostRetrievalLogTool(),
            PipelineReportTool(),
            QueryRouterTool(),
        ]

        # prompt injects the system prompt as the first system message.
        agent = create_react_agent(llm, tools, prompt=system_prompt)

        logger.info("Agent initialised with model '%s' at %s", OLLAMA_MODEL, OLLAMA_BASE_URL)
        return agent, tools

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to build agent: %s", exc, exc_info=True)
        return None, []


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

_agent_executor = None
_agent_tools: list = []


async def _preload_databases() -> None:
    """
    Warm up both database connections in background threads so they are
    ready before the first user query arrives.  The large PBI database files
    can take up to 5 minutes to open; running the load at startup means the
    agent only needs to wait once, rather than on the first tool call.
    """
    try:
        from agent.tools.pbi_tool import preload_retriever
        from agent.tools.sql_tool import preload_db_conn

        loop = asyncio.get_running_loop()
        await asyncio.gather(
            loop.run_in_executor(None, preload_retriever),
            loop.run_in_executor(None, preload_db_conn),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Database preload failed: %s", exc, exc_info=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Build the agent at startup and clean up on shutdown."""
    global _agent_executor, _agent_tools  # noqa: PLW0603
    _agent_executor, _agent_tools = _build_agent()
    # Start DB pre-loading in the background — do not await so the app
    # finishes starting up immediately while the heavy files load.
    # Store the task reference to prevent it being garbage-collected and to
    # log any unexpected exception that escapes _preload_databases.
    _preload_task = asyncio.create_task(_preload_databases())

    def _on_preload_done(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "Unhandled exception in database preload task: %s",
                task.exception(),
                exc_info=task.exception(),
            )

    _preload_task.add_done_callback(_on_preload_done)
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


# ---------------------------------------------------------------------------
# JSON tool-call detection and recovery helpers
# ---------------------------------------------------------------------------

# Maps action values to candidate tool names that handle them.
# Used to identify which tool a model-generated JSON invocation targets.
_ACTION_TO_TOOLS: dict[str, list[str]] = {
    # host_retrieval_log
    "list_failures": ["host_retrieval_log"],
    "get_status": ["host_retrieval_log"],
    "get_fasta_qc": ["host_retrieval_log"],
    "get_download_log": ["host_retrieval_log"],
    "get_host_mapping_log": ["host_retrieval_log"],
    # pbi_retriever
    "get_stats": ["pbi_retriever"],
    "get_phage_by_id": ["pbi_retriever"],
    "get_protein_by_id": ["pbi_retriever"],
    "list_hosts": ["pbi_retriever"],
    "list_failed_hosts": ["pbi_retriever"],
    # pipeline_report / log_explorer overlap
    "list": ["pipeline_report", "log_explorer"],
    "summary": ["pipeline_report", "log_explorer"],
    "read": ["pipeline_report", "log_explorer"],
    # log_explorer-exclusive actions
    "head": ["log_explorer"],
    "tail": ["log_explorer"],
    "search": ["log_explorer"],
    "filter_level": ["log_explorer"],
}

_LOG_ARG_KEYS = ("path", "pattern", "context_lines", "start_line", "end_line", "level")
_REPORT_ARG_KEYS = ("name", "n_rows")


def _choose_tool_name_for_action(action: str, data: dict[str, Any]) -> Optional[str]:
    """Resolve the best tool for an action, including overlap disambiguation."""
    candidates = _ACTION_TO_TOOLS.get(action, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Shared actions between pipeline_report and log_explorer are resolved by
    # argument shape and file hints.
    has_log_args = any(key in data for key in _LOG_ARG_KEYS)
    has_report_args = any(key in data for key in _REPORT_ARG_KEYS)

    if has_log_args and "log_explorer" in candidates:
        return "log_explorer"
    if has_report_args and "pipeline_report" in candidates:
        return "pipeline_report"

    path_val = data.get("path")
    name_val = data.get("name")
    target: Optional[str] = None
    if isinstance(name_val, str):
        target = name_val
    elif isinstance(path_val, str):
        target = path_val
    if target:
        target_lower = target.lower()
        if (
            "log_explorer" in candidates
            and (target_lower.endswith(".log") or target_lower.startswith("logs/"))
        ):
            return "log_explorer"
        if (
            "pipeline_report" in candidates
            and target_lower.endswith((".csv", ".html", ".htm"))
        ):
            return "pipeline_report"

    # Backward-compatible default for bare {"action":"list|read|summary"}.
    return candidates[0]


def _detect_json_tool_invocation(
    text: str, tools: list[Any]
) -> Optional[tuple[Any, dict]]:
    """
    Return ``(tool_instance, parsed_args)`` when *text* is a bare JSON object
    that looks like a tool invocation the model was trying to make but output
    as plain text instead of calling the tool via the framework.

    Returns ``None`` when the text is normal prose or cannot be matched to a
    registered tool.
    """
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    # Match by 'action' field (most tools use this)
    action = str(data.get("action", "")).lower()
    if action:
        target_name = _choose_tool_name_for_action(action, data)
        if target_name:
            tool_obj = next((t for t in tools if t.name == target_name), None)
            if tool_obj:
                return tool_obj, data

    # Match by 'query' field (duckdb_query)
    if "query" in data and isinstance(data.get("query"), str):
        tool_obj = next((t for t in tools if t.name == "duckdb_query"), None)
        if tool_obj:
            return tool_obj, data

    return None


async def _run_tool_recovery(
    tool_obj: Any, args: dict
) -> AsyncIterator[str]:
    """
    Execute *tool_obj* with *args* as a recovery path when the model output
    a bare JSON invocation instead of calling the tool through the framework.

    Emits ``tool_start`` / ``tool_end`` SSE events so the UI shows the tool
    was used, then streams the tool's text result as a token.
    """
    tool_name = getattr(tool_obj, "name", "unknown_tool")
    yield _sse({"type": "tool_start", "tool": tool_name, "input": str(args)[:300]})
    try:
        loop = asyncio.get_running_loop()
        # tool.invoke() validates args through the args_schema (extra fields are
        # silently ignored by Pydantic v2's default 'ignore' extra policy).
        result: str = await loop.run_in_executor(None, lambda: tool_obj.invoke(args))
        yield _sse({"type": "tool_end", "tool": tool_name})
        if result and result.strip():
            yield _sse({"type": "token", "content": result})
    except Exception as exc:  # noqa: BLE001
        logger.error("Tool recovery failed for '%s': %s", tool_name, exc, exc_info=True)
        yield _sse({"type": "tool_end", "tool": tool_name})
        # Do not expose internal exception details to the client.
        yield _sse(
            {"type": "token", "content": f"Could not retrieve results from {tool_name}. Please try again."}
        )


async def _stream_agent(
    executor, message: str, chat_history: list, tools: Optional[list[Any]] = None
) -> AsyncIterator[str]:
    """
    Yield SSE-formatted strings produced by the LangGraph agent.

    Uses ``astream_events`` (LangChain ≥ 0.2) to emit token-level and
    tool-level events.  LangGraph agents expect the full conversation as a
    ``messages`` list; the current user turn is appended here.

    Token buffering
    ---------------
    All content tokens are buffered and only flushed when it is safe to do so.
    This lets the ``on_chain_end`` handler inspect the full accumulated text
    before deciding whether to emit it or to activate the JSON-recovery path.

    Fallback A (tool called, no final tokens): if tools ran but the LLM's
    final response was not streamed token-by-token, the completed graph state
    is read from the ``on_chain_end`` event and the final AI message is emitted.

    Fallback B (no tool called, bare JSON output): when the model outputs a raw
    JSON object that matches a registered tool's input schema instead of calling
    the tool through the framework, the JSON is detected, suppressed, and the
    correct tool is executed transparently so the user always sees a result.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    try:
        messages = list(chat_history) + [HumanMessage(content=message)]

        # Tracking variables for the streaming fallbacks.
        _tool_was_called = False
        _tokens_after_last_tool = False
        # Buffer of (token_str,) tuples; flushed at on_chain_end.
        _token_buffer: list[str] = []

        async for event in executor.astream_events(
            {"messages": messages},
            version="v2",
        ):
            kind = event.get("event", "")
            name = event.get("name", "")

            # LLM token chunks — buffer rather than yield immediately so the
            # on_chain_end handler can inspect the full accumulated text.
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    # Skip chunks that are part of a tool-call invocation.
                    # Ollama/Llama sometimes emits the tool-call JSON as
                    # content text; filtering here prevents that JSON from
                    # appearing in the buffer, keeping _tokens_after_last_tool
                    # accurate so the on_chain_end fallback fires correctly.
                    has_tool_calls = bool(getattr(chunk, "tool_calls", None)) or (
                        isinstance(getattr(chunk, "additional_kwargs", None), dict)
                        and bool(chunk.additional_kwargs.get("tool_calls"))
                    )
                    if has_tool_calls:
                        continue

                    token = ""
                    if hasattr(chunk, "content"):
                        content = chunk.content
                        if isinstance(content, str):
                            token = content
                        elif isinstance(content, list):
                            # Multi-modal content blocks (e.g. {"type":"text","text":"…"})
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    token += part.get("text", "")
                                elif isinstance(part, str):
                                    token += part
                    elif isinstance(chunk, dict):
                        token = chunk.get("content", "")
                    if token:
                        if _tool_was_called:
                            _tokens_after_last_tool = True
                        _token_buffer.append(token)

            # Tool start — flush any buffered tokens that preceded the tool call,
            # then emit the tool_start event immediately for UI responsiveness.
            elif kind == "on_tool_start":
                for tok in _token_buffer:
                    yield _sse({"type": "token", "content": tok})
                _token_buffer = []
                _tool_was_called = True
                _tokens_after_last_tool = False
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

            # Fallback A / B: end of the top-level agent chain.
            elif kind == "on_chain_end" and not event.get("parent_ids"):
                if _tool_was_called:
                    if _tokens_after_last_tool:
                        # Normal path: flush buffered tokens.
                        for tok in _token_buffer:
                            yield _sse({"type": "token", "content": tok})
                    else:
                        # Fallback A: tools ran but LLM response wasn't streamed
                        # token-by-token. Extract final AI message from graph state.
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict):
                            final_msgs = output.get("messages", [])
                            for msg in reversed(final_msgs):
                                if isinstance(msg, AIMessage) and not getattr(
                                    msg, "tool_calls", None
                                ):
                                    content = msg.content
                                    if isinstance(content, str) and content.strip():
                                        yield _sse({"type": "token", "content": content})
                                    break
                else:
                    # No tool was called: inspect the accumulated buffer.
                    accumulated = "".join(_token_buffer).strip()
                    if accumulated:
                        # Fallback B: detect bare JSON tool invocations that the
                        # model output as text instead of calling through the API.
                        recovery = (
                            _detect_json_tool_invocation(accumulated, tools or [])
                            if tools
                            else None
                        )
                        if recovery is not None:
                            tool_obj, args = recovery
                            logger.warning(
                                "Model output bare JSON tool invocation for '%s'; "
                                "executing via recovery path.",
                                getattr(tool_obj, "name", "unknown"),
                            )
                            async for sse in _run_tool_recovery(tool_obj, args):
                                yield sse
                        else:
                            # Normal prose — flush buffer.
                            for tok in _token_buffer:
                                yield _sse({"type": "token", "content": tok})

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
        _stream_agent(_agent_executor, body.message, lc_history, tools=_agent_tools),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

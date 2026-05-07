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

import ast
import asyncio
import json
import logging
import os
import re
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

        from agent.tools.pipeline_logs_tool import PipelineLogsTool
        from agent.tools.pbi_tool import PBIRetrieverTool
        from agent.tools.sql_tool import DuckDBQueryTool, get_db_schema
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
            PipelineLogsTool(),
            PBIRetrieverTool(),
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

# Maps action values to the tool that handles them.
# All pipeline log/report/host actions now route to the single pipeline_logs tool,
# eliminating the previous routing ambiguity between log_explorer, pipeline_report,
# and host_retrieval_log.
_ACTION_TO_TOOLS: dict[str, list[str]] = {
    # pipeline_logs — all file/log/report actions
    "list": ["pipeline_logs"],
    "show": ["pipeline_logs"],
    "read": ["pipeline_logs"],
    "head": ["pipeline_logs"],
    "tail": ["pipeline_logs"],
    "search": ["pipeline_logs"],
    "filter_level": ["pipeline_logs"],
    "summary": ["pipeline_logs"],
    # pipeline_logs — host retrieval shortcuts
    "list_failures": ["pipeline_logs"],
    "get_status": ["pipeline_logs"],
    "get_fasta_qc": ["pipeline_logs"],
    "get_download_log": ["pipeline_logs"],
    "get_host_mapping_log": ["pipeline_logs"],
    # pbi_retriever
    "get_stats": ["pbi_retriever"],
    "get_phage_by_id": ["pbi_retriever"],
    "get_protein_by_id": ["pbi_retriever"],
    "list_hosts": ["pbi_retriever"],
    "list_failed_hosts": ["pbi_retriever"],
}

_LOG_ARG_KEYS = ("path", "pattern", "context_lines", "start_line", "end_line", "level")
_REPORT_ARG_KEYS = ("name", "n_rows")
# Top-level keys that are commonly produced outside nested "parameters"/"arguments"
# wrappers by model outputs.
# Selection criteria:
# - keys already used by current tool schemas;
# - low-risk scalar routing/query fields;
# - no transport/envelope metadata.
# We merge only this conservative subset into nested args so recovery stays
# deterministic and avoids forwarding arbitrary metadata to tools.
_RECOVERY_MERGE_TOP_LEVEL_KEYS = (
    "action",
    "query",
    "path",
    "name",
    "pattern",
    "n_lines",
    "n_rows",
    "filter",
)


def _choose_tool_name_for_action(action: str, data: dict[str, Any]) -> Optional[str]:
    """Resolve the tool for an action. All log/report/host actions map to pipeline_logs."""
    candidates = _ACTION_TO_TOOLS.get(action, [])
    if not candidates:
        return None
    # All entries in _ACTION_TO_TOOLS have exactly one candidate now.
    return candidates[0]


def _parse_json_like_dict(raw: str) -> Optional[dict[str, Any]]:
    """Parse *raw* as JSON first, then as a Python literal dict; return dict or None."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_balanced_braces(text: str, start_index: int) -> Optional[tuple[str, int]]:
    """
    Return ``(braced_segment, end_index_exclusive)`` for a balanced ``{...}`` block.

    Returns ``None`` when ``start_index`` is invalid, does not point to ``'{'``,
    or when braces are unbalanced/malformed. String-state tracking supports both
    JSON and Python-literal style quoted strings to avoid counting braces inside
    quoted content.
    """
    if start_index < 0 or start_index >= len(text) or text[start_index] != "{":
        return None

    depth = 0
    in_string = False
    quote_char = ""
    escape = False

    for i in range(start_index, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == quote_char:
                in_string = False
            continue

        if ch in ('"', "'"):
            in_string = True
            quote_char = ch
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_index:i + 1], i + 1

    return None


def _extract_dict_from_model_text(text: str) -> Optional[dict[str, Any]]:
    """
    Extract a dict payload from model text that may be:
    - a bare JSON/Python dict
    - a code-fenced dict
    - a tool echo like "pipeline_report({...})" or "🔧 pipeline_report({...})"
    """
    stripped = text.strip()

    # Code-fenced payloads.
    fenced = re.search(r"```(?:json|python)?", stripped)
    if fenced:
        brace_start = stripped.find("{", fenced.end())
        if brace_start != -1:
            segment = _extract_balanced_braces(stripped, brace_start)
            if segment is not None:
                parsed = _parse_json_like_dict(segment[0].strip())
                if parsed is not None:
                    return parsed

    # Bare dict payload.
    if stripped.startswith("{"):
        segment = _extract_balanced_braces(stripped, 0)
        spans_full_text = segment is not None and segment[1] == len(stripped)
        if spans_full_text:
            parsed = _parse_json_like_dict(segment[0])
            if parsed is not None:
                return parsed

    # Match echoed calls (including prefixed symbols like "🔧"):
    #   "pipeline_report({...})"
    #   "🔧 pipeline_report({...})"
    call_match = re.search(
        r"(?:^|\s)[^\w]*([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        stripped,
    )
    if call_match:
        explicit_tool = call_match.group(1)
        brace_start = stripped.find("{", call_match.end())
        if brace_start != -1:
            segment = _extract_balanced_braces(stripped, brace_start)
            if segment is not None:
                inner, end_idx = segment
                # Ensure the balanced dict is the function argument payload.
                trailing = stripped[end_idx:].strip()
                if trailing.startswith(")"):
                    parsed = _parse_json_like_dict(inner.strip())
                    if isinstance(parsed, dict):
                        # Inject the echoed tool name only when the payload
                        # does not already specify a tool target explicitly.
                        if not any(k in parsed for k in ("name", "function", "tool")):
                            parsed["function"] = explicit_tool
                        return parsed

    return None


def _is_envelope_name(
    payload: dict[str, Any],
    nested: Optional[dict[str, Any]],
    explicit_tool: Optional[str],
) -> bool:
    """
    Return True when payload['name'] is an envelope tool identifier.

    Args:
        payload: Original parsed payload dictionary.
        nested: Nested arguments dictionary (parameters/arguments/args), if present.
        explicit_tool: Explicit tool target inferred from payload envelope keys.
    """
    has_tool = bool(explicit_tool)
    payload_name = payload.get("name")
    has_matching_name = isinstance(payload_name, str) and payload_name == explicit_tool
    nested_defines_name = isinstance(nested, dict) and "name" in nested
    return has_tool and has_matching_name and not nested_defines_name


def _normalise_recovery_payload(
    payload: dict[str, Any],
) -> tuple[Optional[str], dict[str, Any]]:
    """
    Normalize multiple payload shapes into ``(explicit_tool_name, tool_args)``.

    Supports:
    - {"action": "...", ...}
    - {"name"|"function"|"tool": "...", "parameters"| "arguments"| "args": {...}}
    - mixed top-level + nested argument fields.
    """
    explicit_tool = None
    for key in ("name", "function", "tool"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            explicit_tool = val.strip()
            break

    nested = None
    for key in ("parameters", "arguments", "args"):
        val = payload.get(key)
        if isinstance(val, dict):
            nested = val
            break

    # Default to top-level args, but when a nested args object is present
    # use it and merge selected top-level fields only if absent.
    if nested is None:
        args = dict(payload)
    else:
        args = dict(nested)
        for key in _RECOVERY_MERGE_TOP_LEVEL_KEYS:
            if key in payload and key not in args:
                args[key] = payload[key]

    # Remove envelope-only keys from the final tool args.
    for key in ("function", "tool", "parameters", "arguments", "args"):
        args.pop(key, None)
    # 'name' is overloaded:
    # - envelope tool name in {"name":"pipeline_report","parameters":{...}}
    # - legitimate tool argument in {"action":"summary","name":"report.html"}
    # Remove only the envelope form.
    if _is_envelope_name(payload, nested, explicit_tool):
        args.pop("name", None)

    return explicit_tool, args


# Old tool names that mapped to what is now pipeline_logs.
_LEGACY_PIPELINE_LOGS_TOOL_NAMES = frozenset(
    {"pipeline_report", "log_explorer", "host_retrieval_log"}
)


def _normalise_tool_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """
    Post-process *args* for *tool_name* to handle legacy field names and
    backward-compatible translations.

    Specifically: when routing to ``pipeline_logs``, the old ``pipeline_report``
    tool used ``name`` for file identification while the new tool uses ``path``.
    If the model echoed an old-style invocation (e.g. ``name='host_status_report.csv'``),
    translate ``name`` → ``path`` so the unified tool receives the right argument.
    """
    resolved_name = tool_name
    # If explicit_tool was an old name, it was already resolved to pipeline_logs
    # by the action lookup; normalise here too for direct explicit_tool hits.
    if resolved_name in _LEGACY_PIPELINE_LOGS_TOOL_NAMES:
        resolved_name = "pipeline_logs"

    if resolved_name == "pipeline_logs":
        args = dict(args)
        # Translate 'name' → 'path' for backward compatibility with pipeline_report.
        if "name" in args and "path" not in args:
            args["path"] = args.pop("name")
        # Translate old pipeline_report action='summary'/'read' → action='show' for
        # report files (path ends in .html/.csv/.htm).
        action = str(args.get("action", "")).lower()
        if action in ("summary", "read"):
            path_val = str(args.get("path", "")).lower()
            if path_val.endswith((".html", ".htm", ".csv")):
                args["action"] = "show"
    return args


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
    payload = _extract_dict_from_model_text(text)
    if payload is None:
        return None

    explicit_tool, data = _normalise_recovery_payload(payload)

    if explicit_tool:
        tool_obj = next((t for t in tools if t.name == explicit_tool), None)
        if tool_obj:
            return tool_obj, _normalise_tool_args(explicit_tool, data)

    # Match by 'action' field (most tools use this)
    action = str(data.get("action", "")).lower()
    if action:
        target_name = _choose_tool_name_for_action(action, data)
        if target_name:
            tool_obj = next((t for t in tools if t.name == target_name), None)
            if tool_obj:
                return tool_obj, _normalise_tool_args(target_name, data)

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

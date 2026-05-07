import asyncio

from agent import app as agent_app


def test_load_system_prompt_includes_schema_placeholder_replacement():
    prompt = agent_app._load_system_prompt("Table: fact_phages")
    assert "Table: fact_phages" in prompt


def test_sse_serialization_format():
    payload = {"type": "token", "content": "ok"}
    sse = agent_app._sse(payload)
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")


def test_health_reports_single_tool_list_shape():
    class MockTool:
        name = "duckdb_query"

    previous_tools = list(agent_app._agent_tools)
    try:
        agent_app._agent_tools = [MockTool()]
        data = asyncio.run(agent_app.health())
        assert data["tools"] == ["duckdb_query"]
    finally:
        agent_app._agent_tools = previous_tools

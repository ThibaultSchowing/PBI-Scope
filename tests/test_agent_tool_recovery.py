from agent.app import _detect_json_tool_invocation


class _Tool:
    def __init__(self, name: str):
        self.name = name


def _tools():
    return [
        _Tool("pipeline_logs"),
        _Tool("duckdb_query"),
        _Tool("pbi_retriever"),
    ]


def test_detects_wrapped_name_parameters_payload():
    text = '{"name":"pipeline_logs","parameters":{"action":"list"}}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_logs"
    assert args == {"action": "list"}


def test_detects_wrapped_function_parameters_payload():
    text = '{"function":"pipeline_logs","parameters":{"action":"show","path":"reports/phage_metadata_report.html"}}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_logs"
    assert args == {"action": "show", "path": "reports/phage_metadata_report.html"}


def test_detects_python_style_echoed_tool_call():
    text = "🔧 pipeline_logs({'parameters': {'action': 'list'}, 'function': 'pipeline_logs'})"
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_logs"
    assert args == {"action": "list"}


def test_action_list_routes_to_pipeline_logs():
    text = '{"action":"list"}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_logs"
    assert args == {"action": "list"}


def test_action_show_routes_to_pipeline_logs():
    text = '{"action":"show","path":"reports/host_status_report.csv"}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_logs"
    assert args == {"action": "show", "path": "reports/host_status_report.csv"}


def test_action_summary_routes_to_pipeline_logs():
    text = '{"action":"summary","path":"logs/host_download.log"}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_logs"
    assert args == {"action": "summary", "path": "logs/host_download.log"}

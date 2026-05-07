from agent.app import _detect_json_tool_invocation


class _Tool:
    def __init__(self, name: str):
        self.name = name


def _tools():
    return [
        _Tool("pipeline_report"),
        _Tool("log_explorer"),
        _Tool("duckdb_query"),
    ]


def test_detects_wrapped_name_parameters_payload():
    text = '{"name":"pipeline_report","parameters":{"action":"list"}}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_report"
    assert args == {"action": "list"}


def test_detects_wrapped_function_parameters_payload():
    text = '{"function":"pipeline_report","parameters":{"action":"summary","name":"phage_metadata_report.html"}}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_report"
    assert args == {"action": "summary", "name": "phage_metadata_report.html"}


def test_detects_python_style_echoed_tool_call():
    text = "🔧 pipeline_report({'parameters': {'action': 'list'}, 'function': 'pipeline_report'})"
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "pipeline_report"
    assert args == {"action": "list"}


def test_action_overlap_prefers_log_tool_when_path_looks_like_log():
    text = '{"action":"summary","path":"logs/host_download.log"}'
    found = _detect_json_tool_invocation(text, _tools())
    assert found is not None
    tool, args = found
    assert tool.name == "log_explorer"
    assert args == {"action": "summary", "path": "logs/host_download.log"}

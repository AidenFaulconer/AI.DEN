"""Unit tests for tool-call normalization."""
import json

import server


def test_unwrap_write_file_smuggling() -> None:
    nested = json.dumps({"name": "list_models", "arguments": {}})
    raw = [{
        "id": "x",
        "type": "function",
        "function": {
            "name": "write_file",
            "arguments": json.dumps({
                "path": "/.tmp/tool_call_1.json",
                "content": nested,
            }),
        },
    }]
    out = server._normalize_tool_calls(raw)
    assert len(out) == 1
    assert out[0]["function"]["name"] == "list_models"


def test_parse_tool_json_from_content() -> None:
    content = 'Sure. <tool_call>{"name": "list_models", "arguments": {}}</tool_call>'
    calls = server._tool_calls_from_content(content)
    assert calls and calls[0]["function"]["name"] == "list_models"


def test_tools_for_chat_excludes_chat_generate() -> None:
    names = {t["function"]["name"] for t in server._tools_for_chat_payload()}
    assert "chat" not in names
    assert "generate" not in names
    assert "list_models" in names

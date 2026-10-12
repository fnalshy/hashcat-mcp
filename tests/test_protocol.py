"""MCP protocol tests: stdio handshake plus in-process dispatch."""

import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

EXPECTED_TOOLS = {
    "hashcat_identify",
    "hashcat_devices",
    "hashcat_wordlists",
    "hashcat_merge_rockyou",
    "hashcat_start",
    "hashcat_status",
    "hashcat_result",
    "hashcat_stop",
    "hashcat_potfile",
}


def _spawn(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["HASHCAT_MCP_DATA"] = str(tmp_path / "data")
    env.pop("HASHCAT_EXE", None)
    env.pop("DATA_DIR", None)
    return subprocess.Popen(
        [sys.executable, "-m", "hashcat_mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(tmp_path), env=env, text=True, encoding="utf-8",
    )


def test_stdio_handshake_and_tools_list(tmp_path):
    proc = _spawn(tmp_path)
    try:
        def send(payload):
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()

        def read():
            return json.loads(proc.stdout.readline())

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "pytest", "version": "0"}}})
        init = read()
        assert init["result"]["serverInfo"]["name"] == "hashcat-mcp"
        assert init["result"]["protocolVersion"] == "2024-11-05"

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = read()
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert names == EXPECTED_TOOLS
        assert len(names) == 9

        send({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        assert read()["result"] == {}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def test_protocol_version_negotiation(server):
    result = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"protocolVersion": "2024-11-05"}})["result"]
    assert result["protocolVersion"] == "2024-11-05"

    unknown = server.handle({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                             "params": {"protocolVersion": "1999-01-01"}})["result"]
    assert unknown["protocolVersion"] == "2025-06-18"


def test_unknown_method_returns_error(server):
    response = server.handle({"jsonrpc": "2.0", "id": 9, "method": "does/not/exist"})
    assert response["error"]["code"] == -32601


def test_unknown_tool_is_error(server):
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": "nope", "arguments": {}}})
    assert response["result"]["isError"] is True


def test_notification_has_no_response(server):
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

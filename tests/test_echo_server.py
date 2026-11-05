"""Testes do eco MCP feito à mão (passo 01).

O script não faz parte do pacote taxlaw (é descartável), então é carregado
pelo caminho do arquivo. Os testes de handle_message não abrem processo; o
último teste roda o script de verdade, como o Claude Code faria.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "echo" / "echo_server.py"

_spec = importlib.util.spec_from_file_location("echo_server", SCRIPT)
echo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(echo)

MODERN_META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}


def request(method, params=None, msg_id=1):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def test_discover_lists_modern_version_and_tools_capability():
    response = echo.handle_message(request("server/discover", {"_meta": MODERN_META}))
    result = response["result"]
    assert result["supportedVersions"] == ["2026-07-28"]
    assert result["capabilities"] == {"tools": {}}
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "eco-manual"


def test_initialize_accepts_known_legacy_version():
    response = echo.handle_message(request("initialize", {"protocolVersion": "2025-06-18"}))
    assert response["result"]["protocolVersion"] == "2025-06-18"
    assert response["result"]["serverInfo"]["name"] == "eco-manual"


def test_initialize_with_unknown_version_answers_latest_legacy():
    response = echo.handle_message(request("initialize", {"protocolVersion": "1999-01-01"}))
    assert response["result"]["protocolVersion"] == "2025-11-25"


def test_modern_request_with_unsupported_version_is_rejected():
    meta = {**MODERN_META, "io.modelcontextprotocol/protocolVersion": "2099-01-01"}
    response = echo.handle_message(request("tools/list", {"_meta": meta}))
    assert response["error"]["code"] == -32022
    assert response["error"]["data"] == {"supported": ["2026-07-28"], "requested": "2099-01-01"}


def test_tools_list_has_only_eco():
    response = echo.handle_message(request("tools/list", {"_meta": MODERN_META}))
    tools = response["result"]["tools"]
    assert [t["name"] for t in tools] == ["eco"]
    assert tools[0]["inputSchema"]["required"] == ["texto"]


def test_tools_call_echoes_text():
    params = {"_meta": MODERN_META, "name": "eco", "arguments": {"texto": "reforma"}}
    result = echo.handle_message(request("tools/call", params))["result"]
    assert result["content"] == [{"type": "text", "text": "reforma"}]
    assert result["isError"] is False


def test_tools_call_without_text_is_tool_error_not_protocol_error():
    params = {"name": "eco", "arguments": {}}
    response = echo.handle_message(request("tools/call", params))
    assert "error" not in response
    assert response["result"]["isError"] is True


def test_unknown_tool_is_protocol_error():
    response = echo.handle_message(request("tools/call", {"name": "outra", "arguments": {}}))
    assert response["error"]["code"] == -32602


def test_unknown_method_is_method_not_found():
    assert echo.handle_message(request("resources/list"))["error"]["code"] == -32601


def test_notification_has_no_response():
    assert echo.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_client_response_has_no_response():
    assert echo.handle_message({"jsonrpc": "2.0", "id": 7, "result": {}}) is None


def test_script_over_stdio(tmp_path):
    log_path = tmp_path / "log" / "echo.jsonl"
    lines = [
        json.dumps(request("server/discover", {"_meta": MODERN_META}, msg_id=1)),
        "",
        "{isto não é json",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps(
            request(
                "tools/call",
                {"_meta": MODERN_META, "name": "eco", "arguments": {"texto": "ação\nlinha 2"}},
                msg_id=2,
            ),
            ensure_ascii=False,
        ),
    ]
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        env={**os.environ, "ECHO_LOG_PATH": str(log_path)},
        timeout=10,
    )
    assert completed.returncode == 0
    out_lines = completed.stdout.splitlines()
    # 3 respostas: discover, erro de JSON inválido e tools/call.
    # Linha em branco e notificação não geram resposta.
    responses = [json.loads(line) for line in out_lines]
    assert len(responses) == 3
    assert responses[0]["id"] == 1
    assert responses[1]["error"]["code"] == -32700
    assert responses[2]["result"]["content"][0]["text"] == "ação\nlinha 2"
    logged = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [entry["direcao"] for entry in logged].count("saida") == 3
    assert [entry["direcao"] for entry in logged].count("entrada") == 4

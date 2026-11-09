"""O server taxlaw via Streamable HTTP, com token (passo extra).

Sobe o server HTTP de verdade num subprocesso (`python -m taxlaw.http`), numa
porta livre de 127.0.0.1, com um token gerado na hora. Nada sai da máquina.
O cliente de terminal é carregado pelo caminho do arquivo, como em
`test_taxlaw_client.py`. CPF sintético, gerado em tempo de execução.
"""

import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import anyio
import pytest

from taxlaw import tools
from taxlaw.http import MAX_BODY_BYTES, MIN_TOKEN_LENGTH, TOKEN_ENV, BearerTokenMiddleware
from taxlaw.synthetic_ids import make_cpf

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("taxlaw_client", ROOT / "client" / "taxlaw_client.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

TOKEN = secrets.token_urlsafe(32)
TOOLS_LIST = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}}
).encode()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    """O server HTTP rodando; devolve a URL do endpoint MCP."""
    port = free_port()
    env = {**os.environ, TOKEN_ENV: TOKEN}
    process = subprocess.Popen(
        [sys.executable, "-m", "taxlaw.http", "--port", str(port)],
        env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.1)
    else:
        process.kill()
        pytest.fail("o server HTTP não abriu a porta em 30 s")
    yield f"http://127.0.0.1:{port}/mcp"
    process.terminate()
    process.wait(timeout=10)


def post(url, body=TOOLS_LIST, headers=None):
    """POST cru; devolve (status, corpo)."""
    base = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    request = urllib.request.Request(url, data=body, headers={**base, **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def run_cli(capsys, monkeypatch, url, *argv, token=TOKEN):
    if token is None:
        monkeypatch.delenv(TOKEN_ENV, raising=False)
    else:
        monkeypatch.setenv(TOKEN_ENV, token)
    code = cli.main(["--url", url, *argv])
    out, err = capsys.readouterr()
    return code, out, err


# ------------------------------------------------------------------ funcionamento


def test_client_works_over_http(server, capsys, monkeypatch):
    code, out, _ = run_cli(capsys, monkeypatch, server, "ferramentas")
    assert code == 0 and "buscar_dispositivos:" in out and "obter_dispositivo:" in out
    code, out, _ = run_cli(capsys, monkeypatch, server, "buscar", "zona franca de manaus")
    assert code == 0 and "[ADCT.art126.incIII.alia]" in out


def test_json_over_http_is_exactly_tools_py(server, capsys, monkeypatch):
    code, out, _ = run_cli(capsys, monkeypatch, server, "--json", "obter", "CF.art156-A.par1.incIX", "--data", "2030-06-01")
    expected = tools.obter_dispositivo(tools.load_context(), "CF.art156-A.par1.incIX", "2030-06-01", today=date(2026, 11, 9))
    assert code == 0 and json.loads(out) == expected


def test_stateless_revision_and_no_session(server):
    status, body = post(server, headers={"authorization": f"Bearer {TOKEN}"})
    assert status == 200 and [t["name"] for t in json.loads(body)["result"]["tools"]] == ["buscar_dispositivos", "obter_dispositivo"]
    assert post(server, headers={"authorization": f"Bearer {TOKEN}"})[0] == 200  # de novo, sem sessão nenhuma


def test_taxpayer_id_blocked_by_the_server_over_the_network(server, capsys, monkeypatch):
    # Cliente remoto não tem o hook do Claude Code: a guarda do server é que protege.
    number = make_cpf("987654321", formatted=True)
    code, out, err = run_cli(capsys, monkeypatch, server, "buscar", f"situação de {number}")
    assert code == 1 and json.loads(err)["erro"] == "dados_de_contribuinte"
    assert number not in out + err and number.replace(".", "").replace("-", "") not in out + err


# ------------------------------------------------------------------ token


@pytest.mark.parametrize("authorization", [None, "Bearer errado", f"Basic {TOKEN}", f"Bearer {TOKEN}x", f"bearer {TOKEN}"])
def test_requests_without_the_exact_token_get_401(server, authorization):
    status, body = post(server, headers={"authorization": authorization} if authorization else {})
    assert status == 401 and json.loads(body)["error"]["message"] == "nao_autorizado"
    assert TOKEN not in body


def test_401_happens_on_any_path_before_mcp(server):
    assert post(server.replace("/mcp", "/qualquer-coisa"))[0] == 401


@pytest.mark.parametrize("token", ["errado", None])
def test_client_with_wrong_or_missing_token_is_exit_2_without_echo(server, capsys, monkeypatch, token):
    code, out, err = run_cli(capsys, monkeypatch, server, "ferramentas", token=token)
    assert code == 2 and out == ""
    assert ("token recusado pelo server" in err) if token else (TOKEN_ENV in err)
    assert TOKEN not in err and (token is None or token not in err.replace(TOKEN_ENV, ""))


def test_client_cannot_reach_a_closed_port(capsys, monkeypatch):
    code, _, err = run_cli(capsys, monkeypatch, f"http://127.0.0.1:{free_port()}/mcp", "ferramentas")
    assert code == 2 and "não consegui falar com o server" in err and TOKEN not in err


def test_client_rejects_url_and_server_together():
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--url", "http://127.0.0.1:1/mcp", "--server", "python -m taxlaw.server", "ferramentas"])
    assert exit_info.value.code == 2


# ------------------------------------------------------------------ proteções


def test_unknown_host_header_is_refused(server):
    status, _ = post(server, headers={"authorization": f"Bearer {TOKEN}", "host": "evil.example"})
    assert status == 421  # medido: a proteção do SDK contra DNS rebinding responde 421


def test_body_over_the_limit_is_413(server):
    status, _ = post(server, body=b"x" * (MAX_BODY_BYTES + 1), headers={"authorization": f"Bearer {TOKEN}"})
    assert status == 413


# ------------------------------------------------------------------ partida


@pytest.mark.parametrize("value", [None, "curto-demais"])
def test_server_does_not_start_without_a_long_token(value):
    # Subprocesso com tempo máximo: se a checagem regredir e o server subir,
    # o teste falha por tempo, em vez de pendurar a suíte.
    env = {k: v for k, v in os.environ.items() if k != TOKEN_ENV}
    if value is not None:
        env[TOKEN_ENV] = value
    done = subprocess.run(
        [sys.executable, "-m", "taxlaw.http", "--port", str(free_port())],
        env=env, cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert done.returncode == 2
    assert TOKEN_ENV in done.stderr and str(MIN_TOKEN_LENGTH) in done.stderr
    assert value is None or value not in done.stderr


# ------------------------------------------------------------------ middleware isolado


def test_middleware_unit():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["type"])

    middleware = BearerTokenMiddleware(app, "t" * 40)

    async def drive(scope):
        sent = []

        async def send(message):
            sent.append(message)

        await middleware(scope, None, send)
        return sent

    ok = anyio.run(drive, {"type": "http", "headers": [(b"authorization", b"Bearer " + b"t" * 40)]})
    refused = anyio.run(drive, {"type": "http", "headers": [(b"authorization", b"Bearer " + b"t" * 39)]})
    anyio.run(drive, {"type": "lifespan"})
    assert ok == [] and calls == ["http", "lifespan"]
    assert refused[0]["status"] == 401 and (b"www-authenticate", b"Bearer") in refused[0]["headers"]

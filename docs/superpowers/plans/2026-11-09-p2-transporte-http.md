# P2, passo extra: o taxlaw via Streamable HTTP, com token (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-09-p2-transporte-http.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o mesmo server taxlaw servido também via Streamable HTTP stateless, sempre com token, e o cliente de terminal consultando por URL, como primeira etapa da publicação numa VPS.

**Architecture:** `src/taxlaw/http.py` (novo) monta o app HTTP do SDK (`streamable_http_app`, stateless, JSON, Host restrito, corpo de 64 KB) a partir do `build_server()` existente e o embrulha num `BearerTokenMiddleware` ASGI; `main` lê o token de `TAXLAW_HTTP_TOKEN` e roda o `uvicorn`. O cliente ganha `--url` com um alvo `HttpTarget` e reconhece 401 por um event hook do httpx. `server.py` (stdio) não muda.

**Tech Stack:** Python 3.13, SDK `mcp` 2.3.0 (`streamable_http_app`, `TransportSecuritySettings`, `streamable_http_client`), `uvicorn` e `httpx2` (vêm com o SDK), pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-transporte-http-design.md`

## Global Constraints

- Nenhuma dependência nova; `pyproject.toml` e `uv.lock` não mudam.
- O modo HTTP sempre exige o token: sem `TAXLAW_HTTP_TOKEN` de pelo menos 32 caracteres, `python -m taxlaw.http` sai com 2; toda requisição sem `Authorization: Bearer <token>` exato recebe 401 antes do MCP.
- O token só vem da variável `TAXLAW_HTTP_TOKEN` (server e cliente), nunca de argumento; nenhuma mensagem, log ou `repr` contém o token.
- Escuta padrão `127.0.0.1`; `Host` só da lista permitida; nenhuma `Origin` permitida; corpo máximo 64 KB; log de acesso desligado.
- `server.py`, `tools.py`, `guard.py` e o `.mcp.json` não mudam; o stdio continua igual.
- O cliente continua sem importar `taxlaw` e sem `@dataclass` (o teste o carrega pelo caminho, sem `sys.modules`).
- Testes 100% offline (só 127.0.0.1) e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes; nenhum teste pode pendurar: o server sobe em subprocesso, e o teste de partida tem tempo máximo.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `corpus/`, `.claude/`, `.kiro/`, `hooks/`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-09 no protótipo)

- `MCPServer.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, max_request_body_size=65536, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[...], allowed_origins=[]))` devolve um app Starlette; `uvicorn.run(app, host, port, access_log=False, log_level="warning")` o serve.
- `curl` no protótipo: sem token e com token errado → 401; com token → `tools/list` em JSON; `Host: evil.example` → **421 "Invalid Host header"**; corpo de 70 KB → **413 "Request body too large"**.
- O cliente do SDK transforma um 401 com corpo qualquer em `MCPError` genérico ("Server returned an error response", código -32603); com o corpo como erro JSON-RPC, repassa o erro. Por isso o 401 tem corpo `{"jsonrpc": "2.0", "id": null, "error": {"code": -32001, "message": "nao_autorizado"}}`, e o cliente reconhece o 401 por um event hook de resposta do `httpx2.AsyncClient` (funciona também se o 401 vier do proxy).
- `@dataclass` num módulo carregado com `spec_from_file_location` sem registro em `sys.modules` falha na coleta (`'NoneType' object has no attribute '__dict__'`): `HttpTarget` é classe simples.
- Mutações no protótipo (todas quebram ao menos um teste): `startswith` no lugar de `compare_digest`, token curto aceito (falha por tempo, 21 s, sem pendurar), proteção de Host desligada, limite de corpo padrão, `lifespan` barrado, 401 sem mensagem própria no cliente, cliente sem token tentando conectar.

## Review Focus

- Um token que só começa com o token certo (`Bearer <token>x`) ou com esquema em minúsculas ser aceito (teste `test_requests_without_the_exact_token_get_401`).
- Uma regressão na checagem do token curto fazer o server subir e pendurar a suíte (teste `test_server_does_not_start_without_a_long_token`, em subprocesso com `timeout=20`).
- O 401 aparecer para o usuário como "não consegui falar com o server" em vez de "token recusado" (teste `test_client_with_wrong_or_missing_token_is_exit_2_without_echo`).
- Algum caminho responder sem token (teste `test_401_happens_on_any_path_before_mcp`).
- CPF numa consulta HTTP chegar ao corpus ou voltar na saída (teste `test_taxpayer_id_blocked_by_the_server_over_the_network`).

---

### Task 1: Server HTTP com token e cliente por URL

**Files:**
- Create: `src/taxlaw/http.py`
- Modify: `client/taxlaw_client.py`
- Create: `tests/test_http.py`
- Create: `docs/steps/http.md`

**Interfaces:**
- Consumes: `taxlaw.server.build_server() -> TaxLawServer`, `TaxLawServer`; `taxlaw.tools.load_context`, `obter_dispositivo`; `taxlaw.synthetic_ids.make_cpf` (testes); `mcp.server.transport_security.TransportSecuritySettings`; `mcp.client.streamable_http.streamable_http_client(url, *, http_client=...)`; `httpx2.AsyncClient(headers=..., timeout=..., event_hooks=...)`.
- Produces: `taxlaw.http.TOKEN_ENV = "TAXLAW_HTTP_TOKEN"`, `MIN_TOKEN_LENGTH = 32`, `MAX_BODY_BYTES = 65536`, `MCP_PATH = "/mcp"`, `BearerTokenMiddleware(app, token)`, `build_http_app(server, *, token, allowed_hosts) -> ASGI app`, `main(argv=None) -> int` (`python -m taxlaw.http [--host] [--port] [--allowed-host ...]`); no cliente: `TOKEN_ENV`, `HttpTarget(url, token)`, `http_target(url) -> HttpTarget`, opção `--url` (exclusiva com `--server`).

- [ ] **Step 1: testes que falham.** Crie `tests/test_http.py`:

```python
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
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_http.py -q` → `ModuleNotFoundError: No module named 'taxlaw.http'`.

- [ ] **Step 3: server HTTP.** Crie `src/taxlaw/http.py`:

```python
"""O server taxlaw via Streamable HTTP, com token (spec 2026-11-09-transporte-http-design).

O stdio (`server.py`) continua sendo o transporte do Claude Code e do Kiro.
Aqui o MESMO server (`build_server()`: mesma guarda de CPF/CNPJ antes do SDK,
mesmas ferramentas, mesmo corpus) fica atrás de uma porta HTTP, para um
cliente em outra máquina. É a primeira etapa de uma publicação numa VPS; o
deploy (proxy, HTTPS, limite de taxa) é outro passo.

Regras:
- **sempre com token**: toda requisição HTTP sem `Authorization: Bearer
  <token>` válido recebe 401 antes de chegar ao MCP. Sem token configurado
  (ou com menos de 32 caracteres), o server nem sobe;
- o token vem só da variável `TAXLAW_HTTP_TOKEN`, nunca de argumento (que
  apareceria no `ps` e no histórico do shell), e nenhuma mensagem o repete;
- stateless (combina com a revisão 2026-07-28: cada requisição se explica
  sozinha) e resposta JSON simples;
- escuta em 127.0.0.1 por padrão; `Host` só da lista permitida (proteção do
  SDK contra DNS rebinding) e nenhuma `Origin` (navegadores são recusados);
- corpo de no máximo 64 KB (uma consulta tem até 500 caracteres);
- log de acesso desligado: nenhum log de cabeçalhos (o token) nem de argumentos.

Uso:
    TAXLAW_HTTP_TOKEN=... uv run python -m taxlaw.http --port 8000
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import sys

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from taxlaw.server import TaxLawServer, build_server

TOKEN_ENV = "TAXLAW_HTTP_TOKEN"
MIN_TOKEN_LENGTH = 32
MAX_BODY_BYTES = 65536
MCP_PATH = "/mcp"

# Corpo do 401 como erro JSON-RPC: o cliente do SDK repassa um erro JSON-RPC
# recebido com status de erro (em vez de um genérico "Server returned an error
# response"), então qualquer cliente MCP entende a recusa. -32001 está na faixa
# de erros do server (-32000 a -32099).
_UNAUTHORIZED = json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "nao_autorizado"}}).encode()


class BearerTokenMiddleware:
    """ASGI: só deixa passar requisições HTTP com `Authorization: Bearer <token>` exato."""

    def __init__(self, app, token: str):
        self.app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan e afins não têm cabeçalhos
            return await self.app(scope, receive, send)
        given = dict(scope.get("headers") or []).get(b"authorization", b"")
        # Tempo constante: a resposta não revela quantos caracteres batem.
        if hmac.compare_digest(given, self._expected):
            return await self.app(scope, receive, send)
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b"Bearer"),
                (b"content-length", str(len(_UNAUTHORIZED)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": _UNAUTHORIZED})


def build_http_app(server: TaxLawServer, *, token: str, allowed_hosts: list[str]):
    """O app HTTP do SDK (stateless, JSON, Host restrito, corpo limitado) atrás do token."""
    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        max_request_body_size=MAX_BODY_BYTES,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=[],
        ),
    )
    return BearerTokenMiddleware(app, token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taxlaw.http", description="O server taxlaw via Streamable HTTP, com token.")
    parser.add_argument("--host", default="127.0.0.1", help="interface (padrão 127.0.0.1; na VPS, atrás do proxy)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--allowed-host", action="append", default=None, help="valor de Host aceito (repetível)")
    args = parser.parse_args(argv)

    token = os.environ.get(TOKEN_ENV, "")
    if len(token) < MIN_TOKEN_LENGTH:
        # Nunca repetir o valor: só dizer o que falta.
        print(
            f"erro: defina {TOKEN_ENV} com pelo menos {MIN_TOKEN_LENGTH} caracteres "
            '(ex.: python -c "import secrets; print(secrets.token_urlsafe(32))")',
            file=sys.stderr,
        )
        return 2
    allowed = args.allowed_host or [f"127.0.0.1:{args.port}", f"localhost:{args.port}"]
    app = build_http_app(build_server(), token=token, allowed_hosts=allowed)
    uvicorn.run(app, host=args.host, port=args.port, access_log=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: cliente.** Substitua `client/taxlaw_client.py` inteiro por:

```python
"""Cliente MCP de terminal para o server taxlaw (spec 2026-11-09-cliente-mcp-design).

Contraparte do `echo/`: lá, um server MCP feito à mão; aqui, um cliente que
usa o SDK oficial. Ele sobe o server como processo filho (stdio), faz UMA
chamada e sai. Não importa o pacote `taxlaw`: conversa só pelo protocolo, com
os nomes do contrato público do server (spec principal, seção 6).

Uso (da raiz do repositório ou de qualquer pasta):
    uv run python client/taxlaw_client.py ferramentas
    uv run python client/taxlaw_client.py buscar "zona franca de manaus"
    uv run python client/taxlaw_client.py obter CF.art156-A.par1.incIX --data 2030-06-01
    uv run python client/taxlaw_client.py --json buscar "cesta básica"
    TAXLAW_HTTP_TOKEN=... uv run python client/taxlaw_client.py --url http://127.0.0.1:8000/mcp ferramentas

Com `--url`, fala Streamable HTTP com um server remoto (`python -m
taxlaw.http`), mandando o token de `TAXLAW_HTTP_TOKEN` no cabeçalho
`Authorization`. O token nunca vem de argumento nem aparece numa mensagem.

Códigos de saída: 0 sucesso (inclusive "não encontrado"), 1 erro devolvido
pelo server (isError), 2 erro do cliente (uso, configuração, server que não
sobe ou não responde).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

import anyio
import httpx2
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

# client/taxlaw_client.py → parents[1] é a raiz do repositório.
DEFAULT_MCP_JSON = Path(__file__).resolve().parents[1] / ".mcp.json"
SERVER_NAME = "taxlaw"
TIMEOUT_SECONDS = 30
TOKEN_ENV = "TAXLAW_HTTP_TOKEN"


class ClientError(Exception):
    """Erro do lado do cliente (código 2), com mensagem curta para gente."""


# ------------------------------------------------------------------ configuração


def server_params(mcp_json: Path, name: str = SERVER_NAME, override: str | None = None) -> StdioServerParameters:
    """Como subir o server: a entrada `name` do .mcp.json, ou o comando de `override`.

    `cwd` é a pasta do .mcp.json: o `uv run` do comando precisa achar o projeto,
    e assim o cliente funciona rodado de qualquer diretório.
    """
    cwd = mcp_json.resolve().parent
    if override:
        command, *args = shlex.split(override)
        return StdioServerParameters(command=command, args=args, cwd=cwd)
    try:
        config = json.loads(mcp_json.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ClientError(f"não achei {mcp_json}") from None
    except (OSError, ValueError) as exc:
        raise ClientError(f"não consegui ler {mcp_json} ({exc.__class__.__name__})") from None
    entry = config.get("mcpServers", {}).get(name)
    if not isinstance(entry, dict) or "command" not in entry:
        raise ClientError(f"{mcp_json.name} não tem o server '{name}' em mcpServers")
    return StdioServerParameters(command=entry["command"], args=list(entry.get("args", [])), cwd=cwd)


class HttpTarget:
    """Um server remoto via Streamable HTTP.

    Classe simples (não dataclass): o teste carrega este arquivo pelo caminho,
    sem registrá-lo em sys.modules, e @dataclass precisa do módulo registrado.
    O `repr` não mostra o token.
    """

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token

    def __repr__(self) -> str:
        return f"HttpTarget(url={self.url!r}, token=<oculto>)"


def http_target(url: str) -> HttpTarget:
    """Alvo HTTP com o token de TAXLAW_HTTP_TOKEN (nunca de argumento)."""
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise ClientError(f"defina {TOKEN_ENV} com o token do server para usar --url")
    return HttpTarget(url, token)


# ------------------------------------------------------------------ MCP (a única parte que fala protocolo)


def _run(target: StdioServerParameters | HttpTarget, operation):
    """Abre o Client (stdio ou HTTP), roda `operation(client)` com teto de tempo e fecha.

    No stdio, o stderr do server (logs do SDK) vai para /dev/null: o stderr do
    cliente fica só com as mensagens do cliente.
    """

    # Códigos HTTP vistos nesta conexão: o SDK transforma um 401 num erro MCP
    # genérico, e quem responde o 401 pode ser o proxy, não o server.
    statuses: list[int] = []

    async def record(response):
        statuses.append(response.status_code)

    async def main():
        with open(os.devnull, "w") as quiet, anyio.fail_after(TIMEOUT_SECONDS):
            if isinstance(target, HttpTarget):
                headers = {"Authorization": f"Bearer {target.token}"}
                hooks = {"response": [record]}
                async with httpx2.AsyncClient(headers=headers, timeout=TIMEOUT_SECONDS, event_hooks=hooks) as http:
                    async with Client(streamable_http_client(target.url, http_client=http)) as client:
                        return await operation(client)
            async with Client(stdio_client(target, errlog=quiet)) as client:
                return await operation(client)

    try:
        return anyio.run(main)
    except TimeoutError:
        raise ClientError(f"o server não respondeu em {TIMEOUT_SECONDS} s") from None
    except Exception as exc:  # noqa: BLE001 - qualquer falha de subir/conversar vira código 2
        if 401 in statuses:
            raise ClientError("token recusado pelo server") from None
        raise ClientError(f"não consegui falar com o server ({exc.__class__.__name__})") from None


def list_tools(params: StdioServerParameters | HttpTarget) -> list:
    return _run(params, lambda client: _tools(client))


async def _tools(client):
    return (await client.list_tools()).tools


def call(params: StdioServerParameters | HttpTarget, tool: str, arguments: dict[str, Any]):
    """Uma chamada `tools/call`. Devolve o CallToolResult do SDK."""
    return _run(params, lambda client: client.call_tool(tool, arguments))


# ------------------------------------------------------------------ formatação (funções puras)

DASH = "—"


def _get(data: dict, *keys: str) -> Any:
    """data[k1][k2]...; DASH se faltar algum nível (campo novo ou removido no server)."""
    value: Any = data
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return DASH
        value = value[key]
    return DASH if value is None else value


def _in_effect(value: Any) -> str:
    # Três estados: null é "não se sabe", nunca "não".
    return {True: "sim", False: "não"}.get(value, "não se sabe") if value in (True, False, None) else DASH


def _effects_line(effects: Any) -> str:
    if not isinstance(effects, dict):
        return f"efeitos: {DASH}"
    since, until = _get(effects, "desde"), effects.get("ate")
    span = f"desde {since}" + (f" até {until}" if until else "")
    return f"efeitos {span} ({_get(effects, 'fundamento')}); produz efeitos na data: {_in_effect(effects.get('produz_efeitos_na_data'))}"


def _corpus(data: dict) -> str:
    versao = _get(data, "corpus", "versao")
    short = versao[:8] + "…" if isinstance(versao, str) and versao != DASH else DASH
    return f"corpus coletado em {_get(data, 'corpus', 'coletado_em')}, {short}"


def render_busca(data: dict) -> str:
    head = f'Consulta "{_get(data, "consulta")}" em {_get(data, "data_referencia")} ({_corpus(data)})'
    if data.get("encontrado") is not True:
        return f"{head}\n\nNada encontrado: {_get(data, 'motivo')}"
    lines = [head, ""]
    for n, item in enumerate(data.get("resultados") or [], start=1):
        score = item.get("pontuacao")
        relevance = f"{score:.2f}".replace(".", ",") if isinstance(score, (int, float)) else DASH
        lines.append(f"{n}. {_get(item, 'citacao')}   [{_get(item, 'id')}]   relevância {relevance}")
        lines.append(f"   {_get(item, 'trecho')}")
        lines.append(f"   {_effects_line(item.get('efeitos'))}")
    return "\n".join(lines)


def _versions_line(others: Any) -> str | None:
    if not others:
        return None
    parts = []
    for other in others:
        since, until = _get(other, "efeitos", "desde"), _get(other, "efeitos", "ate")
        span = f"{since} a {until}" if until != DASH else f"desde {since}"
        parts.append(f"{_get(other, 'versao')} ({span})")
    return "outras versões: " + ", ".join(parts)


def render_dispositivo(data: dict) -> str:
    if data.get("encontrado") is not True:
        return f"Não encontrado: {_get(data, 'id')} ({_get(data, 'motivo')})"
    lines = [
        f"{_get(data, 'citacao')}   [{_get(data, 'id')}]",
        f"versão {_get(data, 'versao')}, {_get(data, 'origem')} ({_get(data, 'alteracao')}), em {_get(data, 'data_referencia')}",
        "",
        str(_get(data, "texto")),
    ]
    children = data.get("filhos") or []
    if children:
        lines.append("")
        for child in children:
            text = child.get("texto")
            lines.append(f"  {_get(child, 'citacao')}: {text if text is not None else '(não coube no teto; peça este id)'}")
    lines.append("")
    lines.append(_effects_line(data.get("efeitos")))
    if versions := _versions_line(data.get("outras_versoes")):
        lines.append(versions)
    if data.get("observacao"):
        lines.append(f"observação: {data['observacao']}")
    if data.get("truncado"):
        lines.append("truncado: o texto e os filhos passaram do teto do server")
    lines.append(f"fonte: {_get(data, 'fonte_url')} ({_corpus(data)})")
    return "\n".join(lines)


def render_ferramentas(tools: list) -> str:
    lines = []
    for tool in tools:
        description = (tool.description or "").strip().splitlines()
        lines.append(f"{tool.name}: {description[0] if description else DASH}")
        schema = tool.input_schema or {}
        required = set(schema.get("required", []))
        for name in schema.get("properties", {}):
            lines.append(f"  - {name}{' (obrigatório)' if name in required else ''}")
    return "\n".join(lines)


# ------------------------------------------------------------------ CLI


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="taxlaw_client.py", description="Cliente MCP do server taxlaw (EC 132/2023).")
    parser.add_argument("--json", action="store_true", help="imprime o structuredContent cru")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--server", help='comando do server, no lugar do .mcp.json (ex.: "python -m taxlaw.server")')
    where.add_argument("--url", help=f"server remoto via Streamable HTTP (token em {TOKEN_ENV})")
    parser.add_argument("--mcp-json", type=Path, default=DEFAULT_MCP_JSON, help="arquivo de configuração MCP")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ferramentas", help="lista as ferramentas do server")
    busca = sub.add_parser("buscar", help="buscar_dispositivos")
    busca.add_argument("consulta")
    busca.add_argument("--data", help="data de referência AAAA-MM-DD")
    busca.add_argument("--limite", type=int)
    obter = sub.add_parser("obter", help="obter_dispositivo")
    obter.add_argument("id")
    obter.add_argument("--data", help="data de referência AAAA-MM-DD")
    obter.add_argument("--sem-filhos", action="store_true")
    return parser


def _arguments(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    """Ferramenta e argumentos. Só envia o que foi dado: os padrões são os do server."""
    if args.command == "buscar":
        arguments: dict[str, Any] = {"consulta": args.consulta}
        if args.limite is not None:
            arguments["limite"] = args.limite
        tool = "buscar_dispositivos"
    else:
        arguments = {"id": args.id}
        if args.sem_filhos:
            arguments["incluir_filhos"] = False
        tool = "obter_dispositivo"
    if args.data:
        arguments["data_referencia"] = args.data
    return tool, arguments


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)  # uso errado: argparse sai com 2
    try:
        params = http_target(args.url) if args.url else server_params(args.mcp_json, override=args.server)
        if args.command == "ferramentas":
            tools = list_tools(params)
            print(json.dumps([t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in tools], ensure_ascii=False, indent=2) if args.json else render_ferramentas(tools))
            return 0
        tool, arguments = _arguments(args)
        result = call(params, tool, arguments)
    except ClientError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    if result.is_error:
        # O texto de erro do taxlaw é um JSON {"erro", "mensagem"}, já sem CPF/CNPJ.
        print(" ".join(c.text for c in result.content if getattr(c, "text", None)), file=sys.stderr)
        return 1
    data = result.structured_content or {}
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_busca(data) if tool == "buscar_dispositivos" else render_dispositivo(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: rode e veja passar.** `uv run pytest tests/test_http.py tests/test_taxlaw_client.py -q` → 46 passed (19 + 27, com `test_taxlaw_client.py` inalterado); `uv run pytest -q` → 461 passed. Depois, `pgrep -f "taxlaw.http"` não lista nada (nenhum server ficou rodando).

- [ ] **Step 6: nota do passo.** Crie `docs/steps/http.md`:

````markdown
# Passo extra: o taxlaw via Streamable HTTP, com token

## O que mudou

- **`src/taxlaw/http.py`** (novo) deixa o **mesmo** server (`build_server()`: mesma guarda, mesmas ferramentas, mesmo corpus) atrás de uma porta HTTP.
  - **Stateless**, com resposta JSON simples.
  - **Sempre com token:** sem `Authorization: Bearer <token>` exato, a resposta é **401** antes de chegar ao MCP, em qualquer caminho.
  - **O token vem só de `TAXLAW_HTTP_TOKEN`** e precisa ter pelo menos 32 caracteres. Sem ele, o server não sobe.
  - **Escuta em `127.0.0.1` por padrão.**
  - **`Host` só da lista** (`--allowed-host`); um `Host` estranho recebe **421**. Navegadores, que mandam `Origin`, são recusados.
  - **Corpo de no máximo 64 KB**; acima disso, 413.
  - **Log de acesso desligado.**
- **O 401 vem como erro JSON-RPC** (`nao_autorizado`, código -32001). Com isso, o cliente do SDK repassa o motivo, em vez de um "Server returned an error response" genérico.
- **`client/taxlaw_client.py`** ganha `--url`, com o token de `TAXLAW_HTTP_TOKEN`. Ele reconhece o 401 pelo código HTTP e responde "token recusado pelo server", com código de saída 2. `--url` e `--server` juntos são erro de uso.
- O `server.py` (stdio) não muda. O Claude Code e o Kiro continuam por stdio.

## Como rodar

```
export TAXLAW_HTTP_TOKEN=$(uv run python -c "import secrets; print(secrets.token_urlsafe(32))")
uv run python -m taxlaw.http --port 8000 &
uv run python client/taxlaw_client.py --url http://127.0.0.1:8000/mcp buscar "cesta básica"
curl -s -X POST http://127.0.0.1:8000/mcp -d '{}'     # 401, sem token
uv run pytest tests/test_http.py -v
```

No Claude Code, a configuração **pessoal** para um server remoto (nunca no `.mcp.json` do repositório, por causa do token) seria assim:

```json
{"mcpServers": {"taxlaw-remoto": {"type": "http", "url": "https://SEU-DOMINIO/mcp", "headers": {"Authorization": "Bearer ${TAXLAW_HTTP_TOKEN}"}}}}
```

## O que observar

- **O protocolo é o mesmo; só o transporte muda.** O mesmo `tools/list` e o mesmo `tools/call`, agora num `POST /mcp`, sem processo filho. O `--json` pela rede é idêntico ao `tools.py`.
- **A guarda do server vira a principal.** Um cliente remoto não tem o hook do Claude Code. Um CPF numa consulta HTTP é barrado pelo `TaxLawServer.call_tool`, e o número não aparece em nenhuma saída.
- **Três camadas de recusa, cada uma com o seu código:**
  - 401: quem é você? (o token);
  - 421: para quem é esta requisição? (o `Host`);
  - 413: tamanho.

  Só depois de passar por elas a requisição chega ao MCP.
- **O que falta para publicar** (o passo do deploy): HTTPS, limite de taxa, proxy reverso, o server rodando como serviço na VPS e o `--allowed-host` com o domínio.

## Pergunta de previsão

Na VPS, o server vai escutar em `127.0.0.1:8000`, atrás de um proxy com HTTPS. O proxy repassa a requisição com o `Host` do domínio. O que acontece se você esquecer o `--allowed-host SEU-DOMINIO`: o token ainda protege, mas qual resposta o cliente recebe, e por quê?
````

- [ ] **Step 7: commit.** `git add src/taxlaw/http.py client/taxlaw_client.py tests/test_http.py docs/steps/http.md && git commit -m "feat(http): server taxlaw via Streamable HTTP com token e cliente por URL"`

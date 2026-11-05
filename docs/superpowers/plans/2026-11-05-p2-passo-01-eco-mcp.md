# P2, passo 01: eco MCP feito à mão (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-05-p2-passo-01-eco-mcp.json`, só depois do passo 00 mergeado. É um passo de estudo: o código é descartável, mas precisa ser legível e comentado. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um server MCP mínimo, sem SDK, com uma ferramenta `eco`, que fala o protocolo via stdio e grava cada mensagem num log, para o usuário ver o protocolo trafegando e descobrir qual revisão o Claude Code usa.

**Architecture:** Um único script `echo/echo_server.py`, só com a biblioteca padrão. A lógica fica numa função pura `handle_message(dict) -> dict | None` (testável sem processo), e o laço de I/O em `serve(stdin, stdout, log_path)`. O server atende as duas "eras" do protocolo: a moderna (2026-07-28, sem handshake, versão em `params._meta`, descoberta via `server/discover`) e a legada (`initialize`). Fica fora do pacote `taxlaw` de propósito: é descartável.

**Tech Stack:** Python 3.13 (biblioteca padrão), pytest.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seções 3 e 10)

## Global Constraints

- Só biblioteca padrão no `echo/`; nenhuma dependência nova no `pyproject.toml`.
- Testes 100% offline; nenhum teste depende do diretório atual; nada de `conftest.py`.
- stdout do server contém **somente** mensagens JSON-RPC, uma por linha, sem quebras de linha internas. Logs vão para arquivo, nunca para stdout.
- O log padrão fica em `traces/echo.jsonl` (ignorado pelo git) e pode ser trocado pela variável `ECHO_LOG_PATH`; os testes sempre usam `tmp_path`.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `CODEX.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/` nem `src/`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos do protocolo usados aqui (spec MCP 2026-07-28, conferida em 2026-11-05)

- stdio: JSON-RPC 2.0 delimitado por linha, UTF-8; o server não escreve em stdout nada que não seja mensagem MCP.
- Era moderna: cada requisição traz em `params._meta` as chaves `io.modelcontextprotocol/protocolVersion` e `io.modelcontextprotocol/clientCapabilities`. O cliente sonda com `server/discover`; o resultado tem `supportedVersions`, `capabilities` e `_meta["io.modelcontextprotocol/serverInfo"]`. Versão não suportada → erro `-32022` com `data: {"supported": [...], "requested": "..."}`.
- Era legada: o cliente começa com `initialize` (`params.protocolVersion`) e o server responde `protocolVersion`, `capabilities`, `serverInfo`.
- Resultados modernos levam `resultType: "complete"`; clientes antigos ignoram o campo.
- Notificação = mensagem sem `id`: nunca tem resposta.
- Erro de execução de ferramenta vai no **resultado** (`isError: true`), não como erro JSON-RPC; ferramenta desconhecida é erro JSON-RPC `-32602`.

## Review Focus

- Texto com quebra de linha ou acentos no argumento `texto` não quebra o enquadramento: a resposta continua sendo uma única linha de JSON válido (teste no Step 1).
- Linha com JSON inválido não derruba o server: ele responde `-32700` e continua atendendo as linhas seguintes (teste no Step 1).
- Linhas em branco no stdin são ignoradas sem resposta (teste no Step 1).
- O server funciona com qualquer diretório atual e grava o log no caminho configurado (teste de subprocess com `cwd=tmp_path` no Step 1).
- Uma resposta do cliente (mensagem sem `method`) não gera resposta do server (teste no Step 1).

---

### Task 1: Eco MCP feito à mão

**Files:**
- Create: `echo/echo_server.py`
- Test: `tests/test_echo_server.py`
- Create: `.mcp.json`
- Create: `docs/steps/01-eco-mcp.md`

**Interfaces:**
- Consumes: `.gitignore` com `traces/` e `uv run pytest` (passo 00).
- Produces: `handle_message(message: object) -> dict | None`; `serve(stdin: TextIO, stdout: TextIO, log_path: Path) -> None`; server `eco` registrado em `.mcp.json`. Nada no pacote `taxlaw` depende disso.

- [ ] **Step 1: testes que falham.** Crie `tests/test_echo_server.py`:

```python
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
```

Rode `uv run pytest tests/test_echo_server.py -v`. Esperado: erro de coleta, porque `echo/echo_server.py` não existe.

- [ ] **Step 2: implementação.** Crie `echo/echo_server.py`:

```python
"""Eco MCP feito à mão (passo 01, descartável).

Objetivo didático: ver o protocolo MCP sem SDK nenhum. O server expõe uma
única ferramenta, "eco", e grava num arquivo cada mensagem que entra e sai,
para você abrir o log e ver exatamente o que o Claude Code envia.

O MCP mudou na revisão 2026-07-28 e este server atende as duas "eras":

- moderna (2026-07-28, stateless): não há handshake. Cada requisição traz a
  versão do protocolo em params._meta, e o cliente pode sondar o server com
  "server/discover" antes de usá-lo.
- legada (2025-11-25 e anteriores): o cliente começa com "initialize" e só
  depois chama as ferramentas.

Transporte stdio: uma mensagem JSON-RPC por linha. O stdout é exclusivo do
protocolo; qualquer print solto ali corromperia a conversa com o cliente.
Por isso o log vai para um arquivo.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

SERVER_INFO = {"name": "eco-manual", "version": "0.1.0"}

# Versões que este server sabe falar, da mais nova para a mais antiga.
MODERN_VERSIONS = ["2026-07-28"]
LEGACY_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"]

# Na era moderna, a versão viaja dentro de params._meta nesta chave.
META_VERSION_KEY = "io.modelcontextprotocol/protocolVersion"

# Códigos de erro JSON-RPC (os negativos de -32700 a -32600 são do JSON-RPC;
# -32022 é definido pelo MCP para versão não suportada).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
UNSUPPORTED_VERSION = -32022

# A descrição e o inputSchema são o que o modelo lê para decidir usar a
# ferramenta e montar os argumentos. Aqui é o "contrato" visto pelo LLM.
ECO_TOOL = {
    "name": "eco",
    "description": "Devolve exatamente o texto recebido. Ferramenta de teste do passo 01.",
    "inputSchema": {
        "type": "object",
        "properties": {"texto": {"type": "string", "description": "Texto a ser devolvido."}},
        "required": ["texto"],
    },
}

# Caminho do log calculado a partir deste arquivo, não do diretório atual:
# o Claude Code pode iniciar o processo de qualquer lugar.
DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "traces" / "echo.jsonl"


def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str, data: Any = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def handle_message(message: Any) -> dict | None:
    """Recebe uma mensagem JSON-RPC já decodificada e devolve a resposta.

    Devolve None quando o protocolo diz que não há resposta: notificações
    (sem "id") e respostas enviadas pelo cliente (sem "method").
    Função pura: não lê nem escreve nada, por isso é fácil de testar.
    """
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        # Sem "method" não é requisição. Se tiver id, é uma resposta do
        # cliente (não enviamos requisições, então ignoramos) ou lixo.
        if isinstance(message, dict) and ("result" in message or "error" in message):
            return None
        msg_id = message.get("id") if isinstance(message, dict) else None
        return _error(msg_id, INVALID_REQUEST, "Requisição inválida")

    if "id" not in message:
        # Notificação (ex.: notifications/initialized): só informa, não espera resposta.
        return None

    msg_id = message["id"]
    method = message["method"]
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(msg_id, INVALID_PARAMS, "params deve ser um objeto")

    # Era legada: o handshake initialize escolhe a versão da conversa toda.
    if method == "initialize":
        requested = params.get("protocolVersion")
        chosen = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
        return _result(
            msg_id,
            {"protocolVersion": chosen, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO},
        )

    # Era moderna: a versão vem em cada requisição. Se vier uma que não
    # conhecemos, recusamos dizendo quais aceitamos, para o cliente tentar de novo.
    meta = params.get("_meta") or {}
    version = meta.get(META_VERSION_KEY) if isinstance(meta, dict) else None
    if version is not None and version not in MODERN_VERSIONS:
        return _error(
            msg_id,
            UNSUPPORTED_VERSION,
            "Versão do protocolo não suportada",
            {"supported": MODERN_VERSIONS, "requested": version},
        )

    if method == "server/discover":
        return _result(
            msg_id,
            {
                "resultType": "complete",
                "supportedVersions": MODERN_VERSIONS,
                "capabilities": {"tools": {}},
                "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO},
            },
        )

    if method == "ping":
        return _result(msg_id, {})

    if method == "tools/list":
        return _result(msg_id, {"resultType": "complete", "tools": [ECO_TOOL]})

    if method == "tools/call":
        if params.get("name") != "eco":
            # Ferramenta que não existe é erro de protocolo: o cliente pediu algo inválido.
            return _error(msg_id, INVALID_PARAMS, "Ferramenta desconhecida")
        arguments = params.get("arguments") or {}
        texto = arguments.get("texto") if isinstance(arguments, dict) else None
        if not isinstance(texto, str):
            # Argumento ruim é erro de EXECUÇÃO: vai no resultado com isError,
            # para o modelo ler a mensagem e corrigir a chamada.
            return _result(
                msg_id,
                {
                    "resultType": "complete",
                    "content": [{"type": "text", "text": "Argumento 'texto' ausente ou não é texto."}],
                    "isError": True,
                },
            )
        return _result(
            msg_id,
            {"resultType": "complete", "content": [{"type": "text", "text": texto}], "isError": False},
        )

    return _error(msg_id, METHOD_NOT_FOUND, f"Método não suportado: {method}")


def _log(log_path: Path, direction: str, message: Any) -> None:
    """Acrescenta uma linha ao log: quando, direção (entrada/saida) e a mensagem."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "quando": datetime.now(timezone.utc).isoformat(),
        "direcao": direction,
        "mensagem": message,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def serve(stdin: TextIO, stdout: TextIO, log_path: Path) -> None:
    """Laço do transporte stdio: lê uma linha, responde uma linha."""
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            # JSON quebrado não derruba o server: responde o erro e segue.
            _log(log_path, "entrada", {"bruto": line})
            response = _error(None, PARSE_ERROR, "JSON inválido")
        else:
            _log(log_path, "entrada", message)
            response = handle_message(message)
        if response is None:
            continue
        # json.dumps escapa quebras de linha dentro das strings ("\n" vira
        # "\\n"), então cada resposta ocupa exatamente uma linha.
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()  # sem flush, a resposta pode ficar presa no buffer
        _log(log_path, "saida", response)


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    log_path = Path(os.environ.get("ECHO_LOG_PATH", DEFAULT_LOG_PATH))
    serve(sys.stdin, sys.stdout, log_path)


if __name__ == "__main__":
    main()
```

Crie `.mcp.json` (registra o server para o Claude Code neste projeto):

```json
{
  "mcpServers": {
    "eco": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--quiet", "python", "echo/echo_server.py"]
    }
  }
}
```

- [ ] **Step 3: testes passam.** `uv run pytest tests/test_echo_server.py -v`. Esperado: `12 passed`. Depois `uv run pytest -q`: `13 passed`.

- [ ] **Step 4: nota do passo.** Crie `docs/steps/01-eco-mcp.md`:

```markdown
# Passo 01: eco MCP feito à mão

## O que mudou

- `echo/echo_server.py`: server MCP sem SDK, só biblioteca padrão, com a ferramenta `eco`. Atende a era moderna do protocolo (2026-07-28: `server/discover`, versão em `params._meta`) e a legada (`initialize`).
- Cada mensagem que entra e sai é gravada em `traces/echo.jsonl` (ignorado pelo git).
- `.mcp.json` registra o server `eco` para o Claude Code neste projeto.
- Testes de `handle_message` (sem processo) e um teste que roda o script via stdio.

## Como rodar

    uv run pytest tests/test_echo_server.py -v

Para ver o protocolo de verdade:

1. Saia e abra de novo o Claude Code na raiz do projeto. Ele pergunta se aprova o server `eco` do `.mcp.json`: aprove.
2. Rode `/mcp` e confira que `eco` aparece conectado.
3. Peça: "use a ferramenta eco com o texto olá".
4. Em outro terminal: `jq -c '[.direcao, .mensagem.method // .mensagem.id]' traces/echo.jsonl` para ver a sequência, e `jq . traces/echo.jsonl | less` para ver tudo.

Também dá para conversar com o server à mão, sem Claude Code:

    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | uv run python echo/echo_server.py

## O que observar

- **Qual era o Claude Code usou:** a primeira mensagem do log é `server/discover` ou `initialize`? Se for `server/discover`, veja se as requisições seguintes trazem `_meta` com a versão.
- **stdout é sagrado:** um `print()` de depuração no server quebraria o protocolo. É por isso que o log vai para arquivo.
- **Notificações não têm resposta:** mensagens sem `id` aparecem como "entrada" sem "saida" correspondente.
- **Dois tipos de erro:** ferramenta desconhecida é erro JSON-RPC (o cliente errou o pedido); argumento ruim é `isError: true` no resultado (a ferramenta falhou e o modelo pode ler e corrigir). O server do passo 10 usa essa mesma distinção.
- **A descrição da ferramenta é contexto:** o texto de `description` e `inputSchema` é o que o modelo recebe sobre o `eco`. Repare no `tools/list` do log.

## Pergunta de previsão

Antes de abrir o log: quantas mensagens você espera entre o Claude Code iniciar o server e o `tools/call` do eco? E o modelo vai mandar `texto` exatamente "olá", ou pode mudar algo?
```

- [ ] **Step 5: commit.** `git add echo/echo_server.py tests/test_echo_server.py .mcp.json docs/steps/01-eco-mcp.md` e `git commit -m "feat(step-01): eco MCP feito à mão"`.

---

## Depois da execução (arquiteto, fora do Meister)

1. Revisar o diff e rodar `uv run pytest` na raiz.
2. Merge em `main`, tag `step-01`, push.
3. A verificação com o Claude Code real (Como rodar, itens 1 a 4) é feita pelo usuário; registrar a resposta da pergunta de previsão e o que o log mostrou na própria nota, num commit `docs(step-01): o que o log mostrou`.
4. Parar e esperar o usuário estudar o passo.

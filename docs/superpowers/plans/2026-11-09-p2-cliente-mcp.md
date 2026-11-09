# P2, passo extra: cliente MCP de terminal para o taxlaw (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-09-p2-cliente-mcp.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** um cliente MCP de terminal (`client/taxlaw_client.py`), desacoplado do pacote `taxlaw`, que consulta o server pelo stdio com o SDK oficial: `ferramentas`, `buscar` e `obter`, saída legível ou `--json`, e códigos de saída 0/1/2.

**Architecture:** um script fora de `src/`, como o `echo/`. Quatro partes: `server_params` (lê a entrada `taxlaw` do `.mcp.json` ou o `--server`), `list_tools`/`call` (a única parte que fala MCP: `Client(stdio_client(params, errlog=devnull))` com teto de 30 s), `render_*` (funções puras de dicionário para texto) e `main` (argparse). O server, as ferramentas e o pacote não mudam.

**Tech Stack:** Python 3.13, SDK `mcp` 2.3.0 (já é dependência), `anyio` (vem com o SDK), argparse, pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-cliente-mcp-design.md`

## Global Constraints

- Nenhuma dependência nova; `pyproject.toml` e `uv.lock` não mudam.
- `client/taxlaw_client.py` só importa a biblioteca padrão, `anyio` e `mcp`; nunca `taxlaw`.
- Nenhuma mensagem do cliente repete os argumentos; em erro do server, só o texto que o server devolveu.
- Códigos de saída: 0 sucesso (inclusive `encontrado: false`), 1 `isError` do server, 2 erro do cliente (uso, configuração, server que não sobe, tempo esgotado), sem traceback.
- `produz_efeitos_na_data`: `true` → "sim", `false` → "não", `null` → "não se sabe". Nunca "não" no lugar de "não sei".
- O cliente só envia as opções dadas; os padrões são os do server.
- Testes 100% offline e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes (o cliente é carregado com `importlib.util.spec_from_file_location`, como `tests/test_echo_server.py`).
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês.
- Não editar nada em `src/`, `hooks/`, `.claude/`, `.kiro/`, `corpus/`, `.mcp.json`, `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-09 no protótipo)

- `mcp.client.Client` aceita como `server` o gerenciador de contexto de `mcp.client.stdio.stdio_client(params, errlog=...)`; assim o stderr do server (logs do SDK, como `Tool 'buscar_dispositivos' failed: ...`) vai para `/dev/null`.
- Comando inexistente em `--server`: o `Client` levanta `FileNotFoundError` ao subir; o cliente traduz em código 2.
- Rodado de `/tmp`: `ferramentas` lista `buscar_dispositivos` e `obter_dispositivo` com `consulta (obrigatório)` e `id (obrigatório)`; `buscar "zona franca de manaus" --limite 2` → `ADCT.art126.incIII.alia` (relevância 0,40) e `ADCT.art92-B`; `obter CF.art156-A.par1.incIX --data 2030-06-01` → `versão EC132.art3`; "receita de bolo de chocolate" → "Nada encontrado: relevância máxima 0.111 abaixo do limiar 0.15", código 0; `--limite 11` → stderr `{"erro": "entrada_invalida", ...}`, código 1.
- `obter CF.art155.par3 --data 2033-01-01` mostra `observação: revogado a partir de 2033-01-01 (EC 132/2023, art. 22, II, a)` e "produz efeitos na data: não".
- Verificação de mutação no protótipo: "null vira não", "isError sai com 0", "sem cwd", "filho sem texto", "não encontrado vira lista vazia", "manda padrão próprio" e "json sem acentos" quebram ao menos um teste.

## Review Focus

- O cliente mandar seus próprios padrões em vez de deixar os do server (teste `test_only_given_options_are_sent_defaults_are_the_servers`).
- `--json` escapar acentos (`§`) em vez de imprimi-los (teste `test_json_output_keeps_accents_literal`).
- Rodar de outro diretório e o `uv run` do `.mcp.json` não achar o projeto (testes `test_server_params_from_the_real_mcp_json`, `test_runs_as_a_script_from_another_directory` e `test_shared_mcp_json_command_works`).
- Um campo que o server deixar de mandar derrubar o cliente com exceção (teste `test_missing_fields_become_dash_not_exceptions`).
- CPF numa consulta aparecer em alguma saída do cliente (teste `test_taxpayer_id_is_blocked_by_the_server_without_echo`).

---

### Task 1: Cliente MCP de terminal

**Files:**
- Create: `client/taxlaw_client.py`
- Create: `tests/test_taxlaw_client.py`
- Create: `docs/steps/cliente-mcp.md`

**Interfaces:**
- Consumes: o server `taxlaw` pelo protocolo (comando da entrada `taxlaw` de `.mcp.json`, ou `python -m taxlaw.server`); o contrato das ferramentas `buscar_dispositivos` e `obter_dispositivo` (spec principal, seção 6); `taxlaw.synthetic_ids.make_cpf` só nos testes.
- Produces: `client/taxlaw_client.py` com `ClientError`, `DEFAULT_MCP_JSON`, `server_params(mcp_json, name="taxlaw", override=None) -> StdioServerParameters`, `list_tools(params) -> list`, `call(params, tool, arguments) -> CallToolResult`, `render_busca(data) -> str`, `render_dispositivo(data) -> str`, `render_ferramentas(tools) -> str`, `_parser()`, `_arguments(args) -> (tool, arguments)`, `main(argv=None) -> int`.

- [ ] **Step 1: testes que falham.** Crie `tests/test_taxlaw_client.py`:

```python
"""Testes do cliente MCP de terminal (`client/taxlaw_client.py`).

O cliente fica fora do pacote `taxlaw` (como o `echo/`), então é carregado
pelo caminho do arquivo. Os testes de ponta a ponta sobem o server de verdade
via stdio com o próprio Python da suíte (`--server`), sem depender do `uv`;
um teste separado usa o comando do `.mcp.json`. CPF/CNPJ são sintéticos,
gerados em tempo de execução.
"""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from taxlaw.synthetic_ids import make_cpf

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "client" / "taxlaw_client.py"
_spec = importlib.util.spec_from_file_location("taxlaw_client", SCRIPT)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

SERVER = f"{sys.executable} -m taxlaw.server"


def run(capsys, *argv):
    code = cli.main(["--server", SERVER, *argv])
    out, err = capsys.readouterr()
    return code, out, err


# ------------------------------------------------------------------ formatação (sem server)

EFFECTS = {"desde": "2027-01-01", "ate": "2032-12-31", "fundamento": "EC 132/2023, art. 23, I", "metodo": "automatico"}


@pytest.mark.parametrize(("value", "word"), [(True, "sim"), (False, "não"), (None, "não se sabe")])
def test_three_effect_states(value, word):
    data = {"encontrado": True, "id": "X", "citacao": "X", "texto": "t", "efeitos": {**EFFECTS, "produz_efeitos_na_data": value}}
    assert f"produz efeitos na data: {word}" in cli.render_dispositivo(data)


def test_device_with_observation_truncation_and_child_without_text():
    data = {
        "encontrado": True, "id": "CF.art1", "citacao": "CF, art. 1º", "texto": "Art. 1º …", "versao": "EC132.art1",
        "origem": "EC 132/2023, art. 1º", "alteracao": "alterado", "data_referencia": "2030-06-01",
        "filhos": [{"citacao": "CF, art. 1º, I", "texto": "I - um;"}, {"citacao": "CF, art. 1º, II", "texto": None}],
        "efeitos": {**EFFECTS, "produz_efeitos_na_data": False},
        "outras_versoes": [{"versao": "EC132.art4", "efeitos": {"desde": "2033-01-01", "ate": None}}],
        "observacao": "redação anterior não incluída no corpus", "truncado": True,
        "fonte_url": "https://exemplo.invalid", "corpus": {"versao": "0123456789abcdef" * 4, "coletado_em": "2026-11-06"},
    }
    text = cli.render_dispositivo(data)
    assert "CF, art. 1º, I: I - um;" in text
    assert "CF, art. 1º, II: (não coube no teto; peça este id)" in text
    assert "outras versões: EC132.art4 (desde 2033-01-01)" in text
    assert "observação: redação anterior não incluída no corpus" in text and "truncado" in text
    assert "01234567…" in text and "012345678" not in text  # só 8 caracteres do hash


def test_not_found_messages():
    assert cli.render_busca({"encontrado": False, "consulta": "bolo", "motivo": "abaixo do limiar"}).endswith("Nada encontrado: abaixo do limiar")
    assert cli.render_dispositivo({"encontrado": False, "id": "XX", "motivo": "id inexistente no corpus"}) == "Não encontrado: XX (id inexistente no corpus)"


def test_missing_fields_become_dash_not_exceptions():
    text = cli.render_busca({"encontrado": True, "resultados": [{"id": "X"}]})
    assert "relevância —" in text and "efeitos: —" in text
    assert cli.render_dispositivo({"encontrado": True}).startswith("—   [—]")


# ------------------------------------------------------------------ configuração


def test_server_params_from_the_real_mcp_json():
    params = cli.server_params(ROOT / ".mcp.json")
    assert (params.command, params.args) == ("uv", ["run", "--quiet", "python", "-m", "taxlaw.server"])
    assert Path(params.cwd) == ROOT


def test_server_override_is_split_like_a_shell():
    params = cli.server_params(ROOT / ".mcp.json", override='python -m "taxlaw.server"')
    assert (params.command, params.args) == ("python", ["-m", "taxlaw.server"])


@pytest.mark.parametrize("content", [None, "{nao e json", '{"mcpServers": {"eco": {"command": "x"}}}'])
def test_bad_configuration_is_client_error_code_2(tmp_path, capsys, content):
    config = tmp_path / ".mcp.json"
    if content is not None:
        config.write_text(content, encoding="utf-8")
    assert cli.main(["--mcp-json", str(config), "ferramentas"]) == 2
    assert capsys.readouterr().err.startswith("erro: ")


# ------------------------------------------------------------------ de ponta a ponta (server real via stdio)


def test_tools_lists_both(capsys):
    code, out, _ = run(capsys, "ferramentas")
    assert code == 0 and "buscar_dispositivos:" in out and "obter_dispositivo:" in out and "consulta (obrigatório)" in out


def test_search_real(capsys):
    code, out, _ = run(capsys, "buscar", "zona franca de manaus", "--limite", "2")
    assert code == 0 and "[ADCT.art126.incIII.alia]" in out and "relevância 0," in out


def test_get_real_with_date(capsys):
    code, out, _ = run(capsys, "obter", "CF.art156-A.par1.incIX", "--data", "2030-06-01")
    assert code == 0 and "versão EC132.art3" in out and "produz efeitos na data: sim" in out


def test_json_is_the_structured_content(capsys):
    code, out, _ = run(capsys, "--json", "obter", "CF.art155.par3", "--data", "2033-01-01", "--sem-filhos")
    data = json.loads(out)
    assert code == 0 and data["filhos"] == [] and data["observacao"].startswith("revogado a partir de 2033-01-01")
    assert data["data_referencia"] == "2033-01-01"


def test_not_found_is_exit_0(capsys):
    code, out, _ = run(capsys, "buscar", "receita de bolo de chocolate")
    assert code == 0 and "Nada encontrado:" in out


def test_server_error_is_exit_1_with_the_server_message(capsys):
    code, out, err = run(capsys, "buscar", "ibs", "--limite", "11")
    assert code == 1 and out == "" and json.loads(err)["erro"] == "entrada_invalida"


def test_taxpayer_id_is_blocked_by_the_server_without_echo(capsys):
    # Fora do Claude Code não há hook: quem bloqueia é o server (camada 2).
    number = make_cpf("987654321", formatted=True)
    code, out, err = run(capsys, "buscar", f"situação do contribuinte {number}")
    assert code == 1 and json.loads(err)["erro"] == "dados_de_contribuinte"
    for shown in (out, err):
        assert number not in shown and number.replace(".", "").replace("-", "") not in shown


def test_server_that_does_not_start_is_exit_2(capsys):
    assert cli.main(["--server", "comando-que-nao-existe-xyz", "ferramentas"]) == 2
    assert "não consegui falar com o server" in capsys.readouterr().err


def test_shared_mcp_json_command_works(capsys):
    # Sem --server: o mesmo comando do Claude Code (uv run ... taxlaw.server).
    assert cli.main(["ferramentas"]) == 0
    assert "obter_dispositivo:" in capsys.readouterr().out


# ------------------------------------------------------------------ desacoplamento


def test_client_does_not_import_taxlaw():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "taxlaw" not in modules and "mcp" in modules


def test_runs_as_a_script_from_another_directory(tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--server", SERVER, "obter", "CF.art195.incV"],
        capture_output=True, text=True, cwd=tmp_path, timeout=60,
    )
    assert done.returncode == 0 and "CF, art. 195, V" in done.stdout and done.stderr == ""


# ------------------------------------------------------------------ argumentos enviados


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["buscar", "ibs"], ("buscar_dispositivos", {"consulta": "ibs"})),
        (["buscar", "ibs", "--limite", "3", "--data", "2030-06-01"], ("buscar_dispositivos", {"consulta": "ibs", "limite": 3, "data_referencia": "2030-06-01"})),
        (["obter", "CF.art1"], ("obter_dispositivo", {"id": "CF.art1"})),
        (["obter", "CF.art1", "--sem-filhos"], ("obter_dispositivo", {"id": "CF.art1", "incluir_filhos": False})),
    ],
)
def test_only_given_options_are_sent_defaults_are_the_servers(argv, expected):
    assert cli._arguments(cli._parser().parse_args(argv)) == expected


def test_json_output_keeps_accents_literal(capsys):
    code, out, _ = run(capsys, "--json", "obter", "CF.art155.par3", "--sem-filhos")
    assert code == 0 and '"citacao": "CF, art. 155, § 3º"' in out
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_taxlaw_client.py -q` → erro de coleta `FileNotFoundError` (o `client/taxlaw_client.py` ainda não existe).

- [ ] **Step 3: implemente.** Crie `client/taxlaw_client.py`:

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
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

# client/taxlaw_client.py → parents[1] é a raiz do repositório.
DEFAULT_MCP_JSON = Path(__file__).resolve().parents[1] / ".mcp.json"
SERVER_NAME = "taxlaw"
TIMEOUT_SECONDS = 30


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


# ------------------------------------------------------------------ MCP (a única parte que fala protocolo)


def _run(params: StdioServerParameters, operation):
    """Abre o Client via stdio, roda `operation(client)` com teto de tempo e fecha.

    O stderr do server (logs do SDK) vai para /dev/null: o stderr do cliente
    fica só com as mensagens do cliente.
    """

    async def main():
        with open(os.devnull, "w") as quiet, anyio.fail_after(TIMEOUT_SECONDS):
            async with Client(stdio_client(params, errlog=quiet)) as client:
                return await operation(client)

    try:
        return anyio.run(main)
    except TimeoutError:
        raise ClientError(f"o server não respondeu em {TIMEOUT_SECONDS} s") from None
    except Exception as exc:  # noqa: BLE001 - qualquer falha de subir/conversar vira código 2
        raise ClientError(f"não consegui falar com o server ({exc.__class__.__name__})") from None


def list_tools(params: StdioServerParameters) -> list:
    return _run(params, lambda client: _tools(client))


async def _tools(client):
    return (await client.list_tools()).tools


def call(params: StdioServerParameters, tool: str, arguments: dict[str, Any]):
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
    parser.add_argument("--server", help='comando do server, no lugar do .mcp.json (ex.: "python -m taxlaw.server")')
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
        params = server_params(args.mcp_json, override=args.server)
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

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_taxlaw_client.py -q` → 27 passed; `uv run pytest -q` → 407 passed. Confira também, de outra pasta: `cd /tmp && uv run --project <raiz do repositório> python <raiz do repositório>/client/taxlaw_client.py obter CF.art195.incV` imprime `CF, art. 195, V` e sai com 0.

- [ ] **Step 5: nota do passo.** Crie `docs/steps/cliente-mcp.md`:

````markdown
# Passo extra: cliente MCP de terminal para o taxlaw

## O que mudou

- **`client/taxlaw_client.py`:** uma ferramenta de terminal que é cliente MCP de verdade. Ela sobe o server como processo filho (stdio) com o `Client` do SDK oficial, faz **uma** chamada e sai.
  - `ferramentas`: lista as ferramentas e os parâmetros.
  - `buscar CONSULTA [--data] [--limite]`
  - `obter ID [--data] [--sem-filhos]`
  - `--json`: imprime o `structuredContent` cru.
  - `--server "cmd args"`: troca o comando do server.
- **Acha o server pelo `.mcp.json`:** a mesma entrada `taxlaw` que o Claude Code usa (e o Kiro, pelo `.kiro/settings/mcp.json`). O `cwd` é a pasta do `.mcp.json`, então o cliente funciona de qualquer diretório.
- **Desacoplado, como o `echo/`:** não importa o pacote `taxlaw`, só a biblioteca padrão e o `mcp`, e um teste confere os imports. Os nomes de ferramentas e campos são os do contrato público do server.
- **Códigos de saída:** 0 para sucesso, **inclusive "não encontrado"**; 1 para erro devolvido pelo server (`isError`); 2 para erro do cliente (uso, configuração, server que não sobe).
- **Os logs do server** (stderr do processo filho) vão para `/dev/null`, para o stderr do cliente ter só as mensagens dele.

## Como rodar

```
uv run python client/taxlaw_client.py ferramentas
uv run python client/taxlaw_client.py buscar "zona franca de manaus" --limite 2
uv run python client/taxlaw_client.py obter CF.art156-A.par1.incIX --data 2030-06-01
uv run python client/taxlaw_client.py --json obter CF.art155.par3 --data 2033-01-01 --sem-filhos
uv run pytest tests/test_taxlaw_client.py -v
```

## O que observar

- **Três clientes, um server.** O Claude Code (revisão 2026-07-28, sem sessão), o Kiro (`initialize`, 2025-11-25) e este cliente sobem o mesmo comando do `.mcp.json`. O SDK do cliente negocia a versão sozinho.
- **A guarda sem hook.** Fora do Claude Code não existe hook. Um CPF numa consulta deste cliente é bloqueado pelo **server** (camada 2): o cliente sai com código 1, a mensagem é `dados_de_contribuinte`, e o número não aparece em nenhuma saída.
- **"Não encontrado" sai com código 0.** Num script, o código de saída separa "a consulta funcionou e a resposta é 'nada'" de "algo deu errado". É a mesma regra do server (`isError: false`).
- **Os padrões são do server.** O cliente só envia as opções que você deu. Se o server mudar o `limite` padrão, o cliente segue a mudança sem alteração.
- **O tempo de cada chamada** inclui subir o server e montar o índice: cerca de 1 s com `--server` e um pouco mais com o `uv run` do `.mcp.json`. É o custo de não manter o server vivo entre as consultas, uma decisão da spec.

## Pergunta de previsão

Um script do P3 vai rodar 100 perguntas com este cliente, uma por processo. Onde está o custo maior: na busca, no `obter`, ou em subir o server 100 vezes? Que mudança, e em qual camada, resolveria isso sem perder o desacoplamento?
````

- [ ] **Step 6: commit.** `git add client/taxlaw_client.py tests/test_taxlaw_client.py docs/steps/cliente-mcp.md && git commit -m "feat(cliente): cliente MCP de terminal para o taxlaw"`

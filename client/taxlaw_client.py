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

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

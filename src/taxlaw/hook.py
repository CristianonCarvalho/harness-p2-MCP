"""Hook `PreToolUse` do Claude Code: bloqueia CPF/CNPJ antes de a chamada sair (critério 2).

O Claude Code roda o hook antes de cada chamada de ferramenta cujo nome casa
com o matcher em `.claude/settings.json` (as ferramentas `mcp__taxlaw__*`,
`WebSearch` e `WebFetch`). Ele recebe a chamada em JSON no stdin, com
`tool_name` e `tool_input` (os argumentos que o modelo gerou).

Contrato com o Claude Code (documentação de hooks, conferida em 2026-11-08):
- código 0: a chamada segue o fluxo normal de permissões;
- código 2: a chamada é bloqueada, e o stderr volta ao modelo como motivo;
- **qualquer outro código não bloqueia** (a chamada segue). Por isso este hook
  nunca termina com 1: entrada ilegível ou erro interno também dão 2. Na
  dúvida, bloqueia (fail closed).

O motivo diz o tipo, a quantidade e o campo, nunca o número.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from taxlaw.guard import find_in_arguments

ALLOW = 0
BLOCK = 2

UNREADABLE = "não foi possível ler os argumentos da chamada; bloqueada por precaução"
INTERNAL_ERROR = "erro interno do hook; chamada bloqueada por precaução"


def check(payload: object) -> str | None:
    """Motivo para bloquear a chamada, ou None para deixá-la seguir."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return UNREADABLE
    return find_in_arguments(payload["tool_input"])


def main(stdin: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Lê a chamada do stdin e devolve o código de saída do hook."""
    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    try:
        try:
            payload = json.loads(stdin.read())
        except ValueError:  # JSON inválido (UnicodeDecodeError também é ValueError)
            payload = None
        reason = check(payload)
    except Exception:  # noqa: BLE001 - qualquer falha bloqueia; nunca sair com 1
        reason = INTERNAL_ERROR
    if reason is None:
        return ALLOW
    stderr.write(f"Chamada bloqueada pelo hook do projeto: {reason}. CPF e CNPJ não são enviados a ferramentas.\n")
    return BLOCK

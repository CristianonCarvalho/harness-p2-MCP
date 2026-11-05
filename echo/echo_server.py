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

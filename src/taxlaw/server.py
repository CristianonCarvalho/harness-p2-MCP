"""MCP server via stdio: uma camada fina sobre `taxlaw.tools` (spec, seção 4).

Toda a lógica está em `tools.py`. Aqui ficam só três coisas que dependem do
protocolo:

1. **Os schemas.** O SDK gera o `inputSchema` da assinatura e o `outputSchema`
   do tipo de retorno (TypedDicts abaixo). Atenção: o SDK valida a saída
   contra o TypedDict e **descarta do `structuredContent` toda chave que não
   está nele**, enquanto o texto continua com ela. Por isso cada campo que
   `tools.py` devolve precisa estar declarado aqui; um teste confere que
   `structuredContent` e o texto são iguais.
2. **A guarda antes do SDK.** O SDK valida os argumentos (pydantic) antes de
   chamar a ferramenta, e a mensagem de erro de validação **repete o valor
   recebido** (`input_value=...`). Um CPF mandado em `limite` voltaria inteiro
   no erro. Por isso `TaxLawServer.call_tool` varre todos os argumentos crus,
   inclusive chaves desconhecidas e valores aninhados, antes de qualquer
   validação, e reescreve os erros de validação só com o nome do campo.
3. **Os erros.** `tools.ToolError`, a guarda e a validação viram `isError`
   com o texto igual a um JSON `{"erro": código, "mensagem": ...}`, sem o
   prefixo "Error executing tool" do SDK. "Não encontrei" não é erro.

Rodar: `uv run python -m taxlaw.server` (fala JSON-RPC no stdin/stdout).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Any, NotRequired, TypedDict

from pydantic import Field, ValidationError

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as SDKToolError
from mcp.types import ToolAnnotations

from taxlaw import tools
from taxlaw.guard import describe_findings, find_taxpayer_ids

SERVER_NAME = "taxlaw"  # o Claude Code mostra as ferramentas como mcp__taxlaw__<nome>

# Só leitura, sem rede, mesma entrada → mesma saída.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# ------------------------------------------------------------------ schemas de saída


class Corpus(TypedDict):
    versao: str  # sha256 de dispositivos.json
    coletado_em: str


class Efeitos(TypedDict):
    desde: str | None
    ate: str | None
    fundamento: str | None
    fundamento_ate: str | None
    metodo: str
    produz_efeitos_na_data: bool | None  # null = não sei


class Intervalo(TypedDict):
    desde: str | None
    ate: str | None


class OutraVersao(TypedDict):
    versao: str
    efeitos: Intervalo


class Resultado(TypedDict):
    id: str
    versao: str
    citacao: str
    trecho: str
    pontuacao: float
    efeitos: Efeitos
    outras_versoes: list[OutraVersao]


class BuscaSaida(TypedDict):
    encontrado: bool
    consulta: str
    data_referencia: str
    resultados: list[Resultado]
    motivo: str | None
    corpus: Corpus


class Filho(TypedDict):
    id: str
    versao: str
    citacao: str
    texto: str | None  # None quando não coube no teto
    produz_efeitos_na_data: bool | None


class DispositivoSaida(TypedDict):
    # Sempre presentes:
    encontrado: bool
    id: str
    data_referencia: str
    corpus: Corpus
    # Só quando encontrado=false:
    motivo: NotRequired[str]
    # Só quando encontrado=true:
    versao: NotRequired[str]
    citacao: NotRequired[str]
    norma: NotRequired[str]
    origem: NotRequired[str]
    alteracao: NotRequired[str]
    texto: NotRequired[str]
    filhos: NotRequired[list[Filho]]
    vigor_desde: NotRequired[str | None]
    efeitos: NotRequired[Efeitos]
    outras_versoes: NotRequired[list[OutraVersao]]
    observacao: NotRequired[str | None]
    truncado: NotRequired[bool]
    fonte_url: NotRequired[str]


# ------------------------------------------------------------------ server


class TaxLawError(SDKToolError):
    """Erro previsto do taxlaw: o texto é só o JSON `{"erro": código, "mensagem": ...}`."""

    def __init__(self, code: str, message: str):
        super().__init__(json.dumps({"erro": code, "mensagem": message}, ensure_ascii=False))


def _scan(value: Any, path: str) -> str | None:
    """Caminho do primeiro texto com CPF/CNPJ válido (chaves também), ou None."""
    if isinstance(value, str):
        findings = find_taxpayer_ids(value)
        return f"{describe_findings(findings)} no campo '{path}'" if findings else None
    if isinstance(value, dict):
        for key, item in value.items():
            found = _scan(str(key), f"{path}.<chave>") or _scan(item, f"{path}.{key}")
            if found:
                return found
    if isinstance(value, list | tuple):
        for i, item in enumerate(value):
            found = _scan(item, f"{path}[{i}]")
            if found:
                return found
    return None


class TaxLawServer(MCPServer):
    """MCPServer com a guarda de CPF/CNPJ antes da validação do SDK."""

    async def call_tool(self, name, arguments, context=None):  # type: ignore[override]
        for key, value in (arguments or {}).items():
            found = _scan(str(key), "<chave>") or _scan(value, key)
            if found:
                raise TaxLawError("dados_de_contribuinte", found)
        try:
            return await super().call_tool(name, arguments, context)
        except SDKToolError as exc:
            # O SDK embrulha o erro da ferramenta em "Error executing tool <nome>: ...";
            # desembrulhamos para o texto ser só o JSON, igual ao da guarda acima.
            if isinstance(exc.__cause__, TaxLawError):
                raise exc.__cause__ from None
            if isinstance(exc.__cause__, ValidationError):
                # Só o nome dos campos: o valor rejeitado é dado do chamador.
                fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.__cause__.errors()})
                raise TaxLawError("entrada_invalida", "argumento inválido: " + ", ".join(fields)) from None
            raise


def _call(function, **kwargs) -> Any:
    """Chama a função pura e converte `tools.ToolError` no erro do SDK (isError)."""
    try:
        return function(**kwargs)
    except tools.ToolError as exc:
        raise TaxLawError(exc.code, exc.message) from None


DATE_FIELD = Field(
    default=None,
    description="Data AAAA-MM-DD em que a pergunta se coloca. Ausente: a data de hoje (ecoada na resposta).",
)


def build_server(ctx: tools.Context | None = None, *, today: date | None = None) -> TaxLawServer:
    """Monta o server. `ctx` e `today` existem para os testes; em produção, o corpus real e hoje."""
    context = ctx or tools.load_context()
    server = TaxLawServer(SERVER_NAME, version="0.1.0")

    @server.tool(annotations=READ_ONLY)
    def buscar_dispositivos(
        consulta: Annotated[str, Field(description="Palavras a buscar no texto da EC 132/2023 e dos dispositivos da CF e do ADCT que ela inclui ou altera (1 a 500 caracteres).")],
        data_referencia: Annotated[str | None, DATE_FIELD] = None,
        # strict: sem isso o pydantic aceitaria True e "5" como inteiros, e o
        # server divergiria de tools.py, que os rejeita.
        limite: Annotated[int, Field(strict=True, description="Número máximo de resultados, de 1 a 10.")] = 5,
    ) -> BuscaSaida:
        """Busca dispositivos da reforma tributária (EC 132/2023) por palavras.

        Cada resultado traz a citação, um trecho, a versão do texto que vale na
        data de referência e as datas de efeito com fundamento. Sem resultado
        relevante: encontrado=false com motivo. Use obter_dispositivo para o
        texto completo antes de citar.
        """
        return _call(tools.buscar_dispositivos, ctx=context, consulta=consulta, data_referencia=data_referencia, limite=limite, today=today)

    @server.tool(annotations=READ_ONLY)
    def obter_dispositivo(
        id: Annotated[str, Field(description="Id do dispositivo, como devolvido pela busca (ex.: CF.art156-A.par1.incIX).")],
        data_referencia: Annotated[str | None, DATE_FIELD] = None,
        incluir_filhos: Annotated[bool, Field(strict=True, description="Incluir os filhos diretos (incisos, alíneas, parágrafos).")] = True,
    ) -> DispositivoSaida:
        """Texto completo de um dispositivo na versão que vale na data de referência.

        Traz citação, origem na EC, filhos diretos, datas de efeito com
        fundamento, se produz efeitos na data (true, false ou null quando não
        se sabe), as outras versões e observações (redação anterior fora do
        corpus, revogação). Id inexistente: encontrado=false.
        """
        return _call(tools.obter_dispositivo, ctx=context, id=id, data_referencia=data_referencia, incluir_filhos=incluir_filhos, today=today)

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()

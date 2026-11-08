# P2, passo 10: o server MCP via stdio (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-08-p2-passo-10-server.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** expor `buscar_dispositivos` e `obter_dispositivo` (de `taxlaw.tools`) como ferramentas MCP via stdio, com `inputSchema`/`outputSchema`, `structuredContent` igual ao retorno de `tools.py`, erros como `isError` com JSON, e a guarda de CPF/CNPJ rodando antes da validação do SDK; registrar o server no `.mcp.json`.

**Architecture:** Task 1 adiciona o SDK (`mcp>=2,<3`) e cria `taxlaw.server`: `TaxLawServer` (subclasse de `MCPServer` que sobrescreve `call_tool` para varrer os argumentos crus com a guarda, desembrulhar os erros e reescrever erros de validação só com o nome do campo), TypedDicts de saída com todos os campos, e `build_server(ctx, today)`. Task 2 testa o processo de verdade via stdio, registra o server no `.mcp.json` e escreve a nota. Nenhuma lógica nova: tudo vem de `tools.py`.

**Tech Stack:** Python 3.13, SDK `mcp` 2.3.0 (`mcp.server.MCPServer`, `mcp.client.Client`, `mcp.client.stdio.StdioServerParameters`), `anyio` (vem com o SDK), pydantic (vem com o SDK), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seções 3, 4, 6, 7 "Camada 2", 9 e 10)

## Global Constraints

- Única dependência nova: `mcp>=2,<3`, adicionada só com `uv add "mcp>=2,<3"` (muda `pyproject.toml` e `uv.lock`; nada mais nesses arquivos).
- `server.py` não tem lógica de domínio: busca, versões, validação de valores e mensagens vêm de `tools.py`.
- Nenhuma mensagem de erro contém o número de CPF/CNPJ nem o valor rejeitado de um argumento.
- "Não encontrei" é `isError: false`; `isError: true` só com `entrada_invalida` ou `dados_de_contribuinte`, e o texto do erro é só o JSON `{"erro": ..., "mensagem": ...}`.
- O retorno só tem dados; nada de `instructions` no server (spec, seção 2).
- Testes 100% offline e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes; testes assíncronos com `anyio.run` dentro de funções de teste comuns (sem plugin novo).
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório (testes geram com `taxlaw.synthetic_ids`).
- Mensagens, comentários e notas em português; identificadores em inglês; nomes e campos expostos ao modelo em português. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `corpus/`, nem os módulos existentes em `src/taxlaw/` (`tools.py`, `versions.py`, `search.py`, `corpus.py`, `guard.py`, `synthetic_ids.py`, `ingest/`).
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-08 com `mcp` 2.3.0)

- `MCPServer.tool()` gera o `inputSchema` da assinatura (descrições via `Annotated[..., Field(description=...)]`) e o `outputSchema` do tipo de retorno; um `TypedDict` com `NotRequired` vira propriedade fora de `required`.
- O SDK valida a saída contra o tipo de retorno e **descarta do `structuredContent` toda chave que não está no TypedDict**; o texto (`content[0].text`, JSON com `indent=2`) continua com ela.
- O SDK valida os argumentos com pydantic **antes** da ferramenta; o erro volta como `isError` com o texto `Error executing tool <nome>: 1 validation error ... input_value='<o valor recebido>'`. Um CPF mandado em `limite` voltaria inteiro.
- `MCPServer.call_tool(name, arguments, context)` recebe os argumentos crus antes dessa validação; o SDK chama esse método para todo `tools/call` (inclusive via `Client` em processo).
- Erro levantado dentro da ferramenta como `mcp.server.mcpserver.exceptions.ToolError` vira `isError` com o prefixo `Error executing tool <nome>: `; o original fica em `__cause__`. Erro de validação: `__cause__` é `pydantic.ValidationError`.
- Em modo não estrito, pydantic converte `True` → 1 e `"5"` → 5 para `int`, e `1` e `"true"` → `True` para `bool` (`"sim"` é rejeitado); com `Field(strict=True)` todos são rejeitados.
- `Client(server)` com um `MCPServer` despacha em processo; `Client(StdioServerParameters(...))` sobe o processo filho. Os dois falam a revisão `2026-07-28` (`client.protocol_version`).
- Consultas de exemplo no corpus real: "IBS integra própria base de cálculo" em 2030 traz `CF.art156-A.par1.incIX` (versão `EC132.art3`) entre os 3 primeiros.

## Review Focus

- CPF/CNPJ num argumento de tipo errado (`limite`), numa chave, num campo desconhecido ou aninhado é bloqueado antes do SDK e o número não aparece no texto (teste `test_taxpayer_ids_are_blocked_before_the_sdk_without_echo`).
- Um campo que `tools.py` devolve e o TypedDict esquece some do `structuredContent` sem erro (teste `test_output_schemas_declare_every_field_tools_returns`).
- `limite=True`, `limite="5"` e `incluir_filhos=1` são `entrada_invalida`, como em `tools.py` (teste `test_schema_errors_are_entrada_invalida_with_field_name_only`).
- Erro vindo de `tools.py` chega sem o prefixo do SDK, como JSON puro (teste `test_tools_py_errors_come_through_as_plain_json`).
- O server sobe de qualquer diretório e acha o corpus (teste `test_stdio_server_speaks_the_stateless_revision_and_matches_tools_py`, com `cwd=tmp_path`).

---

### Task 1: SDK do MCP e `taxlaw.server`

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (só pelo comando do Step 1)
- Create: `src/taxlaw/server.py`
- Create: `tests/test_server.py`

**Interfaces:**
- Consumes: `taxlaw.tools` (`Context`, `load_context()`, `ToolError(code, message)` com `.code`/`.message`, `buscar_dispositivos(ctx, consulta, data_referencia=None, limite=5, *, today=None) -> dict`, `obter_dispositivo(ctx, id, data_referencia=None, incluir_filhos=True, *, today=None) -> dict`); `taxlaw.guard.find_taxpayer_ids`, `describe_findings`; `taxlaw.synthetic_ids.make_cpf`, `make_cnpj` (só nos testes).
- Produces: `taxlaw.server.SERVER_NAME = "taxlaw"`; `TaxLawServer(MCPServer)`; `TaxLawError(code, message)` (subclasse do `ToolError` do SDK, texto = JSON); `build_server(ctx: tools.Context | None = None, *, today: date | None = None) -> TaxLawServer`; `main()` (roda via stdio); `python -m taxlaw.server`.

- [ ] **Step 1: dependência.** `uv add "mcp>=2,<3"`. Confira: `uv pip show mcp` mostra a versão 2.x (2.3.0 em 2026-11-08) e `pyproject.toml` ganhou só a linha `"mcp>=2,<3",` em `dependencies`.

- [ ] **Step 2: testes que falham.** Crie `tests/test_server.py`:

```python
"""O server MCP em processo (sem subprocesso), com o `Client` oficial do SDK.

`Client(server)` despacha direto para o server, sem JSON-RPC: testa os schemas,
a conversão de erros e a guarda antes do SDK. O transporte stdio de verdade
fica em `test_server_stdio.py`. Usa o corpus real (só leitura) e `today` fixo.
Os CPF/CNPJ são gerados em tempo de execução a partir de bases sintéticas.
"""

import json
from datetime import date

import anyio
import pytest

from mcp.client import Client
from taxlaw import tools
from taxlaw.server import SERVER_NAME, build_server
from taxlaw.synthetic_ids import make_cnpj, make_cpf

TODAY = date(2026, 11, 7)
CTX = tools.load_context()
SERVER = build_server(CTX, today=TODAY)
CPF = make_cpf("987654321", formatted=True)
CNPJ = make_cnpj("ABCDEFGH0001")


def run(coro_fn):
    """Roda uma função assíncrona que recebe o Client conectado."""

    async def main():
        async with Client(SERVER) as client:
            return await coro_fn(client)

    return anyio.run(main)


def call(name, arguments):
    return run(lambda c: c.call_tool(name, arguments))


def error_of(result):
    """O texto de um isError é só um JSON {"erro", "mensagem"}."""
    assert result.is_error is True and result.structured_content is None
    return json.loads(result.content[0].text)


def test_lists_exactly_the_two_tools_read_only():
    tools_listed = run(lambda c: c.list_tools()).tools
    assert sorted(t.name for t in tools_listed) == ["buscar_dispositivos", "obter_dispositivo"]
    for tool in tools_listed:
        assert tool.annotations.read_only_hint is True and tool.annotations.open_world_hint is False
        assert tool.description and tool.output_schema["type"] == "object"


def test_input_schemas_match_the_spec():
    by_name = {t.name: t for t in run(lambda c: c.list_tools()).tools}
    search = by_name["buscar_dispositivos"].input_schema
    assert list(search["properties"]) == ["consulta", "data_referencia", "limite"] and search["required"] == ["consulta"]
    assert search["properties"]["limite"]["default"] == 5
    get = by_name["obter_dispositivo"].input_schema
    assert list(get["properties"]) == ["id", "data_referencia", "incluir_filhos"] and get["required"] == ["id"]
    assert get["properties"]["incluir_filhos"]["default"] is True


def test_output_schemas_declare_every_field_tools_returns():
    # O SDK descarta do structuredContent toda chave fora do schema: nenhuma pode faltar.
    by_name = {t.name: t.output_schema for t in run(lambda c: c.list_tools()).tools}
    found = tools.obter_dispositivo(CTX, "CF.art156-A.par1", "2030-06-01", today=TODAY)
    missing = tools.obter_dispositivo(CTX, "XX.art1", today=TODAY)
    assert set(found) | set(missing) == set(by_name["obter_dispositivo"]["properties"])
    search = tools.buscar_dispositivos(CTX, "zona franca de manaus", today=TODAY)
    assert set(search) == set(by_name["buscar_dispositivos"]["properties"])


@pytest.mark.parametrize(
    ("name", "arguments", "direct"),
    [
        ("buscar_dispositivos", {"consulta": "zona franca de manaus"}, lambda: tools.buscar_dispositivos(CTX, "zona franca de manaus", today=TODAY)),
        ("buscar_dispositivos", {"consulta": "receita de bolo de chocolate"}, lambda: tools.buscar_dispositivos(CTX, "receita de bolo de chocolate", today=TODAY)),
        ("obter_dispositivo", {"id": "CF.art156-A.par1", "data_referencia": "2030-06-01"}, lambda: tools.obter_dispositivo(CTX, "CF.art156-A.par1", "2030-06-01", today=TODAY)),
        ("obter_dispositivo", {"id": "CF.art155.par3", "data_referencia": "2033-01-01", "incluir_filhos": False}, lambda: tools.obter_dispositivo(CTX, "CF.art155.par3", "2033-01-01", False, today=TODAY)),
        ("obter_dispositivo", {"id": "XX.art1"}, lambda: tools.obter_dispositivo(CTX, "XX.art1", today=TODAY)),
    ],
)
def test_call_is_exactly_tools_py_in_structured_and_text(name, arguments, direct):
    result = call(name, arguments)
    expected = direct()
    assert result.is_error is False
    assert result.structured_content == expected
    assert json.loads(result.content[0].text) == expected


def test_not_found_is_not_an_error():
    result = call("buscar_dispositivos", {"consulta": "receita de bolo de chocolate"})
    assert result.is_error is False and result.structured_content["encontrado"] is False


@pytest.mark.parametrize(
    ("name", "arguments", "field"),
    [
        ("buscar_dispositivos", {"consulta": 5}, "consulta"),
        ("buscar_dispositivos", {}, "consulta"),
        ("buscar_dispositivos", {"consulta": "ibs", "limite": "abc"}, "limite"),
        ("buscar_dispositivos", {"consulta": "ibs", "limite": True}, "limite"),
        ("buscar_dispositivos", {"consulta": "ibs", "limite": "5"}, "limite"),
        ("obter_dispositivo", {"id": "CF.art155.par3", "incluir_filhos": "sim"}, "incluir_filhos"),
        ("obter_dispositivo", {"id": "CF.art155.par3", "incluir_filhos": 1}, "incluir_filhos"),
    ],
)
def test_schema_errors_are_entrada_invalida_with_field_name_only(name, arguments, field):
    error = error_of(call(name, arguments))
    assert error == {"erro": "entrada_invalida", "mensagem": f"argumento inválido: {field}"}


@pytest.mark.parametrize(
    "arguments",
    [
        {"consulta": "ibs", "limite": 11},
        {"consulta": ""},
        {"consulta": "ibs", "data_referencia": "20300601"},
    ],
)
def test_tools_py_errors_come_through_as_plain_json(arguments):
    error = error_of(call("buscar_dispositivos", arguments))
    assert error["erro"] == "entrada_invalida" and not error["mensagem"].startswith("Error executing")


@pytest.mark.parametrize(
    ("name", "arguments", "field"),
    [
        ("buscar_dispositivos", {"consulta": f"tributo do contribuinte {CPF}"}, "consulta"),
        ("buscar_dispositivos", {"consulta": "ibs", "data_referencia": CNPJ}, "data_referencia"),
        # Tipo errado: sem a guarda antes do SDK, o erro de validação repetiria o número.
        ("buscar_dispositivos", {"consulta": "ibs", "limite": CPF}, "limite"),
        ("buscar_dispositivos", {"consulta": "ibs", "extra": {"lista": ["ok", CPF]}}, "extra.lista[1]"),
        ("buscar_dispositivos", {"consulta": "ibs", "extra": {CPF: "ok"}}, "extra.<chave>"),
        ("obter_dispositivo", {"id": CNPJ}, "id"),
        ("obter_dispositivo", {CPF: "x", "id": "CF.art155.par3"}, "<chave>"),
    ],
)
def test_taxpayer_ids_are_blocked_before_the_sdk_without_echo(name, arguments, field):
    result = call(name, arguments)
    error = error_of(result)
    assert error["erro"] == "dados_de_contribuinte" and error["mensagem"].endswith(f"no campo '{field}'")
    text = result.content[0].text
    for number in (CPF, CNPJ):
        compact = number.replace(".", "").replace("-", "").replace("/", "")
        assert number not in text and compact not in text


def test_server_name_gives_the_hook_matcher_prefix():
    # O Claude Code expõe as ferramentas como mcp__taxlaw__<nome> (passo 01);
    # o hook do passo 11 casa com mcp__taxlaw__.*
    assert SERVER_NAME == "taxlaw"
```

- [ ] **Step 3: rode e veja falhar.** `uv run pytest tests/test_server.py -q` → `ModuleNotFoundError: No module named 'taxlaw.server'`.

- [ ] **Step 4: implemente.** Crie `src/taxlaw/server.py`:

```python
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
```

- [ ] **Step 5: rode e veja passar.** `uv run pytest tests/test_server.py -q` → 27 passed; `uv run pytest -q` → tudo verde.

- [ ] **Step 6: commit.** `git add pyproject.toml uv.lock src/taxlaw/server.py tests/test_server.py && git commit -m "feat(step-10): server MCP sobre tools.py, com a guarda antes do SDK"`

### Task 2: stdio de verdade, `.mcp.json` e nota

**Files:**
- Create: `tests/test_server_stdio.py`
- Modify: `.mcp.json`
- Create: `docs/steps/10-server.md`

**Interfaces:**
- Consumes: `python -m taxlaw.server` e `build_server` (Task 1); `taxlaw.tools.load_context`, `obter_dispositivo`; `mcp.client.Client`, `mcp.client.stdio.StdioServerParameters(command, args, cwd)`.
- Produces: o server `taxlaw` registrado no `.mcp.json` do projeto (ferramentas `mcp__taxlaw__buscar_dispositivos` e `mcp__taxlaw__obter_dispositivo` no Claude Code).

- [ ] **Step 1: teste.** Crie `tests/test_server_stdio.py`:

```python
"""O server como processo filho via stdio, como o Claude Code o usa.

Sobe `python -m taxlaw.server` com o mesmo interpretador da suíte, a partir
de um diretório temporário (o corpus tem de ser achado sem depender do
diretório atual), e conversa com o `Client` oficial do SDK. Nada de rede: o
processo filho só lê `corpus/dispositivos.json`.
"""

import sys
from datetime import date

import anyio

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from taxlaw import tools


def test_stdio_server_speaks_the_stateless_revision_and_matches_tools_py(tmp_path):
    params = StdioServerParameters(command=sys.executable, args=["-m", "taxlaw.server"], cwd=tmp_path)
    ctx = tools.load_context()

    async def main():
        # Teto de tempo: se o processo filho travar, o teste falha em vez de pendurar a suíte.
        with anyio.fail_after(30):
            async with Client(params) as client:
                names = sorted(t.name for t in (await client.list_tools()).tools)
                result = await client.call_tool("obter_dispositivo", {"id": "CF.art156-A.par1.incIX", "data_referencia": "2030-06-01"})
                return client.protocol_version, names, result

    version, names, result = anyio.run(main)

    assert version == "2026-07-28"  # a revisão stateless que o Claude Code também fala (passo 01)
    assert names == ["buscar_dispositivos", "obter_dispositivo"]
    assert result.is_error is False
    # data_referencia explícita: o `today` do processo filho não importa aqui.
    assert result.structured_content == tools.obter_dispositivo(ctx, "CF.art156-A.par1.incIX", "2030-06-01", today=date(2026, 11, 7))
    assert result.structured_content["versao"] == "EC132.art3"
```

- [ ] **Step 2: rode.** `uv run pytest tests/test_server_stdio.py -v` → 1 passed (o server já existe desde a Task 1; o teste prova o transporte de verdade e o `cwd` independente). Se falhar, a causa está no server ou no ambiente, não no teste: não mude o teste.

- [ ] **Step 3: registre o server.** Substitua `.mcp.json` inteiro por:

```json
{
  "mcpServers": {
    "eco": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--quiet", "python", "echo/echo_server.py"]
    },
    "taxlaw": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--quiet", "python", "-m", "taxlaw.server"]
    }
  }
}
```

Confira: `python3 -m json.tool .mcp.json` sem erro.

- [ ] **Step 4: nota do passo.** Crie `docs/steps/10-server.md`:

````markdown
# Passo 10: o server MCP via stdio

## O que mudou

- **Dependência nova:** `mcp>=2,<3`, o SDK oficial em Python. A versão travada no `uv.lock` é a 2.3.0.
- **`src/taxlaw/server.py`:** uma camada fina sobre `tools.py`.
  - `build_server(ctx, today)` monta um `TaxLawServer`, uma subclasse de `MCPServer`, com as duas ferramentas.
  - Ambas são marcadas como só leitura.
  - `main()` roda o server via stdio.
- **`.mcp.json`:** registra o server `taxlaw` ao lado do `eco`. O Claude Code expõe as ferramentas como `mcp__taxlaw__buscar_dispositivos` e `mcp__taxlaw__obter_dispositivo`.
- **Três coisas do SDK 2.3 que o código contorna** (medidas no protótipo em 2026-11-08):
  1. **O erro de validação repete o valor recebido.** O SDK valida os argumentos com o pydantic antes de chamar a ferramenta, e o erro traz `input_value=...`. Um CPF mandado no campo `limite` voltaria inteiro. Por isso `TaxLawServer.call_tool` varre todos os argumentos crus antes do SDK, incluindo chaves, valores aninhados e campos desconhecidos. Depois reescreve o erro de validação só com o nome do campo.
  2. **O que não está no tipo de retorno some em silêncio.** O SDK descarta do `structuredContent` toda chave que não está no `TypedDict`, mas o texto continua com ela. Por isso cada campo de `tools.py` está declarado, e um teste compara os dois.
  3. **O pydantic aceita `True` e `"5"` como inteiros.** `limite` e `incluir_filhos` são `strict`, para o server rejeitar o mesmo que `tools.py` rejeita.
- **Erros:** todo `isError` tem como texto só um JSON `{"erro", "mensagem"}`. O prefixo "Error executing tool" do SDK é removido.

## Como rodar

```
uv run pytest tests/test_server.py tests/test_server_stdio.py -v
```

No Claude Code, a primeira consulta real:

1. Rode `/mcp` e reconecte. O `taxlaw` deve aparecer com 2 ferramentas.
2. Pergunte: "Pela EC 132, o IBS integra a própria base de cálculo em 2030? Cite o dispositivo."
3. Confira se o modelo chamou `mcp__taxlaw__buscar_dispositivos` e depois `mcp__taxlaw__obter_dispositivo` com `data_referencia` 2030, e se a resposta cita `CF, art. 156-A, § 1º, IX` na redação do art. 3º da EC.

## O que observar

- **O mesmo resultado nos dois caminhos.** Chamar `tools.py` direto e chamar via MCP dá o mesmo resultado, no `structuredContent` e no texto. O teste de stdio sobe o processo de verdade, a partir de outro diretório, e fala a revisão `2026-07-28`.
- **O ponto único por onde todas as ações passam** (lição do P1). A guarda agora existe em duas camadas do server: em `call_tool`, antes do SDK, e em `tools.py`, para chamadas diretas. O hook do passo 11 será a terceira, no cliente.
- **"Não encontrei" volta com `isError: false`.** O modelo recebe a ausência como dado, e não como falha.

## Pergunta de previsão

Sem `/mcp` reconectado, o Claude Code ainda vê o server? E depois de reconectar: se você mudar o `dispositivos.json` e não reiniciar o server, a resposta muda? Pense em quando o `load_context()` roda.
````

- [ ] **Step 5: suíte inteira.** `uv run pytest -q` → 290 passed.

- [ ] **Step 6: commit.** `git add tests/test_server_stdio.py .mcp.json docs/steps/10-server.md && git commit -m "feat(step-10): server via stdio registrado no .mcp.json"`

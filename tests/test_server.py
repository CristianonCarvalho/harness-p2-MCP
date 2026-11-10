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


def test_descriptions_name_every_norm_in_the_corpus():
    # Se o corpus ganhar uma fonte, as descrições vistas pelo modelo precisam dizer.
    labels = {"ec132-2023": "EC 132/2023", "lc214-2025": "LC 214/2025"}
    assert set(CTX.corpus.fontes) == set(labels), "fonte nova no corpus: atualize as descrições e este teste"
    search = next(t for t in run(lambda c: c.list_tools()).tools if t.name == "buscar_dispositivos")
    for label in labels.values():
        assert label in search.description, label
        assert label in search.input_schema["properties"]["consulta"]["description"], label
    assert "Anexos" in search.description


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

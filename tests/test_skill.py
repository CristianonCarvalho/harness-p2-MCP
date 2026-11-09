"""Testes de forma da skill `consultar-reforma-tributaria` (passo 12, critério 3).

O comportamento do modelo com a skill é avaliado no P3, não aqui. Aqui só se
confere o que pode quebrar sem ninguém notar:
- o frontmatter que o Claude Code lê (nome, descrição com os gatilhos);
- o tamanho (spec: menos de 100 linhas);
- que toda ferramenta e todo campo citados existem no server de verdade;
- que os conselhos funcionam no corpus real (as expressões da tabela acham o
  dispositivo-âncora; o exemplo das três datas bate com as ferramentas);
- nenhum CPF/CNPJ escrito.
"""

import re
from datetime import date
from pathlib import Path

import anyio
import pytest
import yaml

from mcp.client import Client
from taxlaw import tools
from taxlaw.guard import find_taxpayer_ids
from taxlaw.server import build_server

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / ".claude" / "skills" / "consultar-reforma-tributaria"
TEXT = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
CTX = tools.load_context()
TODAY = date(2026, 11, 8)


def frontmatter() -> dict:
    # O Claude Code só lê o frontmatter se o "---" de abertura for a 1ª linha.
    assert TEXT.startswith("---\n")
    head, _, _ = TEXT[4:].partition("\n---\n")
    return yaml.safe_load(head)


def body() -> str:
    return TEXT[4:].partition("\n---\n")[2]


def server_tools():
    async def main():
        async with Client(build_server(CTX, today=TODAY)) as client:
            return (await client.list_tools()).tools

    return anyio.run(main)


def schema_properties(schema, found=None) -> set[str]:
    """Todos os nomes de propriedade de um JSON Schema, em qualquer profundidade."""
    found = set() if found is None else found
    if isinstance(schema, dict):
        found.update(schema.get("properties", {}))
        for value in schema.values():
            schema_properties(value, found)
    elif isinstance(schema, list):
        for item in schema:
            schema_properties(item, found)
    return found


def test_frontmatter_name_matches_directory_and_description_has_triggers():
    meta = frontmatter()
    assert meta["name"] == SKILL_DIR.name
    description = meta["description"]
    # A lista de skills trunca description em 1.536 caracteres; a nossa cabe com folga.
    assert 0 < len(description) <= 1024
    for trigger in ("reforma tributária", "EC 132", "LC 214", "IBS", "CBS", "Imposto Seletivo", "cesta básica", "redução de alíquota", "transição", "já está valendo"):
        assert trigger in description, trigger


def test_skill_is_short():
    assert len(TEXT.splitlines()) < 100


def test_no_taxpayer_id_written():
    assert find_taxpayer_ids(TEXT) == []


def test_every_tool_and_field_cited_exists_in_the_server():
    listed = server_tools()
    names = {t.name for t in listed}
    fields = set()
    for tool in listed:
        fields |= schema_properties(tool.input_schema) | schema_properties(tool.output_schema)
    # Tudo entre crases que começa em snake_case é ferramenta ou campo do
    # server, inclusive na forma `campo: valor` (ex.: `encontrado: false`).
    cited = set(re.findall(r"`([a-z_]+)(?::[^`]*)?`", body()))
    assert cited, "a skill deveria citar ferramentas e campos"
    assert cited <= names | fields, cited - (names | fields)
    assert {"buscar_dispositivos", "obter_dispositivo"} <= cited


@pytest.mark.parametrize(
    ("phrase", "anchor"),
    [
        ("imposto sobre bens e serviços", "CF.art156-A"),
        ("contribuição sobre bens e serviços", "CF.art195.incV"),
        ("bens e serviços prejudiciais à saúde ou ao meio ambiente", "CF.art153.incVIII"),
        ("Comitê Gestor do Imposto sobre Bens e Serviços", "CF.art156-B"),
        # LC 214 (passo 13c): o âncora é o artigo da LC.
        ("cesta básica nacional de alimentos", "LC214.art125"),
        ("reduzidas em 60% serviços de educação", "LC214.art128"),
        ("reduzidas em 30% profissionais", "LC214.art127"),
        ("alíquotas do imposto seletivo", "LC214.art422"),
    ],
)
def test_law_wording_table_finds_the_anchor(phrase, anchor):
    assert phrase in body()
    out = tools.buscar_dispositivos(CTX, phrase, "2030-06-01", today=TODAY)
    ids = [r["id"] for r in out["resultados"]]
    assert any(i == anchor or i.startswith(anchor + ".") for i in ids), ids


@pytest.mark.parametrize("abbreviation", ["IBS", "CBS"])
def test_abbreviations_alone_reach_only_the_lc_which_is_why_the_table_exists(abbreviation):
    # A EC e a CF não usam as siglas; a LC 214 (passo 13b) usa. A sigla sozinha
    # acha a LC, mas nunca o dispositivo da Constituição que institui o tributo.
    out = tools.buscar_dispositivos(CTX, abbreviation, "2030-06-01", limite=10, today=TODAY)
    assert out["resultados"] and all(r["id"].startswith("LC214.") for r in out["resultados"])


@pytest.mark.parametrize(
    ("when", "versao", "ec_article"),
    [("2025-06-01", "EC132.art1", "art. 1º"), ("2030-06-01", "EC132.art3", "art. 3º"), ("2040-01-01", "EC132.art4", "art. 4º")],
)
def test_example_matches_the_tools(when, versao, ec_article):
    row = next(line for line in body().splitlines() if line.startswith(f"| {when} |"))
    assert f"EC 132, {ec_article}" in row
    out = tools.obter_dispositivo(CTX, "CF.art156-A.par1.incIX", when, today=TODAY)
    assert out["versao"] == versao and out["efeitos"]["produz_efeitos_na_data"] is True
    assert "CF, art. 156-A, § 1º, IX" in body()

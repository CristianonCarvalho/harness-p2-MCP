"""Testes do structure no arquivo real da EC 132 (passo 05).

Leem `corpus/raw/ec132-2023.html` pelo caminho do próprio teste (funciona de
qualquer diretório) e conferem antes o sha256 com o meta: se o arquivo mudar,
estes números precisam ser revistos de propósito, não por acaso.

Os textos conferidos aqui foram comparados, em 2026-11-06, com a impressão em
PDF da mesma página feita pelo navegador (fonte independente do parser).
"""

from collections import Counter, defaultdict
from pathlib import Path

import pytest

from taxlaw.ingest.fetch import SOURCE_NAME, verify
from taxlaw.ingest.structure import decode_html, parse

RAW_DIR = Path(__file__).resolve().parents[1] / "corpus" / "raw"

MULTI_VERSION = {
    "ADCT.art104.incIV",
    "CF.art146.incIII.alid",
    "CF.art153.par6.incIV",
    "CF.art156-A.par1.incIX",
    "CF.art159.par3",
    "CF.art195.par17",
    "CF.art195.par19",
    "CF.art212-A.incII.alic",
    "CF.art225.par1.incVIII",
}

# (id, versao) → (alteracao, início do texto), conferidos no PDF da página.
KNOWN = {
    ("CF.art156-A", "EC132.art1"): ("incluido", "Art. 156-A. Lei complementar instituirá imposto sobre bens e serviços de competência compartilhada"),
    ("CF.art149-A", "EC132.art1"): ("alterado", "Art. 149-A. Os Municípios e o Distrito Federal poderão instituir contribuição"),
    ("ADCT.art125", "EC132.art2"): ("incluido", "Art. 125. Em 2026, o imposto previsto no art. 156-A será cobrado à alíquota estadual de 0,1%"),
    ("EC132.art12", "EC132.art12"): ("original", "Art. 12.Fica instituído o Fundo de Compensação de Benefícios Fiscais ou Financeiro-Fiscais"),
    ("EC132.art23.incI", "EC132.art23"): ("original", "I - em 2027, em relação aos arts. 3º e 11;"),
    ("CF.art195.par17", "EC132.art3"): ("alterado", "§ 17. A contribuição prevista no inciso V do caput não integrará sua própria base de cálculo"),
}


@pytest.fixture(scope="module")
def result():
    assert verify(RAW_DIR, SOURCE_NAME), "corpus/raw/ec132-2023.html não bate com o sha256 do meta"
    return parse(decode_html((RAW_DIR / f"{SOURCE_NAME}.html").read_bytes()))


def test_no_errors_and_no_warnings(result):
    assert result.errors == []
    assert result.warnings == []


def test_all_23_ec_articles_are_present(result):
    articles = {r.id for r in result.records if r.norma == "EC132" and r.pai is None}
    assert articles == {f"EC132.art{n}" for n in range(1, 24)}


def test_totals(result):
    # Âncoras de regressão: mudaram? Entenda o porquê antes de atualizar.
    assert len(result.records) == 487
    assert Counter(r.alteracao for r in result.records) == {"incluido": 236, "original": 159, "alterado": 92}
    assert Counter(r.norma for r in result.records) == {"CF": 196, "EC132": 159, "ADCT": 132}


def test_children_of_art12_are_not_glued_to_art11(result):
    # Antes da correção do passo 05, os 22 filhos do art. 12 iam para o art. 11.
    per_version = Counter(r.versao for r in result.records)
    assert per_version["EC132.art11"] == 1
    assert per_version["EC132.art12"] == 23
    assert per_version["EC132.art17"] == 1


def test_dispositivos_with_more_than_one_version(result):
    versions = defaultdict(list)
    for r in result.records:
        versions[r.id].append(r.versao)
    assert {rid for rid, vs in versions.items() if len(vs) > 1} == MULTI_VERSION


def test_versions_of_art156a_par1_inc_ix(result):
    records = [r for r in result.records if r.id == "CF.art156-A.par1.incIX"]
    assert [(r.versao, r.alteracao) for r in records] == [
        ("EC132.art1", "incluido"),
        ("EC132.art3", "alterado"),
        ("EC132.art4", "alterado"),
    ]
    original, from_2027, from_2033 = (r.texto for r in records)
    assert "Programa de Integração Social" in original
    assert "Programa de Integração Social" not in from_2027
    # A própria EC republica o mesmo texto no art. 4º: muda só a data de efeito.
    assert from_2033 == from_2027


def test_known_texts(result):
    index = {(r.id, r.versao): r for r in result.records}
    for key, (alteracao, start) in KNOWN.items():
        assert index[key].alteracao == alteracao, key
        assert index[key].texto.startswith(start), key


def test_pai_is_id_without_last_segment(result):
    for r in result.records:
        norma, path = r.id.split(".", 1)
        expected = r.id.rsplit(".", 1)[0] if "." in path else None
        assert r.pai == expected, r.id


def test_no_leftover_marks_in_texts(result):
    for r in result.records:
        assert "(NR)" not in r.texto, r.id
        assert not r.texto.startswith('"'), r.id
        assert not r.texto.endswith("Vigência"), r.id
        assert set(r.texto) - set(". "), r.id


def test_parse_is_deterministic(result):
    again = parse(decode_html((RAW_DIR / f"{SOURCE_NAME}.html").read_bytes()))
    assert again == result

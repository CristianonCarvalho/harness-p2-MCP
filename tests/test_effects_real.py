"""Testes do effects no corpus real da EC 132 (passo 06).

Datas conferidas à mão contra o texto literal dos arts. 22 e 23 da EC
(spec, seção 3). O arquivo é conferido pelo sha256 antes de tudo.
"""

from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from taxlaw.ingest.effects import effects_for, find_publication_date
from taxlaw.ingest.fetch import SOURCE_NAME, verify
from taxlaw.ingest.structure import decode_html, paragraphs, parse

RAW_DIR = Path(__file__).resolve().parents[1] / "corpus" / "raw"
PUB = date(2023, 12, 21)

REVOKED = [
    ("CF.art195.incI.alib", 2027), ("CF.art195.incIV", 2027), ("CF.art195.par12", 2027),
    ("CF.art155.incII", 2033), ("CF.art155.par2", 2033), ("CF.art155.par3", 2033), ("CF.art155.par4", 2033),
    ("CF.art155.par5", 2033), ("CF.art156.incIII", 2033), ("CF.art156.par3", 2033), ("CF.art158.incIV.alia", 2033),
    ("CF.art158.par1", 2033), ("CF.art161.incI", 2033), ("ADCT.art80.incII", 2033), ("ADCT.art82.par2", 2033),
    ("ADCT.art83", 2033),
]


@pytest.fixture(scope="module")
def corpus():
    assert verify(RAW_DIR, SOURCE_NAME), "corpus/raw/ec132-2023.html não bate com o sha256 do meta"
    html = decode_html((RAW_DIR / f"{SOURCE_NAME}.html").read_bytes())
    records = parse(html).records
    publication = find_publication_date(text for _, text in paragraphs(html))
    return records, publication, effects_for(records, publication)


def dates(result, rid, versao):
    e = result.by_version[(rid, versao)]
    return e.efeitos_desde, e.efeitos_ate


def test_publication_date_and_no_warnings(corpus):
    _, publication, result = corpus
    assert publication == PUB
    assert result.warnings == []


def test_rules_per_ec_article(corpus):
    _, _, result = corpus
    special = {3: (2027, "I"), 11: (2027, "I"), 4: (2033, "II"), 5: (2033, "II")}
    for number, rule in result.rules.items():
        year, inciso = special.get(number, (None, "III"))
        assert rule.desde == (date(year, 1, 1) if year else PUB), number
        assert rule.fundamento == f"EC 132/2023, art. 23, {inciso}", number
    assert sorted(result.rules) == list(range(1, 24))


def test_every_version_has_dates_and_vigor_equals_efeitos(corpus):
    records, _, result = corpus
    assert len(result.by_version) == len(records) == 487
    assert Counter(e.metodo for e in result.by_version.values()) == {"automatico": 487}
    for e in result.by_version.values():
        assert e.vigor_desde == e.efeitos_desde
        assert e.efeitos_ate is None or e.efeitos_ate >= e.efeitos_desde


def test_versions_of_art156a_par1_inc_ix(corpus):
    _, _, result = corpus
    rid = "CF.art156-A.par1.incIX"
    assert dates(result, rid, "EC132.art1") == (PUB, date(2026, 12, 31))
    assert dates(result, rid, "EC132.art3") == (date(2027, 1, 1), date(2032, 12, 31))
    assert dates(result, rid, "EC132.art4") == (date(2033, 1, 1), None)


def test_versions_in_adct_and_two_version_case(corpus):
    _, _, result = corpus
    assert dates(result, "ADCT.art104.incIV", "EC132.art2") == (PUB, date(2032, 12, 31))
    assert dates(result, "ADCT.art104.incIV", "EC132.art5") == (date(2033, 1, 1), None)
    assert dates(result, "CF.art195.par19", "EC132.art1") == (PUB, date(2026, 12, 31))
    assert dates(result, "CF.art195.par19", "EC132.art3") == (date(2027, 1, 1), None)


def test_revocations_of_article_22(corpus):
    _, _, result = corpus
    assert [(r.id, r.desde.year) for r in result.revocations] == REVOKED


def test_revoked_dispositivos_in_corpus_end_in_2032(corpus):
    _, _, result = corpus
    for rid in ("CF.art155.par3", "CF.art158.incIV.alia", "CF.art158.par1", "CF.art161.incI"):
        e = result.by_version[(rid, "EC132.art1")]
        assert (e.efeitos_ate, e.fundamento_ate) == (date(2032, 12, 31), "EC 132/2023, art. 22, II, a"), rid


def test_only_the_revoked_alinea_ends(corpus):
    _, _, result = corpus
    # "158, IV, \"a\"": revoga a alínea a; o inciso IV e a alínea b seguem.
    assert dates(result, "CF.art158.incIV", "EC132.art1") == (PUB, None)
    assert dates(result, "CF.art158.incIV.alib", "EC132.art1") == (PUB, None)


def test_republished_as_revogado_is_untouched(corpus):
    records, _, result = corpus
    text = next(r.texto for r in records if r.id == "ADCT.art82.par2" and r.versao == "EC132.art5")
    assert text == "§ 2º (Revogado)."
    e = result.by_version[("ADCT.art82.par2", "EC132.art5")]
    assert (e.efeitos_desde, e.efeitos_ate, e.fundamento_ate) == (date(2033, 1, 1), None, None)

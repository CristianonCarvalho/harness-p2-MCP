"""Testes dos efeitos da LC pelo art. 544 (passo 13b), com textos sintéticos e com o HTML real.

Os sintéticos imitam a redação do art. 544 da LC 214 (spec do passo 13,
seção 2); os registros são inventados. O real confere as regras extraídas do
`corpus/raw/lc214-2025.html` (só leitura).
"""

from datetime import date
from pathlib import Path

import pytest

from taxlaw.ingest.lc_effects import (
    find_lc_publication_date,
    lc_effects_for,
    parse_544,
    parse_article_list,
)
from taxlaw.ingest.lc_structure import lc_paragraphs
from taxlaw.ingest.structure import Record, decode_html

NOTE = "Este texto não substitui o publicado no DOU de 16.1.2025 - Edição extra e republicado no DOU de 23.1.2025"
ART_544 = [
    "Art. 544. Esta Lei Complementar entra em vigor na data de sua publicação, produzindo efeitos:",
    "I - a partir do primeiro dia do quarto mês subsequente ao da sua publicação, em relação aos arts. 537 a 540;",
    "II - a partir de 1º de janeiro de 2025, em relação aos arts. 35, 58, caput, 60, § 3º, 62 e 541;",
    "III - a partir de 1º de janeiro de 2027, em relação aos arts. 168 a 171, 450, exceto os §§ 1º e 5º, e 542; (Redação dada pela Lei Complementar nº 227, de 2026)",
    "IV - a partir de 1º de janeiro de 2029, em relação aos arts. 446, 450, §§ 1º e 5º, e 474;",
    "V - a partir de 1º de janeiro de 2033, em relação aos arts. 518 e 543; e",
    "VI - a partir de 1º de janeiro de 2026, em relação aos demais dispositivos.",
    "Brasília, 16 de janeiro de 2025; 204o da Independência e 137o da República.",
]
TEXTS = ["Art. 543. Ficam revogados ...", *ART_544, NOTE, "Este texto não substitui o publicado no DOU de 2.7.2025."]


def rec(rid: str, alteracao: str = "original", origem: str = "LC 214/2025") -> Record:
    return Record(id=rid, citacao=rid, norma="LC214", pai=None, versao="LC214", origem=origem, alteracao=alteracao, texto="t")


def effects(records, texts=TEXTS):
    return lc_effects_for(records, texts).by_version


# ------------------------------------------------------------------ peças


def test_publication_is_the_first_dou_note():
    assert find_lc_publication_date(TEXTS) == date(2025, 1, 16)
    assert find_lc_publication_date(["nada aqui"]) is None


def test_article_list_ranges_and_qualifications():
    articles, qualified = parse_article_list("aos arts. 35, 58, caput, 60, § 3º, 62, 480 a 482 e 541")
    assert articles == ["35", "58", "60", "62", "480", "481", "482", "541"]
    assert qualified == {"58", "60"}


def test_paragraph_numbers_with_ordinal_are_not_articles():
    articles, qualified = parse_article_list("aos arts. 446, 450, §§ 1º e 5º, e 474")
    assert articles == ["446", "450", "474"] and qualified == {"450"}
    assert parse_article_list("aos arts. 450, exceto os §§ 1º e 5º, 461") == (["450", "461"], {"450"})


def test_article_with_letter_and_unknown_text():
    assert parse_article_list("ao art. 76-A") == (["76-A"], set())
    assert parse_article_list("aos arts. 10 e seguintes") is None


# ------------------------------------------------------------------ art. 544


def test_rules_dates_and_default():
    result = parse_544(TEXTS, date(2025, 1, 16))
    assert result.warnings == []
    assert result.rules["537"].desde == date(2025, 5, 1) and result.rules["537"].inciso == "I"  # quarto mês subsequente
    assert result.rules["35"].desde == date(2025, 1, 1)
    assert result.rules["169"].desde == date(2027, 1, 1)  # marca "(Redação dada ...)" tirada antes de ler
    assert result.default.desde == date(2026, 1, 1) and result.default.inciso == "VI"
    # 450 aparece com ressalva em dois incisos; 58 e 60 com ressalva no II.
    assert result.qualified == {"58", "60", "450"}


def test_relative_date_crosses_the_year():
    result = parse_544(TEXTS, date(2025, 11, 3))
    assert result.rules["537"].desde == date(2026, 3, 1)


def test_unrecognized_inciso_blocks_the_default():
    texts = TEXTS[:3] + ["II - a partir da data fixada em regulamento, em relação aos arts. 35;"] + TEXTS[4:]
    result = parse_544(texts, date(2025, 1, 16))
    assert result.default is None
    assert len(result.warnings) == 1 and "regra dos demais bloqueada" in result.warnings[0]


def test_missing_article_544_or_publication_is_a_warning():
    assert parse_544(["Art. 1. Nada."], date(2025, 1, 16)).warnings == ["art. 544 não encontrado: efeitos da LC indeterminados"]
    assert "data de publicação" in parse_544(ART_544, None).warnings[0]


# ------------------------------------------------------------------ registros


def test_default_rule_gives_vigor_publication_and_effects_2026():
    e = effects([rec("LC214.art128.incI")])[("LC214.art128.incI", "LC214")]
    assert (e.vigor_desde, e.efeitos_desde, e.efeitos_ate) == (date(2025, 1, 16), date(2026, 1, 1), None)
    assert (e.fundamento, e.metodo) == ("LC 214/2025, art. 544, VI", "automatico")


def test_listed_article_uses_its_inciso():
    e = effects([rec("LC214.art170.par1")])[("LC214.art170.par1", "LC214")]
    assert (e.efeitos_desde, e.fundamento) == (date(2027, 1, 1), "LC 214/2025, art. 544, III")


def test_qualified_article_is_indeterminate_but_keeps_vigor():
    e = effects([rec("LC214.art450.par2")])[("LC214.art450.par2", "LC214")]
    assert (e.metodo, e.vigor_desde, e.efeitos_desde, e.fundamento) == ("indeterminado", date(2025, 1, 16), None, None)


@pytest.mark.parametrize(
    ("alteracao", "origem"),
    [
        ("alterado", "LC 214/2025, com redação dada pela LC 227/2026"),
        ("incluido", "LC 214/2025, incluído pela LC 227/2026"),
        ("original", "LC 214/2025, parte promulgada após veto"),
    ],
)
def test_amended_or_promulgated_is_fully_indeterminate(alteracao, origem):
    e = effects([rec("LC214.art128.incII", alteracao, origem)])[("LC214.art128.incII", "LC214")]
    assert (e.metodo, e.vigor_desde, e.efeitos_desde, e.efeitos_ate, e.fundamento) == ("indeterminado", None, None, None, None)


def test_blocked_default_makes_unlisted_articles_indeterminate():
    texts = TEXTS[:3] + ["II - a partir da data fixada em regulamento, em relação aos arts. 35;"] + TEXTS[4:]
    by_version = effects([rec("LC214.art128"), rec("LC214.art170")], texts)
    assert by_version[("LC214.art128", "LC214")].metodo == "indeterminado"
    assert by_version[("LC214.art170", "LC214")].efeitos_desde == date(2027, 1, 1)  # regra própria continua


# ------------------------------------------------------------------ HTML real


def test_real_article_544():
    raw = Path(__file__).resolve().parents[1] / "corpus" / "raw" / "lc214-2025.html"
    texts = [p.text for p in lc_paragraphs(decode_html(raw.read_bytes())) if not p.struck and p.text]
    result = parse_544(texts, find_lc_publication_date(texts))
    assert result.publication == date(2025, 1, 16) and result.warnings == []
    assert result.default.desde == date(2026, 1, 1) and result.default.inciso == "VI"
    assert result.rules["537"].desde == date(2025, 5, 1)
    assert result.qualified == {"58", "60", "450"}
    assert len(result.rules) == 74
    # Nenhum artigo do escopo do passo 13 nos incisos I a V.
    assert not {str(n) for n in [*range(125, 143), *range(419, 424)]} & set(result.rules)


def test_article_in_two_incisos_has_no_single_rule():
    texts = [
        "Art. 544. Esta Lei Complementar entra em vigor na data de sua publicação, produzindo efeitos:",
        "I - a partir de 1º de janeiro de 2025, em relação aos arts. 10 e 20;",
        "II - a partir de 1º de janeiro de 2027, em relação aos arts. 20 e 30;",
        "III - a partir de 1º de janeiro de 2026, em relação aos demais dispositivos.",
        NOTE,
    ]
    result = parse_544(texts, date(2025, 1, 16))
    assert result.qualified == {"20"}
    assert effects([rec("LC214.art20")], texts)[("LC214.art20", "LC214")].metodo == "indeterminado"

"""Testes do effects (passo 06) com registros sintéticos.

Os registros são montados à mão (sem HTML): o effects só depende de
`Record`. Textos do art. 23 e do art. 22 seguem o formato real; os demais
são inventados.
"""

from datetime import date

import pytest

from taxlaw.ingest.effects import (
    ArticleRule,
    Revocation,
    compute_effects,
    effects_for,
    find_publication_date,
    parse_revocation_list,
    parse_revocations,
    parse_vigencia,
)
from taxlaw.ingest.structure import Record

PUB = date(2023, 12, 21)


def rec(rid: str, art: int, texto: str = "texto sintético", alteracao: str = "alterado") -> Record:
    """Registro mínimo: o effects só usa id, versao e texto (pai fica None)."""
    norma = rid.split(".", 1)[0]
    return Record(rid, rid, norma, None, f"EC132.art{art}", f"EC 132/2023, art. {art}", alteracao, texto)


def art23(*incisos: str) -> list[Record]:
    out = [rec("EC132.art23", 23, "Art. 23. Esta Emenda Constitucional entra em vigor:", "original")]
    for texto in incisos:
        roman = texto.split(" - ", 1)[0]
        out.append(rec(f"EC132.art23.inc{roman}", 23, texto, "original"))
    return out


REAL_ART23 = art23(
    "I - em 2027, em relação aos arts. 3º e 11;",
    "II - em 2033, em relação aos arts. 4º e 5º; e",
    "III - na data de sua publicação, em relação aos demais dispositivos.",
)
OTHER_ARTICLES = [rec(f"EC132.art{n}", n, alteracao="original") for n in (1, 3, 4, 5, 11)]


def test_find_publication_date():
    assert find_publication_date(["x", "Este texto não substitui o publicado no DOU 21.12.2023"]) == PUB
    assert find_publication_date(["sem data"]) is None


def test_vigencia_rules_from_real_format():
    rules, warnings = parse_vigencia(REAL_ART23 + OTHER_ARTICLES, PUB)
    assert warnings == []
    assert rules[3] == rules[11] == ArticleRule(date(2027, 1, 1), "EC 132/2023, art. 23, I", "automatico")
    assert rules[4] == rules[5] == ArticleRule(date(2033, 1, 1), "EC 132/2023, art. 23, II", "automatico")
    assert rules[1] == rules[23] == ArticleRule(PUB, "EC 132/2023, art. 23, III", "automatico")


def test_singular_article_is_accepted():
    rules, warnings = parse_vigencia(art23("I - em 2030, em relação ao art. 3º;") + OTHER_ARTICLES, PUB)
    assert warnings == []
    assert rules[3].desde == date(2030, 1, 1)


def test_unrecognized_inciso_blocks_the_default_rule():
    records = art23(
        "I - em data a ser fixada em lei, em relação ao art. 3º;",
        "II - na data de sua publicação, em relação aos demais dispositivos.",
    ) + OTHER_ARTICLES
    rules, warnings = parse_vigencia(records, PUB)
    assert {n: r.metodo for n, r in rules.items()} == {n: "indeterminado" for n in (1, 3, 4, 5, 11, 23)}
    assert warnings == [
        "inciso do art. 23 não reconhecido: I - em data a ser fixada em lei, em relação ao art. 3º;",
        "regra dos demais dispositivos não aplicada: há inciso do art. 23 não reconhecido",
    ]


def test_article_in_two_incisos_is_indeterminate():
    records = art23(
        "I - em 2027, em relação ao art. 3º;",
        "II - em 2033, em relação aos arts. 3º e 4º; e",
        "III - na data de sua publicação, em relação aos demais dispositivos.",
    ) + OTHER_ARTICLES
    rules, warnings = parse_vigencia(records, PUB)
    assert rules[3].metodo == "indeterminado" and rules[3].desde is None
    assert rules[4].desde == date(2033, 1, 1)
    assert warnings == ["art. 3 da EC citado em mais de um inciso do art. 23"]


def test_missing_publication_date_leaves_default_indeterminate():
    rules, warnings = parse_vigencia(REAL_ART23 + OTHER_ARTICLES, None)
    assert rules[1].metodo == "indeterminado"
    assert rules[3].desde == date(2027, 1, 1)
    assert warnings == ["art. 23, III: data de publicação não encontrada"]


def test_no_article_23_means_everything_indeterminate():
    rules, warnings = parse_vigencia(OTHER_ARTICLES, PUB)
    assert all(r.metodo == "indeterminado" for r in rules.values())
    assert warnings == ["art. 23 da EC sem incisos: nenhuma data de vigor reconhecida"]


RULES = {
    1: ArticleRule(PUB, "EC 132/2023, art. 23, III", "automatico"),
    3: ArticleRule(date(2027, 1, 1), "EC 132/2023, art. 23, I", "automatico"),
    4: ArticleRule(date(2033, 1, 1), "EC 132/2023, art. 23, II", "automatico"),
    7: ArticleRule(None, None, "indeterminado"),
}


def test_single_version_has_no_end_and_vigor_equals_efeitos():
    effects, warnings = compute_effects([rec("CF.art10", 1)], RULES)
    e = effects[("CF.art10", "EC132.art1")]
    assert (e.vigor_desde, e.efeitos_desde, e.efeitos_ate, e.metodo) == (PUB, PUB, None, "automatico")
    assert warnings == []


def test_versions_are_chained_by_the_next_start():
    records = [rec("CF.art10.incIX", 4), rec("CF.art10.incIX", 1), rec("CF.art10.incIX", 3)]
    effects, _ = compute_effects(records, RULES)
    assert [(effects[("CF.art10.incIX", f"EC132.art{n}")].efeitos_desde, effects[("CF.art10.incIX", f"EC132.art{n}")].efeitos_ate) for n in (1, 3, 4)] == [
        (PUB, date(2026, 12, 31)),
        (date(2027, 1, 1), date(2032, 12, 31)),
        (date(2033, 1, 1), None),
    ]


def test_next_version_without_date_leaves_end_unknown():
    effects, _ = compute_effects([rec("CF.art10", 1), rec("CF.art10", 7)], RULES)
    assert effects[("CF.art10", "EC132.art1")].efeitos_ate is None
    later = effects[("CF.art10", "EC132.art7")]
    assert (later.efeitos_desde, later.metodo) == (None, "indeterminado")


def test_versions_out_of_order_warn_and_keep_end_unknown():
    rules = {1: ArticleRule(date(2030, 1, 1), "f1", "automatico"), 3: ArticleRule(date(2027, 1, 1), "f3", "automatico")}
    effects, warnings = compute_effects([rec("CF.art10", 1), rec("CF.art10", 3)], rules)
    assert effects[("CF.art10", "EC132.art1")].efeitos_ate is None
    assert warnings == ["versões de CF.art10 com início fora de ordem: EC132.art1 e EC132.art3"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('o art. 195, I, "b", e IV, e § 12, da Constituição Federal', ["CF.art195.incI.alib", "CF.art195.incIV", "CF.art195.par12"]),
        (
            'os arts. 155, II, e §§ 2º a 5º, 156, III, e § 3º, 158, IV, "a", e § 1º, e 161, I, da Constituição Federal',
            ["CF.art155.incII", "CF.art155.par2", "CF.art155.par3", "CF.art155.par4", "CF.art155.par5",
             "CF.art156.incIII", "CF.art156.par3", "CF.art158.incIV.alia", "CF.art158.par1", "CF.art161.incI"],
        ),
        ("os arts. 80, II, 82, § 2º, e 83 do Ato das Disposições Constitucionais Transitórias", ["ADCT.art80.incII", "ADCT.art82.par2", "ADCT.art83"]),
    ],
)
def test_revocation_lists_in_real_format(text, expected):
    assert parse_revocation_list(text) == expected


@pytest.mark.parametrize("text", ["os arts. 10 e 11 da Lei sintética", 'o "a" do art. 10 da Constituição Federal'])
def test_revocation_list_not_understood_returns_none(text):
    assert parse_revocation_list(text) is None


ART22 = [
    rec("EC132.art22", 22, "Art. 22. Revogam-se:", "original"),
    rec("EC132.art22.incI", 22, 'I - em 2027, o art. 10, I, "b", da Constituição Federal;', "original"),
    rec("EC132.art22.incII", 22, "II - em 2033:", "original"),
    rec("EC132.art22.incII.alia", 22, "a) os arts. 20, § 1º, da Constituição Federal; e", "original"),
]


def test_parse_revocations_with_incisos_and_alineas():
    revocations, warnings = parse_revocations(ART22)
    assert warnings == []
    assert revocations == [
        Revocation("CF.art10.incI.alib", date(2027, 1, 1), "EC 132/2023, art. 22, I"),
        Revocation("CF.art20.par1", date(2033, 1, 1), "EC 132/2023, art. 22, II, a"),
    ]


def test_unrecognized_revocation_is_a_warning():
    records = [rec("EC132.art22", 22, "Art. 22. Revogam-se:", "original"),
               rec("EC132.art22.incI", 22, "I - quando a lei dispuser, o art. 10 da Constituição Federal;", "original")]
    revocations, warnings = parse_revocations(records)
    assert revocations == []
    assert warnings == ["inciso do art. 22 não reconhecido: I - quando a lei dispuser, o art. 10 da Constituição Federal;"]


REVOCATIONS = [Revocation("CF.art20.par1", date(2033, 1, 1), "EC 132/2023, art. 22, II, a"),
               Revocation("CF.art30.incIV", date(2027, 1, 1), "EC 132/2023, art. 22, I")]


def test_revocation_ends_earlier_versions_and_children():
    records = [rec("CF.art20.par1", 1), rec("CF.art30.incIV.alia", 1), rec("CF.art30.incIV2", 1)]
    effects, warnings = compute_effects(records, RULES, REVOCATIONS)
    assert warnings == []
    ended = effects[("CF.art20.par1", "EC132.art1")]
    assert (ended.efeitos_ate, ended.fundamento_ate) == (date(2032, 12, 31), "EC 132/2023, art. 22, II, a")
    child = effects[("CF.art30.incIV.alia", "EC132.art1")]
    assert (child.efeitos_ate, child.fundamento_ate) == (date(2026, 12, 31), "EC 132/2023, art. 22, I")
    # "incIV2" não é filho de "incIV": a comparação é por segmento, não por prefixo de texto.
    assert effects[("CF.art30.incIV2", "EC132.art1")].efeitos_ate is None


def test_revocation_keeps_an_earlier_natural_end():
    records = [rec("CF.art20.par1", 1), rec("CF.art20.par1", 3)]
    effects, _ = compute_effects(records, RULES, REVOCATIONS)
    first = effects[("CF.art20.par1", "EC132.art1")]
    assert (first.efeitos_ate, first.fundamento_ate) == (date(2026, 12, 31), None)
    second = effects[("CF.art20.par1", "EC132.art3")]
    assert (second.efeitos_ate, second.fundamento_ate) == (date(2032, 12, 31), "EC 132/2023, art. 22, II, a")


def test_version_starting_at_revocation_is_untouched_when_it_says_revogado():
    effects, warnings = compute_effects([rec("CF.art20.par1", 4, "§ 1º (Revogado).")], RULES, REVOCATIONS)
    e = effects[("CF.art20.par1", "EC132.art4")]
    assert (e.efeitos_desde, e.efeitos_ate, e.fundamento_ate) == (date(2033, 1, 1), None, None)
    assert warnings == []


def test_version_starting_after_revocation_without_revogado_warns():
    _, warnings = compute_effects([rec("CF.art20.par1", 4, "§ 1º Texto sintético novo.")], RULES, REVOCATIONS)
    assert warnings == ["CF.art20.par1 (EC132.art4) começa depois de revogado por EC 132/2023, art. 22, II, a"]


def test_effects_for_puts_it_all_together():
    records = REAL_ART23 + OTHER_ARTICLES + ART22 + [rec("CF.art10.incI.alib", 1)]
    result = effects_for(records, PUB)
    assert result.warnings == []
    assert result.rules[3].desde == date(2027, 1, 1)
    assert result.by_version[("CF.art10.incI.alib", "EC132.art1")].efeitos_ate == date(2026, 12, 31)

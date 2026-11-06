# P2, passo 06: effects (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-06-p2-passo-06-effects.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um módulo puro `taxlaw.ingest.effects` que lê os arts. 23 (vigência por artigo da EC) e 22 (revogações) e dá a cada versão de dispositivo suas datas de vigor e efeitos, com fundamento, sem nunca inventar data.

**Architecture:** Quatro funções sobre `list[Record]` (do `structure`): `find_publication_date` (nota do DOU), `parse_vigencia` (art. 23 → regra por artigo da EC), `parse_revocations` (art. 22 → lista de `Revocation`) e `compute_effects` (início pela regra do artigo da versão; término pela versão seguinte ou pela revogação, o que vier antes). `effects_for` junta tudo para o build. O que não é reconhecido vira `indeterminado` com aviso.

**Tech Stack:** Python 3.13 (biblioteca padrão: `re`, `datetime`, `dataclasses`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seções 3 e 5, atualizadas em 2026-11-06: vigor = efeitos na EC 132, revogações do art. 22, `fundamento_ate`)

## Global Constraints

- Só biblioteca padrão; nenhuma dependência nova no `pyproject.toml`.
- `effects.py` é puro: não lê arquivo, não acessa rede, não usa relógio (`date.today()` proibido). Recebe registros e a data de publicação.
- Data de término nunca é inventada; ano sem dia vira 1º de janeiro (regra escrita no código); o que não é reconhecido fica `metodo: "indeterminado"` com aviso, nunca cai em silêncio na regra dos "demais dispositivos".
- Testes 100% offline e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes. Não alterar `corpus/`.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `pyproject.toml`, `corpus/`, nem os módulos existentes (`guard.py`, `synthetic_ids.py`, `ingest/__init__.py`, `ingest/fetch.py`, `ingest/structure.py`).
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (texto literal conferido em 2026-11-06 no corpus)

- Art. 23: "Esta Emenda Constitucional entra em vigor: I - em 2027, em relação aos arts. 3º e 11; II - em 2033, em relação aos arts. 4º e 5º; e III - na data de sua publicação, em relação aos demais dispositivos."
- Publicação: "Este texto não substitui o publicado no DOU 21.12.2023" (último parágrafo da página).
- Art. 22: "Revogam-se: I - em 2027, o art. 195, I, \"b\", e IV, e § 12, da Constituição Federal; II - em 2033: a) os arts. 155, II, e §§ 2º a 5º, 156, III, e § 3º, 158, IV, \"a\", e § 1º, e 161, I, da Constituição Federal; e b) os arts. 80, II, 82, § 2º, e 83 do Ato das Disposições Constitucionais Transitórias."
- No corpus, os revogados com registro são: CF art. 155, § 3º; art. 158, IV, "a"; art. 158, § 1º; art. 161, I (versão do art. 1º, efeitos desde 2023) e ADCT art. 82, § 2º (versão do art. 5º, texto "§ 2º (Revogado).", desde 2033).
- Resultado esperado no corpus: 0 avisos, 487 versões `automatico`, 16 revogações.

## Review Focus

- Uma lista de revogação com contexto ("158, IV, \"a\"") revoga só a peça final; o inciso IV e a alínea b seguem (testes `test_revocation_lists_in_real_format` e `test_only_the_revoked_alinea_ends`).
- A comparação de ancestral é por segmento: `CF.art30.incIV` não revoga `CF.art30.incIV2` (teste `test_revocation_ends_earlier_versions_and_children`).
- Inciso do art. 23 não reconhecido bloqueia a regra dos demais; artigo em dois incisos fica indeterminado; sem data de publicação, os demais ficam indeterminados (testes `test_unrecognized_inciso_blocks_the_default_rule`, `test_article_in_two_incisos_is_indeterminate`, `test_missing_publication_date_leaves_default_indeterminate`).
- A versão "(Revogado)" que começa na data da revogação não é encerrada; uma versão sem "Revogado" que começa depois da revogação gera aviso (testes `test_version_starting_at_revocation_is_untouched_when_it_says_revogado` e `test_version_starting_after_revocation_without_revogado_warns`).
- Nenhuma versão termina antes de começar (`test_every_version_has_dates_and_vigor_equals_efeitos`).

---

### Task 1: Módulo effects e nota do passo

**Files:**
- Create: `src/taxlaw/ingest/effects.py`
- Test: `tests/test_effects.py`
- Test: `tests/test_effects_real.py`
- Create: `docs/steps/06-effects.md`

**Interfaces:**
- Consumes: `Record` de `taxlaw.ingest.structure` (campos `id`, `versao` = `"EC132.artN"`, `texto`); `decode_html`, `paragraphs`, `parse` (só nos testes reais); `SOURCE_NAME`, `verify` de `taxlaw.ingest.fetch` (só nos testes reais).
- Produces (usados pelo build no passo 07): `ArticleRule(desde: date | None, fundamento: str | None, metodo: str)`; `Effects(vigor_desde, efeitos_desde, efeitos_ate: date | None, fundamento: str | None, metodo: str, fundamento_ate: str | None = None)`; `Revocation(id: str, desde: date, fundamento: str)`; `EffectsResult(rules: dict[int, ArticleRule], revocations: list[Revocation], by_version: dict[tuple[str, str], Effects], warnings: list[str])`; `find_publication_date(texts) -> date | None`; `parse_vigencia(records, publication) -> tuple[dict[int, ArticleRule], list[str]]`; `parse_revocation_list(text) -> list[str] | None`; `parse_revocations(records) -> tuple[list[Revocation], list[str]]`; `compute_effects(records, rules, revocations=None) -> tuple[dict, list[str]]`; `effects_for(records, publication) -> EffectsResult`.

- [ ] **Step 1: testes que falham.** Crie `tests/test_effects.py`:

```python
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
```

E `tests/test_effects_real.py`:

```python
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
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_effects.py tests/test_effects_real.py -v` → erro de import (`taxlaw.ingest.effects` não existe).

- [ ] **Step 3: implemente.** Crie `src/taxlaw/ingest/effects.py`:

```python
"""Art. 23 da EC 132 → datas de vigor e efeitos de cada versão (puro).

O art. 23 escalona a própria entrada em vigor por artigo da emenda (spec,
seção 3, decisão de 2026-11-06):

    I - em 2027, em relação aos arts. 3º e 11;
    II - em 2033, em relação aos arts. 4º e 5º; e
    III - na data de sua publicação, em relação aos demais dispositivos.

Cada versão de um dispositivo herda a data do artigo da EC que a traz
(`versao` = "EC132.artN"). Para a EC 132, `vigor_desde` = `efeitos_desde`.

Regras que este módulo nunca quebra:
- ano sem dia ("em 2027") vira 1º de janeiro daquele ano;
- o que não é reconhecido com segurança fica `metodo: "indeterminado"` com
  datas `None`, e gera aviso. Nunca cai em silêncio na regra dos "demais";
- `efeitos_ate` de uma versão é o dia anterior ao início da versão seguinte
  do mesmo dispositivo; se a seguinte não tem data, fica `None`. Data de
  término nunca é inventada.

O art. 22 revoga dispositivos em 2027 e 2033 ("os arts. 155, II, e §§ 2º a
5º, ... da Constituição Federal"). Revogar encerra as versões que começam
antes da revogação, e revogar um inciso revoga também suas alíneas. Versões
que começam na data da revogação ou depois representam o estado posterior
(ex.: o art. 5º republica "§ 2º (Revogado)." a partir de 2033) e não mudam.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from taxlaw.ingest.structure import Record

_PUBLICATION = re.compile(r"publicado no DOU (\d{2})\.(\d{2})\.(\d{4})")
_IN_YEAR = re.compile(r"^([IVXLC]+) - em (\d{4}), em relação aos? arts?\. (.+?);?(?: e)?$")
_ON_PUBLICATION = re.compile(r"^([IVXLC]+) - na data de sua publicação, em relação aos demais dispositivos\.?$")
_ARTICLE_LIST = re.compile(r"\d+(?:º|o)?(?:(?:, | e )\d+(?:º|o)?)*")
_FUNDAMENTO = "EC 132/2023, art. 23, {inciso}"
_REVOKE_YEAR = re.compile(r"^([IVXLC]+) - em (\d{4})(?:, (.+?))?:?;?(?: e)?$")
_REVOKE_ITEM = re.compile(r"^([a-z])\) (.+?);?(?: e)?$")
# Peças de uma lista de revogação, na ordem em que aparecem no texto.
_REVOKE_TOKEN = re.compile(r'§§ (\d+)º? a (\d+)º?|§ (\d+)º?|"([a-z])"|\b([IVXLC]+)\b|\b(\d+(?:-[A-Z])?)\b')


@dataclass(frozen=True)
class ArticleRule:
    """Quando entra em vigor um artigo da EC, e por quê."""

    desde: date | None
    fundamento: str | None
    metodo: str  # "automatico" | "indeterminado"


@dataclass(frozen=True)
class Effects:
    """Datas de uma versão de um dispositivo."""

    vigor_desde: date | None
    efeitos_desde: date | None
    efeitos_ate: date | None
    fundamento: str | None
    metodo: str  # "automatico" | "indeterminado"
    fundamento_ate: str | None = None  # revogação que encerra a versão, se houver


@dataclass(frozen=True)
class Revocation:
    """Um dispositivo revogado (e, com ele, todos os seus filhos)."""

    id: str
    desde: date  # primeiro dia sem efeitos
    fundamento: str


@dataclass
class EffectsResult:
    rules: dict[int, ArticleRule] = field(default_factory=dict)
    revocations: list[Revocation] = field(default_factory=list)
    by_version: dict[tuple[str, str], Effects] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


INDETERMINATE = ArticleRule(desde=None, fundamento=None, metodo="indeterminado")


def find_publication_date(texts: Iterable[str]) -> date | None:
    """Data do DOU na nota "Este texto não substitui o publicado no DOU dd.mm.aaaa"."""
    for text in texts:
        if m := _PUBLICATION.search(text):
            day, month, year = (int(g) for g in m.groups())
            return date(year, month, day)
    return None


def _article_number(versao: str) -> int:
    """'EC132.art11' → 11."""
    return int(versao.removeprefix("EC132.art"))


def parse_vigencia(
    records: list[Record], publication: date | None
) -> tuple[dict[int, ArticleRule], list[str]]:
    """Lê os incisos do art. 23 e devolve a regra de cada artigo da EC presente."""
    warnings: list[str] = []
    articles = sorted({_article_number(r.versao) for r in records})
    explicit: dict[int, list[ArticleRule]] = defaultdict(list)
    default: ArticleRule | None = None
    # Se algum inciso não for entendido, não dá para saber quem são "os demais":
    # aplicar a regra geral assim seria cair nela em silêncio.
    something_unrecognized = False

    incisos = [r for r in records if r.versao == "EC132.art23" and ".inc" in r.id]
    if not incisos:
        warnings.append("art. 23 da EC sem incisos: nenhuma data de vigor reconhecida")
    for record in incisos:
        if m := _IN_YEAR.match(record.texto):
            inciso, year, listed = m.group(1), int(m.group(2)), m.group(3)
            if not _ARTICLE_LIST.fullmatch(listed):
                warnings.append(f"lista de artigos não reconhecida no art. 23, {inciso}: {listed}")
                something_unrecognized = True
                continue
            # Ano sem dia: vale desde 1º de janeiro daquele ano.
            rule = ArticleRule(date(year, 1, 1), _FUNDAMENTO.format(inciso=inciso), "automatico")
            for number in re.findall(r"\d+", listed):
                explicit[int(number)].append(rule)
        elif m := _ON_PUBLICATION.match(record.texto):
            inciso = m.group(1)
            if publication is None:
                warnings.append(f"art. 23, {inciso}: data de publicação não encontrada")
            else:
                default = ArticleRule(publication, _FUNDAMENTO.format(inciso=inciso), "automatico")
        else:
            warnings.append(f"inciso do art. 23 não reconhecido: {record.texto[:70]}")
            something_unrecognized = True
    if default is not None and something_unrecognized:
        warnings.append("regra dos demais dispositivos não aplicada: há inciso do art. 23 não reconhecido")
        default = None

    rules: dict[int, ArticleRule] = {}
    for number in articles:
        found = explicit.get(number, [])
        if len(found) > 1:
            warnings.append(f"art. {number} da EC citado em mais de um inciso do art. 23")
            rules[number] = INDETERMINATE
        elif found:
            rules[number] = found[0]
        elif default is not None:
            rules[number] = default
        else:
            rules[number] = INDETERMINATE
    return rules, warnings


def parse_revocation_list(text: str) -> list[str] | None:
    """'os arts. 155, II, e §§ 2º a 5º, 156, III, da Constituição Federal' → ids.

    Número = novo artigo; romano = inciso do artigo atual; "x" = alínea do
    inciso atual; § N / §§ A a B = parágrafos do artigo atual. A norma vem do
    fim da frase. None se a norma não for reconhecida ou se uma peça aparecer
    fora de contexto (ex.: alínea antes de qualquer inciso).
    """
    if "Constituição Federal" in text:
        norma = "CF"
    elif "Ato das Disposições Constitucionais Transitórias" in text:
        norma = "ADCT"
    else:
        return None
    body = re.split(r"\s+d[ao] (?:Constituição Federal|Ato das Disposições)", text)[0]
    body = re.sub(r"^(?:os |o )?arts?\. ", "", body.strip())
    ids: list[str] = []
    article: str | None = None
    inciso: str | None = None
    for m in _REVOKE_TOKEN.finditer(body):
        par_from, par_to, par, alinea, roman, number = m.groups()
        if number is not None:
            article, inciso = f"{norma}.art{number}", None
            ids.append(article)
        elif article is None:
            return None
        elif roman is not None:
            inciso = f"{article}.inc{roman}"
            ids.append(inciso)
        elif alinea is not None:
            if inciso is None:
                return None
            ids.append(f"{inciso}.ali{alinea}")
        else:
            inciso = None
            first, last = (int(par), int(par)) if par else (int(par_from), int(par_to))
            ids.extend(f"{article}.par{n}" for n in range(first, last + 1))
    # Peça seguida de filhos é só contexto: em "158, IV, \"a\"" revoga-se a
    # alínea a, não o art. 158 nem o inciso IV inteiros.
    return [i for k, i in enumerate(ids) if not (k + 1 < len(ids) and ids[k + 1].startswith(i + "."))]


def parse_revocations(records: list[Record]) -> tuple[list[Revocation], list[str]]:
    """Lê o art. 22 (incisos com ano; alíneas quando o inciso termina em ':')."""
    warnings: list[str] = []
    revocations: list[Revocation] = []
    art22 = [r for r in records if r.versao == "EC132.art22" and r.id != "EC132.art22"]
    current_year: tuple[str, int] | None = None
    for record in art22:
        level = record.id.removeprefix("EC132.art22.")  # "incI" ou "incII.alia"
        if re.fullmatch(r"inc[IVXLC]+", level):
            m = _REVOKE_YEAR.match(record.texto)
            if not m:
                warnings.append(f"inciso do art. 22 não reconhecido: {record.texto[:70]}")
                current_year = None
                continue
            inciso, year, listed = m.group(1), int(m.group(2)), m.group(3)
            current_year = (inciso, year)
            if listed:
                _add(revocations, warnings, listed, date(year, 1, 1), f"EC 132/2023, art. 22, {inciso}")
        elif re.fullmatch(r"inc[IVXLC]+\.ali[a-z]", level) and current_year is not None:
            m = _REVOKE_ITEM.match(record.texto)
            if not m:
                warnings.append(f"alínea do art. 22 não reconhecida: {record.texto[:70]}")
                continue
            inciso, year = current_year
            _add(revocations, warnings, m.group(2), date(year, 1, 1), f"EC 132/2023, art. 22, {inciso}, {m.group(1)}")
        else:
            warnings.append(f"dispositivo do art. 22 não reconhecido: {record.texto[:70]}")
    return revocations, warnings


def _add(revocations: list[Revocation], warnings: list[str], text: str, desde: date, fundamento: str) -> None:
    ids = parse_revocation_list(text)
    if ids is None:
        warnings.append(f"lista de revogação não reconhecida ({fundamento}): {text[:70]}")
        return
    revocations.extend(Revocation(i, desde, fundamento) for i in ids)


def _revocation_for(rid: str, revocations: list[Revocation]) -> Revocation | None:
    """A revogação mais cedo que atinge o dispositivo ou um ancestral dele."""
    hits = [r for r in revocations if rid == r.id or rid.startswith(r.id + ".")]
    return min(hits, key=lambda r: r.desde) if hits else None


def compute_effects(
    records: list[Record], rules: dict[int, ArticleRule], revocations: list[Revocation] | None = None
) -> tuple[dict[tuple[str, str], Effects], list[str]]:
    """Datas de cada (id, versao): início pelo artigo da EC, término pela versão seguinte."""
    warnings: list[str] = []
    versions: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        versions[record.id].append(record)

    by_version: dict[tuple[str, str], Effects] = {}
    for rid, recs in versions.items():
        # Ordem legislativa: as versões vêm na ordem dos artigos da EC.
        recs = sorted(recs, key=lambda r: _article_number(r.versao))
        starts = [rules.get(_article_number(r.versao), INDETERMINATE) for r in recs]
        for i, (record, rule) in enumerate(zip(recs, starts)):
            end: date | None = None
            if i + 1 < len(recs):
                following = starts[i + 1].desde
                if following is not None and rule.desde is not None and following <= rule.desde:
                    warnings.append(f"versões de {rid} com início fora de ordem: {record.versao} e {recs[i + 1].versao}")
                elif following is not None:
                    end = following - timedelta(days=1)
            end_reason: str | None = None
            revoked = _revocation_for(rid, revocations or [])
            if revoked is not None and rule.desde is not None:
                if rule.desde < revoked.desde:
                    last_day = revoked.desde - timedelta(days=1)
                    if end is None or last_day < end:
                        end, end_reason = last_day, revoked.fundamento
                elif "Revogado" not in record.texto:
                    warnings.append(f"{rid} ({record.versao}) começa depois de revogado por {revoked.fundamento}")
            by_version[(rid, record.versao)] = Effects(
                vigor_desde=rule.desde,
                efeitos_desde=rule.desde,
                efeitos_ate=end,
                fundamento=rule.fundamento,
                metodo=rule.metodo,
                fundamento_ate=end_reason,
            )
    return by_version, warnings


def effects_for(records: list[Record], publication: date | None) -> EffectsResult:
    """Atalho para o build: regras do art. 23 + datas de todas as versões."""
    rules, warnings = parse_vigencia(records, publication)
    revocations, revocation_warnings = parse_revocations(records)
    by_version, more = compute_effects(records, rules, revocations)
    return EffectsResult(
        rules=rules,
        revocations=revocations,
        by_version=by_version,
        warnings=warnings + revocation_warnings + more,
    )
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_effects.py tests/test_effects_real.py -v` → 32 passed.

- [ ] **Step 5: nota do passo.** Crie `docs/steps/06-effects.md`:

```markdown
# Passo 06: effects (datas de vigor e efeitos)

## O que mudou

- `src/taxlaw/ingest/effects.py`, puro como o `structure`:
  - `find_publication_date` lê "publicado no DOU 21.12.2023" na nota da página.
  - `parse_vigencia` interpreta os incisos do **art. 23** e dá uma regra por artigo da EC: arts. 3º e 11 em 2027, arts. 4º e 5º em 2033, os demais na publicação.
  - `parse_revocation_list` e `parse_revocations` leem o **art. 22**: 16 dispositivos revogados em 2027 e 2033.
  - `compute_effects` dá a cada (`id`, `versao`) `vigor_desde` = `efeitos_desde`, `efeitos_ate`, `fundamento`, `fundamento_ate` e `metodo`.
  - `effects_for` junta tudo para o build (passo 07).
- 23 testes com registros sintéticos e 9 contra o corpus real.

## Como rodar

    uv run pytest tests/test_effects.py tests/test_effects_real.py -v

Para ver as três versões do inciso IX:

    uv run python -c "from taxlaw.ingest.structure import *; from taxlaw.ingest.effects import *; h = decode_html(open('corpus/raw/ec132-2023.html','rb').read()); r = parse(h).records; e = effects_for(r, find_publication_date(t for _, t in paragraphs(h))); [print(k[1], v.efeitos_desde, '->', v.efeitos_ate) for k, v in e.by_version.items() if k[0] == 'CF.art156-A.par1.incIX']"

## O que observar

- **A letra da lei corrigiu a spec:** o art. 23 diz "esta Emenda **entra em vigor**: I - em 2027...". A vigência é escalonada, não só os efeitos. Para a EC 132, `vigor_desde` = `efeitos_desde`.
- **Ano sem dia vira 1º de janeiro:** "em 2027" → 2027-01-01, regra escrita no código.
- **Término pela versão seguinte:** o inciso IX vale de 2023-12-21 a 2026-12-31 (art. 1º), de 2027-01-01 a 2032-12-31 (art. 3º) e a partir de 2033-01-01 (art. 4º).
- **Revogação também encerra:** o art. 155, § 3º, alterado em 2023, vale até 2032-12-31 porque o art. 22, II, "a" o revoga em 2033. Sem isso, o server diria "sem término".
- **Contexto não é revogado:** em "158, IV, \"a\"", só a alínea a cai. O inciso IV e a alínea b continuam.
- **"(Revogado)" é uma versão:** o art. 5º republica o ADCT 82, § 2º, como "(Revogado)" a partir de 2033. Essa versão representa o estado depois da revogação e não é encerrada por ela.
- **Nada de regra geral silenciosa:** se um inciso do art. 23 não for entendido, ninguém cai nos "demais". Fica tudo `indeterminado`, com aviso.

## Pergunta de previsão

Com `data_referencia` 2035-01-01, alguém pergunta sobre o art. 155, § 3º, da CF. O registro existe no corpus, com texto e citação. O que o server deve responder: o texto, um "não encontrei", ou outra coisa? Pense em `produz_efeitos_na_data` e em `fundamento_ate`.
```

- [ ] **Step 6: commit.** `git add src/taxlaw/ingest/effects.py tests/test_effects.py tests/test_effects_real.py docs/steps/06-effects.md` e `git commit -m "feat(step-06): effects (vigência do art. 23 e revogações do art. 22)"`.

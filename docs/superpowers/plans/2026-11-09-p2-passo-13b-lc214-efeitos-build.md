# P2, passo 13b: efeitos do art. 544 e o corpus com duas fontes (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-09-p2-passo-13b-lc214-efeitos-build.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** os 162 registros da LC 214 entram no `corpus/dispositivos.json` com vigor e efeitos calculados pelo art. 544, num build com duas fontes (cabeçalho `fontes`), e as ferramentas apontam `fonte_url` para a norma de cada dispositivo.

**Architecture:** Task 1 cria `ingest/lc_effects.py` (publicação pela 1ª nota "DOU de d.m.aaaa"; incisos do art. 544 → regras por artigo; ressalvas e alterações da LC 227 → `indeterminado`). Task 2 muda `build.py` (duas fontes, `check_lc_minimum`, ordem por versão de normas diferentes, cabeçalho `fontes`), `corpus.py` (`fontes`, `source_of`, `coletado_em` = a mais antiga) e duas linhas de `tools.py`, regenera `dispositivos.json` e ajusta os testes que conheciam o cabeçalho antigo, mais os 7 casos da LC conferidos pelo usuário.

**Tech Stack:** Python 3.13 (biblioteca padrão: `re`, `datetime`, `dataclasses`), pyyaml (já existe), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-09-lc214-capitulos-design.md` (seções 5, 6, 7 e 8), sobre a principal `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md`.

## Global Constraints

- Nenhuma dependência nova.
- As 487 linhas da EC no `dispositivos.json` não mudam (mesmo conteúdo e mesma ordem); as 162 da LC vêm depois delas.
- O schema das ferramentas não muda: só `fonte_url` (passa a ser o da norma do dispositivo) e o valor de `corpus.coletado_em` (a coleta mais antiga entre as fontes).
- Data de efeito nunca é inventada: inciso não reconhecido bloqueia a regra dos demais; ressalva, artigo em dois incisos, redação dada/incluído por outra lei e "parte promulgada após veto" → `indeterminado`.
- O build aborta sem gravar nada se qualquer fonte falhar (sha256, erro de parser, estrutura mínima, correção inválida).
- Não alterar `corpus/raw/`, `corpus/efeitos_correcoes.yaml`, `structure.py`, `lc_structure.py`, `effects.py`, `fetch.py`, `search.py`, `versions.py`, `server.py`, `client/`, `.claude/`, `.kiro/`, `hooks/`, `pyproject.toml`, `uv.lock`.
- Testes 100% offline e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-09 no protótipo)

- `lc_paragraphs` do HTML real: o art. 544 vem com o inciso III antigo como parágrafo tachado (descartado) e o III atual terminando em "(Redação dada pela Lei Complementar nº 227, de 2026)". Notas: "Este texto não substitui o publicado no DOU de 16.1.2025 - Edição extra e republicado no DOU de 23.1.2025" e, depois, "… DOU de 2.7.2025." (promulgação de partes vetadas).
- `parse_544` no real: publicação 2025-01-16; regra padrão VI = 2026-01-01; inciso I = 2025-05-01; 74 artigos citados nos incisos I a V; com ressalva: 58, 60 e 450; nenhum artigo do escopo (125 a 142, 419 a 423) citado nos incisos I a V.
- Build: `dispositivos: 649 versões, 636 ids`; `por norma: ADCT 132, CF 196, EC132 159, LC214 162`; `por método: automatico 645, indeterminado 4`; indeterminados = `LC214.art126.par6`, `LC214.art142.incII`, `LC214.art422.par2`, `LC214.art422.par5`; `avisos: 0`. As 487 linhas da EC são idênticas às do arquivo atual.
- Com o corpus novo, "IBS" e "CBS" sozinhos acham só dispositivos `LC214.*` (a LC usa as siglas; a EC e a CF não). O teste da skill que dizia "sigla sozinha não acha nada" muda para "sigla sozinha só acha a LC".
- Sem recalibrar, `test_search_real` continua passando (limiar 0,15); "cesta básica" → `EC132.art8.parunico`, `EC132.art8`, `LC214.art125`; "redução de 30% advogados" → `LC214.art127.incII` em 1º.
- 7 casos da LC conferidos pelo usuário contra o Planalto em 2026-11-09 (lista em `LC_CHECKED_BY_USER`, Task 2).
- Verificação de mutação no protótipo: todas as 11 mutações planejadas quebram ao menos um teste (inclusive "artigo em dois incisos" e "erro da LC ignorado pelo build", que só foram pegas depois dos testes `test_article_in_two_incisos_has_no_single_rule` e `test_cli_lc_error_aborts_without_writing`).

## Review Focus

- Número de parágrafo com "º" lido como artigo numa lista do art. 544 (teste `test_paragraph_numbers_with_ordinal_are_not_articles`).
- "quarto mês subsequente" numa publicação perto do fim do ano (teste `test_relative_date_crosses_the_year`).
- Dispositivo alterado pela LC 227 recebendo a data da LC 214 (teste `test_amended_or_promulgated_is_fully_indeterminate` e `test_lc_cases_checked_by_user`).
- Linhas da EC mudando de lugar ou de conteúdo com a entrada da LC (teste `test_ec_rows_are_unchanged_by_the_lc`).
- `fonte_url` de um dispositivo da LC apontando para a EC (teste `test_source_url_follows_the_device_norm`).

---

### Task 1: Efeitos da LC pelo art. 544

**Files:**
- Create: `src/taxlaw/ingest/lc_effects.py`
- Create: `tests/test_lc_effects.py`

**Interfaces:**
- Consumes: `taxlaw.ingest.effects.Effects(vigor_desde, efeitos_desde, efeitos_ate, fundamento, metodo, fundamento_ate=None)`; `taxlaw.ingest.structure.Record`, `decode_html`; `taxlaw.ingest.lc_structure.lc_paragraphs` (passo 13a); `corpus/raw/lc214-2025.html`.
- Produces: `taxlaw.ingest.lc_effects.Rule(desde: date, inciso: str)`; `LcEffectsResult(publication, rules: dict[str, Rule], qualified: set[str], default: Rule | None, by_version: dict[tuple[str, str], Effects], warnings: list[str])`; `find_lc_publication_date(texts) -> date | None`; `parse_article_list(text) -> tuple[list[str], set[str]] | None`; `parse_544(texts, publication) -> LcEffectsResult`; `lc_effects_for(records, texts) -> LcEffectsResult` (`texts`: parágrafos não tachados do documento inteiro).

- [ ] **Step 1: testes que falham.** Crie `tests/test_lc_effects.py`:

```python
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
    # Nenhum artigo do escopo do passo 13 aparece nos incisos I a V.
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
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_lc_effects.py -q` → `ModuleNotFoundError: No module named 'taxlaw.ingest.lc_effects'`.

- [ ] **Step 3: implemente.** Crie `src/taxlaw/ingest/lc_effects.py`:

```python
"""Art. 544 da LC 214 → datas de vigor e efeitos dos registros da LC (puro).

O art. 544 (redação atual, spec do passo 13, seção 2) diz que a LC "entra em
vigor na data de sua publicação, produzindo efeitos:" e escalona os efeitos
por artigo em incisos:

    I - a partir do primeiro dia do quarto mês subsequente ao da sua
        publicação, em relação aos arts. 537 a 540;
    II - a partir de 1º de janeiro de 2025, em relação aos arts. 35, 58,
         caput, 60, § 3º, ...;
    ...
    VI - a partir de 1º de janeiro de 2026, em relação aos demais dispositivos.

Diferente da EC 132, aqui vigor e efeitos se separam: `vigor_desde` é a data
de publicação; `efeitos_desde`, a do inciso que alcança o artigo.

Regras que este módulo nunca quebra (as mesmas da EC):
- inciso não reconhecido bloqueia a regra dos "demais dispositivos": tudo o
  que dependeria dela fica `indeterminado`, com aviso;
- artigo citado com ressalva ("58, caput", "60, § 3º", "450, exceto os §§ 1º
  e 5º") fica `indeterminado` no artigo inteiro: a regra não é do artigo todo;
- dispositivo com redação dada ou incluído por outra lei (LC 227/2026), ou
  promulgado depois de veto, fica com vigor e efeitos nulos e `indeterminado`:
  a data dele está em outra norma, fora do corpus;
- data nunca é inventada.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from taxlaw.ingest.effects import Effects
from taxlaw.ingest.structure import Record

# "Este texto não substitui o publicado no DOU de 16.1.2025 - Edição extra ..."
# A 1ª nota é a da publicação; a de 2.7.2025 é a da promulgação de partes vetadas.
_PUBLICATION = re.compile(r"publicado no DOU de (\d{1,2})\.(\d{1,2})\.(\d{4})")
_ARTICLE_START = re.compile(r"^Art\. (\d+)")
_INCISO = re.compile(r"^([IVXLC]+) - a partir (d[oe] .+?), em relação (aos demais dispositivos|aos? arts?\. .+?)[.;]?(?: e)?$")
_FIXED_DATE = re.compile(r"^de (\d{1,2})º? de (\w+) de (\d{4})$")
_RELATIVE_DATE = re.compile(r"^do primeiro dia do (\w+) mês subsequente ao da sua publicação$")
_LIST_TOKEN = re.compile(r"caput|exceto|§§?|(\d+(?:-[A-Z])?)(º)?(?:\s+a\s+(\d+))?")
_MONTHS = {m: i for i, m in enumerate(
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split(), start=1)}
_ORDINALS = {o: i for i, o in enumerate(
    "primeiro segundo terceiro quarto quinto sexto sétimo oitavo nono décimo".split(), start=1)}
_FUNDAMENTO = "LC 214/2025, art. 544, {inciso}"


@dataclass(frozen=True)
class Rule:
    desde: date
    inciso: str


@dataclass
class LcEffectsResult:
    publication: date | None = None
    rules: dict[str, Rule] = field(default_factory=dict)  # artigo ("128", "76-A") → regra
    qualified: set[str] = field(default_factory=set)  # artigos citados com ressalva
    default: Rule | None = None  # "demais dispositivos"; None se ausente ou bloqueada
    by_version: dict[tuple[str, str], Effects] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def find_lc_publication_date(texts: Iterable[str]) -> date | None:
    """Data da 1ª nota "publicado no DOU de d.m.aaaa"."""
    for text in texts:
        if m := _PUBLICATION.search(text):
            day, month, year = (int(g) for g in m.groups())
            return date(year, month, day)
    return None


def _date_of(phrase: str, publication: date | None) -> date | None:
    """'de 1º de janeiro de 2026' ou 'do primeiro dia do quarto mês subsequente ...'."""
    if m := _FIXED_DATE.match(phrase):
        month = _MONTHS.get(m.group(2))
        return date(int(m.group(3)), month, int(m.group(1))) if month else None
    if (m := _RELATIVE_DATE.match(phrase)) and publication and (n := _ORDINALS.get(m.group(1))):
        months = publication.month - 1 + n
        return date(publication.year + months // 12, months % 12 + 1, 1)
    return None


def parse_article_list(text: str) -> tuple[list[str], set[str]] | None:
    """'arts. 35, 58, caput, 480 a 484 e 541' → (artigos, artigos com ressalva).

    Número com "º" é de parágrafo (parte de uma ressalva), não artigo. None se
    sobrar texto não reconhecido.
    """
    body = re.sub(r"^aos? arts?\. ", "", text)
    leftover = _LIST_TOKEN.sub("", body)
    if re.sub(r"[\s,]|\be\b|\bos\b", "", leftover):
        return None
    articles: list[str] = []
    qualified: set[str] = set()
    for m in _LIST_TOKEN.finditer(body):
        number, ordinal, until = m.group(1), m.group(2), m.group(3)
        if number is None or ordinal:  # caput, §, §§, exceto, ou o número de um parágrafo
            if articles:
                qualified.add(articles[-1])
            continue
        if until:
            articles += [str(n) for n in range(int(number), int(until) + 1)]
        else:
            articles.append(number)
    return articles, qualified


def parse_544(texts: list[str], publication: date | None) -> LcEffectsResult:
    """Regras do art. 544 a partir dos parágrafos não tachados do documento inteiro."""
    result = LcEffectsResult(publication=publication)
    start = next((i for i, t in enumerate(texts) if t.startswith("Art. 544.")), None)
    if start is None:
        result.warnings.append("art. 544 não encontrado: efeitos da LC indeterminados")
        return result
    if publication is None:
        result.warnings.append("data de publicação da LC não encontrada: efeitos indeterminados")
    blocked = False
    for text in texts[start + 1:]:
        if _ARTICLE_START.match(text) or text.startswith("Brasília,"):
            break
        text = re.sub(r"\s*\((Redação dada|Incluíd[oa])[^()]*\)\s*$", "", text).strip()
        m = _INCISO.match(text)
        when = _date_of(m.group(2), publication) if m else None
        listed = parse_article_list(m.group(3)) if m and m.group(3) != "aos demais dispositivos" else None
        if m is None or when is None or (m.group(3) != "aos demais dispositivos" and listed is None):
            result.warnings.append(f"inciso do art. 544 não reconhecido; regra dos demais bloqueada: {text[:80]!r}")
            blocked = True
            continue
        rule = Rule(when, m.group(1))
        if listed is None:
            result.default = rule
            continue
        articles, qualified = listed
        result.qualified |= qualified
        for article in articles:
            if article in result.rules:
                result.qualified.add(article)  # dois incisos para o mesmo artigo: não há regra única
            result.rules[article] = rule
    if blocked:
        result.default = None
    return result


def _article_of(rid: str) -> str:
    """'LC214.art128.par1.incII' → '128'."""
    return rid.split(".")[1].removeprefix("art")


def lc_effects_for(records: list[Record], texts: list[str]) -> LcEffectsResult:
    """Efeitos de cada registro da LC. `texts`: parágrafos não tachados do documento."""
    result = parse_544(texts, find_lc_publication_date(texts))
    indeterminate = Effects(vigor_desde=None, efeitos_desde=None, efeitos_ate=None, fundamento=None, metodo="indeterminado")
    for r in records:
        key = (r.id, r.versao)
        if r.alteracao != "original" or "promulgada após veto" in r.origem:
            result.by_version[key] = indeterminate
            continue
        article = _article_of(r.id)
        # Ressalva → indeterminado; citado num inciso → a regra dele; senão, "demais dispositivos".
        rule = None if article in result.qualified else result.rules.get(article, result.default)
        if rule is None or result.publication is None:
            result.by_version[key] = Effects(vigor_desde=result.publication, efeitos_desde=None, efeitos_ate=None, fundamento=None, metodo="indeterminado")
            continue
        result.by_version[key] = Effects(
            vigor_desde=result.publication,
            efeitos_desde=rule.desde,
            efeitos_ate=None,
            fundamento=_FUNDAMENTO.format(inciso=rule.inciso),
            metodo="automatico",
        )
    return result
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_lc_effects.py -q` → 17 passed; `uv run pytest -q` → 424 passed.

- [ ] **Step 5: commit.** `git add src/taxlaw/ingest/lc_effects.py tests/test_lc_effects.py && git commit -m "feat(step-13b): efeitos da LC 214 pelo art. 544"`

### Task 2: Build com duas fontes, corpus e ferramentas

**Files:**
- Modify: `src/taxlaw/ingest/build.py`
- Modify: `src/taxlaw/corpus.py`
- Modify: `src/taxlaw/tools.py` (duas linhas)
- Modify: `corpus/dispositivos.json` (regenerado pelo build)
- Modify: `tests/test_build.py`
- Modify: `tests/test_build_real.py`
- Modify: `tests/test_search.py`
- Modify: `tests/test_tools.py`
- Modify: `tests/test_tools_real.py`
- Modify: `tests/test_skill.py`
- Create: `docs/steps/13b-lc214-efeitos-build.md`

**Interfaces:**
- Consumes: `lc_effects_for`, `LcEffectsResult` (Task 1); `taxlaw.ingest.lc_structure.LC214_SCOPE`, `lc_paragraphs`, `parse_lc` (passo 13a).
- Produces: `dispositivos.json` com `{"fontes": {"ec132-2023": {url, coletado_em, sha256_html}, "lc214-2025": {...}}, "dispositivos": [...]}`; `build.render(records, effects, metas: dict[str, dict])`; `build.check_lc_minimum(records)`; `build.LC_MINIMUM_IDS`; `corpus.SOURCE_OF_VERSION`, `corpus.source_name(versao)`, `Corpus.fontes`, `Corpus.source_of(row) -> dict`, `Corpus.coletado_em` (propriedade: a coleta mais antiga). `Corpus.fonte` deixa de existir.

- [ ] **Step 1: testes que falham.** Substitua `tests/test_build.py` inteiro por:

```python
"""Testes do build (passo 07): correções, estrutura mínima, render e CLI.

As partes puras usam dados sintéticos. Os testes da CLI usam o corpus/raw
real como entrada (só leitura) e gravam sempre em tmp_path.
"""

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from taxlaw.ingest.build import (
    BuildError,
    Correction,
    apply_corrections,
    check_minimum,
    load_corrections,
    main,
    render,
)
from taxlaw.ingest.effects import Effects
from taxlaw.ingest.structure import Record

RAW_DIR = Path(__file__).resolve().parents[1] / "corpus" / "raw"
PUB = date(2023, 12, 21)
AUTO = Effects(PUB, PUB, None, "EC 132/2023, art. 23, III", "automatico")


def rec(rid: str, art: int = 1, pai: str | None = None) -> Record:
    return Record(rid, f"citação de {rid}", rid.split(".", 1)[0], pai, f"EC132.art{art}", f"EC 132/2023, art. {art}º", "incluido", "texto sintético")


# ---------------------------------------------------------------- correções


def test_empty_or_commented_file_has_no_corrections():
    assert load_corrections("") == []
    assert load_corrections("# só comentário\ncorrecoes: []\n") == []


def test_valid_correction_accepts_dates_with_or_without_quotes():
    text = """
correcoes:
  - id: CF.art10
    versao: EC132.art1
    efeitos_desde: 2024-01-01
    efeitos_ate: "2025-12-31"
    fundamento: "fundamento sintético"
"""
    assert load_corrections(text) == [Correction("CF.art10", "EC132.art1", date(2024, 1, 1), date(2025, 12, 31), "fundamento sintético")]


def test_invalid_corrections_report_every_problem_at_once():
    text = """
correcoes:
  - id: CF.art10
    versao: EC132.art1
    efeitos_desde: 2024-01-01
    fundamento: "   "
  - id: CF.art11
    versao: EC132.art1
    efeitos_desde: 2026-01-01
    efeitos_ate: 2025-01-01
    fundamento: f
    observacao: campo que não existe
  - id: CF.art12
    versao: EC132.art1
    efeitos_desde: "31/12/2025"
    fundamento: f
  - id: CF.art12
    versao: EC132.art1
    fundamento: f
  - versao: EC132.art1
    fundamento: f
"""
    with pytest.raises(BuildError) as exc:
        load_corrections(text)
    assert exc.value.errors == [
        "correção 1 (CF.art10, EC132.art1): 'fundamento' é obrigatório",
        "correção 2: campo desconhecido observacao",
        "correção 2 (CF.art11, EC132.art1): efeitos_ate antes de efeitos_desde",
        "correção 3: data inválida '31/12/2025' (use AAAA-MM-DD ou null)",
        "correção 4 (CF.art12, EC132.art1): correção duplicada",
        "correção 5: 'id' e 'versao' são obrigatórios",
    ]


def test_wrong_top_level_shape_is_an_error():
    with pytest.raises(BuildError) as exc:
        load_corrections("- id: CF.art10\n")
    assert exc.value.errors == ["efeitos_correcoes.yaml: esperado 'correcoes:' com uma lista"]


def test_correction_wins_over_automatic():
    by_version = {("CF.art10", "EC132.art1"): AUTO, ("CF.art11", "EC132.art1"): AUTO}
    fixed = apply_corrections(by_version, [Correction("CF.art10", "EC132.art1", date(2024, 1, 1), date(2025, 12, 31), "fundamento sintético")])
    assert fixed[("CF.art10", "EC132.art1")] == Effects(
        date(2024, 1, 1), date(2024, 1, 1), date(2025, 12, 31), "fundamento sintético", "correcao", "fundamento sintético"
    )
    assert fixed[("CF.art11", "EC132.art1")] == AUTO
    assert by_version[("CF.art10", "EC132.art1")] == AUTO  # a entrada não é alterada


def test_correction_for_unknown_version_is_an_error():
    with pytest.raises(BuildError) as exc:
        apply_corrections({("CF.art10", "EC132.art1"): AUTO}, [Correction("CF.art10", "EC132.art3", None, None, "f")])
    assert exc.value.errors == ["correção para versão inexistente: CF.art10 (EC132.art3)"]


# ---------------------------------------------------------- estrutura mínima


def test_minimum_structure():
    complete = [rec(i) for i in ("CF.art149-B", "CF.art156-A", "ADCT.art125")] + [rec(f"EC132.art{n}", n) for n in range(1, 24)]
    assert check_minimum(complete) == []
    missing = [r for r in complete if r.id not in ("CF.art156-A", "EC132.art7")]
    assert check_minimum(missing) == ["estrutura mínima ausente: CF.art156-A", "artigo da EC ausente: EC132.art7"]


# -------------------------------------------------------------------- render

METAS = {
    "ec132-2023": {"url": "https://exemplo.invalid/ec", "coletado_em": "2026-11-06", "sha256": "ab" * 32},
    "lc214-2025": {"url": "https://exemplo.invalid/lc", "coletado_em": "2026-11-09", "sha256": "cd" * 32},
}


def test_render_orders_by_id_then_ec_article_and_uses_spec_fields():
    records = [rec("CF.art10", 10), rec("CF.art10", 3), rec("ADCT.art1", 2)]
    effects = {(r.id, r.versao): AUTO for r in records}
    document = json.loads(render(records, effects, METAS))
    assert document["fontes"] == {
        "ec132-2023": {"url": "https://exemplo.invalid/ec", "coletado_em": "2026-11-06", "sha256_html": "ab" * 32},
        "lc214-2025": {"url": "https://exemplo.invalid/lc", "coletado_em": "2026-11-09", "sha256_html": "cd" * 32},
    }
    assert list(document["fontes"]) == ["ec132-2023", "lc214-2025"]
    rows = document["dispositivos"]
    # art. 3 antes do art. 10: ordem numérica, não alfabética ("art10" < "art3" como texto)
    assert [(r["id"], r["versao"]) for r in rows] == [("ADCT.art1", "EC132.art2"), ("CF.art10", "EC132.art3"), ("CF.art10", "EC132.art10")]
    assert list(rows[0]) == [
        "id", "citacao", "norma", "pai", "versao", "origem", "alteracao", "texto", "vigor_desde", "efeitos_desde",
        "efeitos_ate", "fundamento_efeitos", "fundamento_ate", "metodo",
    ]
    assert rows[0]["efeitos_desde"] == "2023-12-21" and rows[0]["efeitos_ate"] is None


def test_render_is_byte_stable_and_keeps_accents():
    records = [rec("CF.art10")]
    text = render(records, {(r.id, r.versao): AUTO for r in records}, METAS)
    assert text == render(records, {(r.id, r.versao): AUTO for r in records}, METAS)
    assert "citação" in text and text.endswith("}\n")


# ----------------------------------------------------------------------- CLI


def run(tmp_path: Path, *extra: str, raw_dir: Path = RAW_DIR, corrections: str = "correcoes: []\n") -> int:
    corrections_path = tmp_path / "efeitos_correcoes.yaml"
    corrections_path.write_text(corrections, encoding="utf-8")
    return main(["--raw-dir", str(raw_dir), "--corrections", str(corrections_path), "--output", str(tmp_path / "out.json"), *extra])


def test_cli_writes_report_and_file(tmp_path, capsys):
    assert run(tmp_path) == 0
    out = capsys.readouterr().out
    # EC 132 (487 versões, 474 ids) + LC 214 (162 registros, passo 13b).
    assert "dispositivos: 649 versões, 636 ids" in out
    assert "por norma: ADCT 132, CF 196, EC132 159, LC214 162" in out
    # Os 4 indeterminados são os dispositivos tocados pela LC 227/2026.
    assert "indeterminados: 4" in out and "avisos: 0" in out
    document = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert len(document["dispositivos"]) == 649
    assert document["fontes"]["ec132-2023"]["coletado_em"] == "2026-11-06"
    assert document["fontes"]["lc214-2025"]["coletado_em"] == "2026-11-09"


def test_cli_is_deterministic_and_check_mode(tmp_path, capsys):
    assert run(tmp_path) == 0
    first = (tmp_path / "out.json").read_bytes()
    assert run(tmp_path) == 0
    assert (tmp_path / "out.json").read_bytes() == first
    assert run(tmp_path, "--check") == 0
    (tmp_path / "out.json").write_text("[]\n", encoding="utf-8")
    assert run(tmp_path, "--check") == 1
    assert (tmp_path / "out.json").read_text(encoding="utf-8") == "[]\n"  # --check não grava
    assert "desatualizado" in capsys.readouterr().err


def test_cli_invalid_correction_aborts_without_writing(tmp_path, capsys):
    bad = "correcoes:\n  - id: CF.art156-A\n    versao: EC132.art1\n    efeitos_desde: 2024-01-01\n"
    assert run(tmp_path, corrections=bad) == 1
    assert not (tmp_path / "out.json").exists()
    assert "'fundamento' é obrigatório" in capsys.readouterr().err


def test_cli_corrupted_source_aborts_without_writing(tmp_path, capsys):
    raw = tmp_path / "raw"
    shutil.copytree(RAW_DIR, raw)
    (raw / "ec132-2023.html").write_bytes(b"corrompido")
    assert run(tmp_path, raw_dir=raw) == 1
    assert not (tmp_path / "out.json").exists()
    assert "sha256" in capsys.readouterr().err


def test_cli_applies_a_real_correction(tmp_path, capsys):
    fix = (
        "correcoes:\n  - id: ADCT.art125\n    versao: EC132.art2\n    efeitos_desde: 2026-01-01\n"
        "    efeitos_ate: null\n    fundamento: \"teste sintético de correção\"\n"
    )
    assert run(tmp_path, corrections=fix) == 0
    assert "correções aplicadas: 1" in capsys.readouterr().out
    rows = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))["dispositivos"]
    row = next(r for r in rows if r["id"] == "ADCT.art125")
    assert (row["efeitos_desde"], row["metodo"], row["fundamento_efeitos"]) == ("2026-01-01", "correcao", "teste sintético de correção")


def test_cli_lc_error_aborts_without_writing(tmp_path, capsys):
    # Passo 13b: erro do parser da LC também aborta o build (aqui, um artigo do escopo some).
    raw = tmp_path / "raw"
    shutil.copytree(RAW_DIR, raw)
    html = (raw / "lc214-2025.html").read_bytes().replace(b"Art. 125.", b"Art. 9125.")
    (raw / "lc214-2025.html").write_bytes(html)
    meta = json.loads((raw / "lc214-2025.meta.json").read_text(encoding="utf-8"))
    meta["sha256"] = hashlib.sha256(html).hexdigest()
    (raw / "lc214-2025.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert run(tmp_path, raw_dir=raw) == 1
    assert not (tmp_path / "out.json").exists()
    assert "artigo do escopo não encontrado: LC214.art125" in capsys.readouterr().err
```

Substitua `tests/test_build_real.py` inteiro por:

```python
"""O corpus versionado (passos 07 e 13b): em dia com o build e conferido pelo usuário."""

import json
from pathlib import Path

import pytest

from taxlaw.ingest.build import DEFAULT_CORRECTIONS, DEFAULT_OUTPUT, build

ROOT = Path(__file__).resolve().parents[1]
DISPOSITIVOS = ROOT / "corpus" / "dispositivos.json"

# Conferidos à mão pelo usuário contra o texto oficial da EC 132, em 2026-11-07.
# (id, versao): (alteracao, efeitos_desde, efeitos_ate, fundamento_efeitos, fundamento_ate, início do texto)
CHECKED_BY_USER = {
    ("CF.art149-B", "EC132.art1"): ("incluido", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                    "Art. 149-B. Os tributos previstos nos arts. 156-A e 195, V, observarão"),
    ("CF.art155.par3", "EC132.art1"): ("alterado", "2023-12-21", "2032-12-31", "EC 132/2023, art. 23, III", "EC 132/2023, art. 22, II, a",
                                       "§ 3º À exceção dos impostos de que tratam o inciso II do caput"),
    ("CF.art158.incIV.alib", "EC132.art1"): ("alterado", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                             "b) do produto da arrecadação do imposto previsto no art. 156-A"),
    ("CF.art156-A.par1.incIX", "EC132.art1"): ("incluido", "2023-12-21", "2026-12-31", "EC 132/2023, art. 23, III", None,
                                               "IX - não integrará sua própria base de cálculo nem a dos tributos previstos nos arts. 153, VIII, e 195, I, \"b\", IV e V"),
    ("CF.art156-A.par1.incIX", "EC132.art3"): ("alterado", "2027-01-01", "2032-12-31", "EC 132/2023, art. 23, I", None,
                                               "IX - não integrará sua própria base de cálculo nem a dos tributos previstos nos arts. 153, VIII, e 195, V;"),
    ("CF.art156-A.par1.incIX", "EC132.art4"): ("alterado", "2033-01-01", None, "EC 132/2023, art. 23, II", None,
                                               "IX - não integrará sua própria base de cálculo nem a dos tributos previstos nos arts. 153, VIII, e 195, V;"),
    ("ADCT.art125", "EC132.art2"): ("incluido", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                    "Art. 125. Em 2026, o imposto previsto no art. 156-A será cobrado à alíquota estadual de 0,1%"),
    ("ADCT.art82.par2", "EC132.art5"): ("alterado", "2033-01-01", None, "EC 132/2023, art. 23, II", None, "§ 2º (Revogado)."),
    ("EC132.art11", "EC132.art11"): ("original", "2027-01-01", None, "EC 132/2023, art. 23, I", None,
                                     "Art. 11. A revogação do art. 195, I, \"b\", não produzirá efeitos"),
    ("EC132.art12", "EC132.art12"): ("original", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                     "Art. 12.Fica instituído o Fundo de Compensação de Benefícios Fiscais"),
}


# Conferidos à mão pelo usuário contra o texto oficial da LC 214 no Planalto, em 2026-11-09.
# id: (alteracao, origem, vigor_desde, efeitos_desde, fundamento_efeitos, metodo, início do texto)
LC_CHECKED_BY_USER = {
    "LC214.art125": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico",
                     "Art. 125. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre as vendas de produtos destinados à alimentação humana relacionados no Anexo I"),
    "LC214.art127.incII": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico", "II - advogados;"),
    "LC214.art128.incI": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico", "I - serviços de educação;"),
    "LC214.art126.par6": ("incluido", "LC 214/2025, incluído pela LC 227/2026", None, None, None, "indeterminado",
                          "§ 6º O disposto no § 1º deste artigo não se aplica às remessas internacionais sujeitas ao Regime de Tributação Simplificada (RTS)"),
    "LC214.art142.incII": ("alterado", "LC 214/2025, com redação dada pela LC 227/2026", None, None, None, "indeterminado",
                           "II - fornecimento de serviços de segurança da informação e segurança cibernética"),
    "LC214.art422.par2": ("alterado", "LC 214/2025, com redação dada pela LC 227/2026", None, None, None, "indeterminado",
                          "§ 2º As alíquotas do Imposto Seletivo respeitarão o percentual máximo de 0,25% (vinte e cinco centésimos por cento), nas operações com bens minerais extraídos."),
    "LC214.art419": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico",
                     "Art. 419. As alíquotas do Imposto Seletivo aplicáveis aos veículos"),
}


@pytest.fixture(scope="module")
def document():
    return json.loads(DISPOSITIVOS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(document):
    return {(r["id"], r["versao"]): r for r in document["dispositivos"]}


def test_header_fontes_match_the_metas(document):
    assert list(document["fontes"]) == ["ec132-2023", "lc214-2025"]
    for name, fonte in document["fontes"].items():
        meta = json.loads((ROOT / "corpus" / "raw" / f"{name}.meta.json").read_text(encoding="utf-8"))
        assert fonte == {"url": meta["url"], "coletado_em": meta["coletado_em"], "sha256_html": meta["sha256"]}
        assert fonte["url"].startswith("https://www.planalto.gov.br/")


def test_default_paths_point_to_the_repo_corpus():
    assert DEFAULT_OUTPUT == DISPOSITIVOS
    assert DEFAULT_CORRECTIONS == ROOT / "corpus" / "efeitos_correcoes.yaml"


def test_committed_dispositivos_is_exactly_what_build_generates_today():
    # Se falhar: alguém mudou parser, effects, correções ou o HTML e não rodou o build.
    fresh = build(ROOT / "corpus" / "raw", DEFAULT_CORRECTIONS.read_text(encoding="utf-8"))
    assert DISPOSITIVOS.read_text(encoding="utf-8") == fresh.text


def test_cases_checked_by_user(rows):
    for key, (alteracao, desde, ate, fundamento, fundamento_ate, start) in CHECKED_BY_USER.items():
        row = rows[key]
        assert (row["alteracao"], row["efeitos_desde"], row["efeitos_ate"]) == (alteracao, desde, ate), key
        assert (row["fundamento_efeitos"], row["fundamento_ate"]) == (fundamento, fundamento_ate), key
        assert row["texto"].startswith(start), key


def test_lc_cases_checked_by_user(rows):
    for rid, (alteracao, origem, vigor, desde, fundamento, metodo, start) in LC_CHECKED_BY_USER.items():
        row = rows[(rid, "LC214")]
        assert (row["alteracao"], row["origem"], row["metodo"]) == (alteracao, origem, metodo), rid
        assert (row["vigor_desde"], row["efeitos_desde"], row["efeitos_ate"], row["fundamento_efeitos"]) == (vigor, desde, None, fundamento), rid
        assert row["texto"].startswith(start), rid


def test_ec_rows_are_unchanged_by_the_lc(rows):
    # A LC entrou sem mexer na EC: 487 versões, e as linhas da LC vêm depois de todas as da EC.
    norms = [row["norma"] for row in rows.values()]
    assert sum(n != "LC214" for n in norms) == 487
    assert norms.index("LC214") == 487 and set(norms[487:]) == {"LC214"}


def test_lc_effects_vigor_and_efeitos_separate(rows):
    lc = [row for (rid, versao), row in rows.items() if versao == "LC214"]
    assert len(lc) == 162
    automatic = [row for row in lc if row["metodo"] == "automatico"]
    assert len(automatic) == 158
    # Pela primeira vez no corpus, vigor e efeitos têm datas diferentes.
    assert {(row["vigor_desde"], row["efeitos_desde"], row["fundamento_efeitos"]) for row in automatic} == {
        ("2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI")
    }
    assert sorted(row["id"] for row in lc if row["metodo"] == "indeterminado") == [
        "LC214.art126.par6", "LC214.art142.incII", "LC214.art422.par2", "LC214.art422.par5",
    ]


def test_corpus_invariants(rows):
    assert len(rows) == 649
    for (rid, versao), row in rows.items():
        assert row["metodo"] in {"automatico", "correcao", "indeterminado"}, rid
        assert "fonte_url" not in row and "coletado_em" not in row, rid
        if row["metodo"] == "indeterminado":
            assert row["efeitos_desde"] is None, rid
        if row["efeitos_ate"] is not None:
            assert row["efeitos_ate"] >= row["efeitos_desde"], rid
```

Substitua `tests/test_search.py` inteiro por:

```python
"""Testes de corpus e search (passo 08) com um corpus sintético pequeno."""

import hashlib
import json

import pytest

from taxlaw.corpus import load_corpus
from taxlaw.search import THRESHOLD, build_index, score_all, search, tokenize


def row(rid: str, texto: str, versao: str = "EC132.art1") -> dict:
    return {"id": rid, "citacao": rid.replace(".", ", "), "versao": versao, "texto": texto}


ROWS = [
    row("CF.art1", "Texto sintético sobre o imposto de exemplo e suas alíquotas."),
    row("CF.art2", "Operações com mercadorias sintéticas e créditos do imposto."),
    row("CF.art2", "Operação com mercadoria sintética, redação nova e crédito.", "EC132.art3"),
    row("CF.art3", "Disposição sintética sobre fundos regionais de compensação."),
    row("CF.art156-A", "Artigo sintético numerado com letra."),
]


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "dispositivos.json"
    fontes = {"ec132-2023": {"url": "https://exemplo.invalid", "coletado_em": "2026-11-06", "sha256_html": "0" * 64}}
    path.write_text(json.dumps({"fontes": fontes, "dispositivos": ROWS}, ensure_ascii=False), encoding="utf-8")
    return load_corpus(path), path


def test_load_corpus_header_versions_and_hash(corpus):
    c, path = corpus
    assert c.coletado_em == "2026-11-06"
    assert c.source_of(c.versions("CF.art2")[0])["url"] == "https://exemplo.invalid"
    assert c.versao == hashlib.sha256(path.read_bytes()).hexdigest()
    assert c.ids() == ["CF.art1", "CF.art156-A", "CF.art2", "CF.art3"]
    assert [v["versao"] for v in c.versions("CF.art2")] == ["EC132.art1", "EC132.art3"]
    assert c.versions("CF.art999") == []


def test_tokenize_normalizes_accents_plural_and_stopwords():
    assert tokenize("As Operações com Créditos do Imposto") == ["operacao", "credito", "imposto"]
    assert tokenize("alíquotas reduzidas") == ["aliquota", "reduzida"]
    assert tokenize("art. 156-A") == ["156-a"]
    assert tokenize("de da do e ou") == []


def test_versions_are_grouped_in_one_hit_and_both_texts_count(corpus):
    c, _ = corpus
    hits = score_all(build_index(c), "redação nova")
    assert [h.id for h in hits] == ["CF.art2"]  # termo só da versão do art. 3, um resultado só


def test_ranking_and_ties_are_deterministic(corpus):
    c, _ = corpus
    index = build_index(c)
    assert [h.id for h in score_all(index, "crédito mercadoria")][:1] == ["CF.art2"]
    assert score_all(index, "sintético") == score_all(index, "sintético")
    tied = [h for h in score_all(index, "sintético") if h.score == score_all(index, "sintético")[0].score]
    assert [h.id for h in tied] == sorted(h.id for h in tied)


def test_search_finds_with_relevance_between_threshold_and_one(corpus):
    c, _ = corpus
    result = search(build_index(c), "fundos regionais de compensação")
    assert result.found and result.reason is None
    assert result.hits[0].id == "CF.art3"
    assert all(THRESHOLD <= h.relevance <= 1 for h in result.hits)


def test_article_number_with_letter(corpus):
    c, _ = corpus
    assert search(build_index(c), "art. 156-A").hits[0].id == "CF.art156-A"


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("", "a consulta não tem termos pesquisáveis"),
        ("de da do", "a consulta não tem termos pesquisáveis"),
        ("futebol churrasco", "nenhum dispositivo contém os termos da consulta"),
    ],
)
def test_not_found_has_explicit_reason(corpus, query, reason):
    c, _ = corpus
    result = search(build_index(c), query)
    assert (result.found, result.hits, result.reason) == (False, [], reason)


def test_one_known_word_among_many_unknown_is_below_threshold(corpus):
    c, _ = corpus
    result = search(build_index(c), "receita de bolo de chocolate com imposto e cobertura de morango")
    assert not result.found
    assert result.reason.startswith("relevância máxima ") and result.reason.endswith(f"abaixo do limiar {THRESHOLD}")


def test_limit_is_respected_and_validated(corpus):
    c, _ = corpus
    index = build_index(c)
    assert len(search(index, "sintético", limit=1).hits) == 1
    with pytest.raises(ValueError):
        search(index, "sintético", limit=0)
    with pytest.raises(ValueError):
        search(index, "sintético", limit=11)
```

Em `tests/test_tools.py`, troque a linha

```python
    document = {"fonte": {"url": "https://exemplo.invalid/ec", "coletado_em": "2026-11-06", "sha256_html": "ab" * 32}, "dispositivos": ROWS}
```

por

```python
    fontes = {"ec132-2023": {"url": "https://exemplo.invalid/ec", "coletado_em": "2026-11-06", "sha256_html": "ab" * 32}}
    document = {"fontes": fontes, "dispositivos": ROWS}
```

Em `tests/test_skill.py`, troque

```python
@pytest.mark.parametrize("abbreviation", ["IBS", "CBS"])
def test_abbreviations_alone_are_not_found_which_is_why_the_table_exists(abbreviation):
    assert tools.buscar_dispositivos(CTX, abbreviation, "2030-06-01", today=TODAY)["encontrado"] is False
```

por

```python
@pytest.mark.parametrize("abbreviation", ["IBS", "CBS"])
def test_abbreviations_alone_reach_only_the_lc_which_is_why_the_table_exists(abbreviation):
    # A EC e a CF não usam as siglas; a LC 214 (passo 13b) usa. A sigla sozinha
    # acha a LC, mas nunca o dispositivo da Constituição que institui o tributo.
    out = tools.buscar_dispositivos(CTX, abbreviation, "2030-06-01", limite=10, today=TODAY)
    assert out["resultados"] and all(r["id"].startswith("LC214.") for r in out["resultados"])
```

No fim de `tests/test_tools_real.py`, acrescente:

```python
def test_source_url_follows_the_device_norm():
    # Passo 13b: cada dispositivo aponta para a norma de onde veio.
    assert obter("LC214.art125")["fonte_url"] == "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    assert obter("CF.art156-A")["fonte_url"].endswith("/emc132.htm")


def test_corpus_collected_date_is_the_oldest_source():
    fontes = CTX.corpus.fontes
    assert obter("LC214.art125")["corpus"]["coletado_em"] == min(f["coletado_em"] for f in fontes.values()) == "2026-11-06"


def test_lc_device_vigor_before_effects():
    before, after = obter("LC214.art128.incI", "2025-06-01"), obter("LC214.art128.incI", "2026-06-01")
    assert before["vigor_desde"] == "2025-01-16" and before["efeitos"]["produz_efeitos_na_data"] is False
    assert after["efeitos"]["produz_efeitos_na_data"] is True
    assert obter("LC214.art142.incII")["efeitos"]["produz_efeitos_na_data"] is None
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest -q` → falhas e erros em `test_build.py`, `test_build_real.py`, `test_search.py`, `test_tools.py`, `test_tools_real.py` e `test_skill.py` (cabeçalho `fontes` inexistente, `Corpus` sem `coletado_em`/`source_of`, contagens antigas).

- [ ] **Step 3: `corpus.py`.** Substitua `src/taxlaw/corpus.py` inteiro por:

```python
"""Leitura de `corpus/dispositivos.json` (gerado pelo build): só leitura, sem rede.

`versao` é o sha256 do arquivo: toda resposta das ferramentas o expõe como
`corpus.versao`, e o P3 sabe se duas execuções usaram o mesmo corpus.

Desde o passo 13b o corpus tem várias fontes (EC 132 e LC 214), num
cabeçalho `fontes` chaveado pelo nome da fonte. A fonte de cada registro sai
do prefixo da `versao`: "EC132.art3" → ec132-2023; "LC214" → lc214-2025.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# src/taxlaw/corpus.py → parents[2] é a raiz do repositório.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "corpus" / "dispositivos.json"

# Prefixo da `versao` → nome da fonte em `fontes` (e em corpus/raw).
SOURCE_OF_VERSION = {"EC132": "ec132-2023", "LC214": "lc214-2025"}


def source_name(versao: str) -> str:
    """'EC132.art3' → 'ec132-2023'; 'LC214' → 'lc214-2025'."""
    return SOURCE_OF_VERSION[versao.split(".")[0]]


@dataclass(frozen=True)
class Corpus:
    fontes: dict  # nome da fonte → {url, coletado_em, sha256_html}
    dispositivos: tuple[dict, ...]
    versao: str
    _by_id: dict[str, list[dict]] = field(default_factory=dict, repr=False, compare=False)

    def ids(self) -> list[str]:
        """Ids distintos, em ordem."""
        return sorted(self._by_id)

    def versions(self, rid: str) -> list[dict]:
        """Versões de um id na ordem do arquivo (artigo da EC crescente); [] se não existe."""
        return list(self._by_id.get(rid, []))

    def source_of(self, row: dict) -> dict:
        """A fonte (url, coletado_em, sha256_html) de onde veio um registro."""
        return self.fontes[source_name(row["versao"])]

    @property
    def coletado_em(self) -> str:
        """A coleta mais antiga entre as fontes: o limite de quão desatualizado o corpus pode estar."""
        return min(f["coletado_em"] for f in self.fontes.values())


def load_corpus(path: Path = DEFAULT_PATH) -> Corpus:
    raw = path.read_bytes()
    document = json.loads(raw)
    by_id: dict[str, list[dict]] = defaultdict(list)
    for row in document["dispositivos"]:
        by_id[row["id"]].append(row)
    return Corpus(
        fontes=document["fontes"],
        dispositivos=tuple(document["dispositivos"]),
        versao=hashlib.sha256(raw).hexdigest(),
        _by_id=dict(by_id),
    )
```

- [ ] **Step 4: `tools.py`.** Troque

```python
    return {"versao": ctx.corpus.versao, "coletado_em": ctx.corpus.fonte["coletado_em"]}
```

por

```python
    # coletado_em: a coleta mais antiga entre as fontes (EC 132 e LC 214, passo 13b).
    return {"versao": ctx.corpus.versao, "coletado_em": ctx.corpus.coletado_em}
```

e troque

```python
        "fonte_url": ctx.corpus.fonte["url"],
```

por

```python
        "fonte_url": ctx.corpus.source_of(v)["url"],  # a norma de onde veio este dispositivo
```

Nada mais muda em `tools.py`.

- [ ] **Step 5: `build.py`.** Substitua `src/taxlaw/ingest/build.py` inteiro por:

```python
"""Build do corpus: fontes + efeitos + correções → corpus/dispositivos.json.

Uso:
    uv run python -m taxlaw.ingest.build            # gera e imprime o relatório
    uv run python -m taxlaw.ingest.build --check    # só confere se o arquivo está em dia

Regras (spec, seção 5):
- lê `coletado_em` e a URL do `.meta.json`, nunca do relógio;
- aborta, sem gravar nada, se o HTML não bater com o sha256 do meta, se o
  structure tiver erros, se faltar a estrutura mínima ou se alguma correção
  for inválida;
- correções de `efeitos_correcoes.yaml` vencem o automático e exigem
  `fundamento`;
- saída determinística: mesma entrada, mesmos bytes (o teste confere que o
  `dispositivos.json` versionado é exatamente o que o build gera hoje);
- `fonte_url` e `coletado_em` ficam uma vez só, no cabeçalho (spec, seção 5,
  decisão de 2026-11-07): repetidos em cada registro, uma recoleta que muda
  uma vírgula mudaria centenas de linhas e esconderia a mudança no diff.

Duas fontes desde o passo 13b (spec do passo 13, seção 6):
- `ec132-2023`: structure + effects (art. 23 e art. 22 da EC);
- `lc214-2025`: lc_structure (só os artigos de `LC214_SCOPE`) + lc_effects
  (art. 544). O cabeçalho vira `fontes`, chaveado pelo nome da fonte; cada
  fonte confere o próprio sha256, e o erro de qualquer uma aborta o build.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

import yaml

from taxlaw.ingest.effects import Effects, effects_for, find_publication_date
from taxlaw.ingest.fetch import DEFAULT_RAW_DIR, paths_for, verify
from taxlaw.ingest.lc_effects import lc_effects_for
from taxlaw.ingest.lc_structure import LC214_SCOPE, lc_paragraphs, parse_lc
from taxlaw.ingest.structure import Record, decode_html, paragraphs, parse

CORPUS_DIR = DEFAULT_RAW_DIR.parent
DEFAULT_CORRECTIONS = CORPUS_DIR / "efeitos_correcoes.yaml"
DEFAULT_OUTPUT = CORPUS_DIR / "dispositivos.json"

# Dispositivos que a EC traz por inteiro (novos) e o art. 23: se faltar
# algum, o corpus está quebrado, mesmo que o parser não reclame. (O caput do
# art. 195 não serve: no texto da EC ele aparece só como linha de pontos.)
MINIMUM_IDS = ("CF.art149-B", "CF.art156-A", "ADCT.art125", "EC132.art23")
EC_ARTICLES = range(1, 24)
# LC 214 (passo 13b): cesta básica, redução de 60% e alíquotas do IS.
LC_MINIMUM_IDS = ("LC214.art125", "LC214.art128", "LC214.art422")

_CORRECTION_KEYS = {"id", "versao", "efeitos_desde", "efeitos_ate", "fundamento"}


class BuildError(Exception):
    """Motivos para não gravar nada. Cada item é uma linha do relatório."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Correction:
    id: str
    versao: str
    efeitos_desde: date | None
    efeitos_ate: date | None
    fundamento: str


@dataclass
class BuildResult:
    text: str  # conteúdo de dispositivos.json
    report: list[str] = field(default_factory=list)


def _as_date(value: object, where: str, errors: list[str]) -> date | None:
    """YAML devolve `date` para 2027-01-01 sem aspas e `str` com aspas: aceita os dois."""
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    errors.append(f"{where}: data inválida {value!r} (use AAAA-MM-DD ou null)")
    return None


def load_corrections(text: str) -> list[Correction]:
    """Lê o YAML de correções. Junta todos os problemas antes de falhar."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict) or not isinstance(data.get("correcoes", []), list):
        raise BuildError(["efeitos_correcoes.yaml: esperado 'correcoes:' com uma lista"])
    errors: list[str] = []
    corrections: list[Correction] = []
    seen: set[tuple[str, str]] = set()
    for n, item in enumerate(data.get("correcoes") or [], start=1):
        where = f"correção {n}"
        if not isinstance(item, dict):
            errors.append(f"{where}: esperado um mapa com id, versao, efeitos_desde, efeitos_ate, fundamento")
            continue
        unknown = sorted(set(item) - _CORRECTION_KEYS)
        if unknown:
            errors.append(f"{where}: campo desconhecido {', '.join(unknown)}")
        rid, versao = item.get("id"), item.get("versao")
        if not isinstance(rid, str) or not isinstance(versao, str):
            errors.append(f"{where}: 'id' e 'versao' são obrigatórios")
            continue
        fundamento = item.get("fundamento")
        if not isinstance(fundamento, str) or not fundamento.strip():
            errors.append(f"{where} ({rid}, {versao}): 'fundamento' é obrigatório")
        desde = _as_date(item.get("efeitos_desde"), where, errors)
        ate = _as_date(item.get("efeitos_ate"), where, errors)
        if desde and ate and ate < desde:
            errors.append(f"{where} ({rid}, {versao}): efeitos_ate antes de efeitos_desde")
        if (rid, versao) in seen:
            errors.append(f"{where} ({rid}, {versao}): correção duplicada")
        seen.add((rid, versao))
        corrections.append(Correction(rid, versao, desde, ate, str(fundamento or "").strip()))
    if errors:
        raise BuildError(errors)
    return corrections


def apply_corrections(
    by_version: dict[tuple[str, str], Effects], corrections: list[Correction]
) -> dict[tuple[str, str], Effects]:
    """Correção vence o automático. Correção para versão inexistente é erro."""
    errors = [f"correção para versão inexistente: {c.id} ({c.versao})" for c in corrections if (c.id, c.versao) not in by_version]
    if errors:
        raise BuildError(errors)
    out = dict(by_version)
    for c in corrections:
        out[(c.id, c.versao)] = Effects(
            vigor_desde=c.efeitos_desde,
            efeitos_desde=c.efeitos_desde,
            efeitos_ate=c.efeitos_ate,
            fundamento=c.fundamento,
            metodo="correcao",
            fundamento_ate=c.fundamento if c.efeitos_ate else None,
        )
    return out


def check_minimum(records: list[Record]) -> list[str]:
    """Estrutura mínima esperada da EC: se faltar, o parser perdeu algo grande."""
    ids = {r.id for r in records}
    errors = [f"estrutura mínima ausente: {rid}" for rid in MINIMUM_IDS if rid not in ids]
    errors += [f"artigo da EC ausente: EC132.art{n}" for n in EC_ARTICLES if f"EC132.art{n}" not in ids]
    return errors


def check_lc_minimum(records: list[Record]) -> list[str]:
    """Estrutura mínima esperada da LC 214."""
    ids = {r.id for r in records}
    return [f"estrutura mínima ausente: {rid}" for rid in LC_MINIMUM_IDS if rid not in ids]


def _version_key(versao: str) -> tuple[str, int]:
    """'EC132.art11' → ('EC132', 11); 'LC214' → ('LC214', 0): ordena versões de normas diferentes."""
    norma, _, article = versao.partition(".art")
    return norma, int(article or 0)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def render(records: list[Record], effects: dict[tuple[str, str], Effects], metas: dict[str, dict]) -> str:
    """JSON determinístico: cabeçalho `fontes` + registros ordenados por (id, versão).

    `metas`: nome da fonte → conteúdo do `.meta.json`, na ordem do cabeçalho.
    """
    ordered = sorted(records, key=lambda r: (r.id, _version_key(r.versao)))
    rows = []
    for r in ordered:
        e = effects[(r.id, r.versao)]
        rows.append({
            "id": r.id,
            "citacao": r.citacao,
            "norma": r.norma,
            "pai": r.pai,
            "versao": r.versao,
            "origem": r.origem,
            "alteracao": r.alteracao,
            "texto": r.texto,
            "vigor_desde": _iso(e.vigor_desde),
            "efeitos_desde": _iso(e.efeitos_desde),
            "efeitos_ate": _iso(e.efeitos_ate),
            "fundamento_efeitos": e.fundamento,
            "fundamento_ate": e.fundamento_ate,
            "metodo": e.metodo,
        })
    document = {
        "fontes": {
            name: {"url": meta["url"], "coletado_em": meta["coletado_em"], "sha256_html": meta["sha256"]}
            for name, meta in metas.items()
        },
        "dispositivos": rows,
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _load_source(raw_dir: Path, name: str) -> tuple[dict, str]:
    """(meta, html decodificado) de uma fonte, conferindo o sha256."""
    html_path, meta_path = paths_for(raw_dir, name)
    if not verify(raw_dir, name):
        raise BuildError([f"{html_path.name} ausente ou diferente do sha256 em {meta_path.name}"])
    return json.loads(meta_path.read_text(encoding="utf-8")), decode_html(html_path.read_bytes())


def build(raw_dir: Path, corrections_text: str) -> BuildResult:
    """Pipeline inteiro em memória. Levanta BuildError em vez de gravar algo errado."""
    ec_meta, ec_html = _load_source(raw_dir, "ec132-2023")
    lc_meta, lc_html = _load_source(raw_dir, "lc214-2025")

    ec = parse(ec_html)
    lc = parse_lc(lc_html, norma="LC214", scope=LC214_SCOPE)
    errors = list(ec.errors) + check_minimum(ec.records) + list(lc.errors) + check_lc_minimum(lc.records)
    if errors:
        raise BuildError(errors)
    ec_effects = effects_for(ec.records, find_publication_date(t for _, t in paragraphs(ec_html)))
    lc_texts = [p.text for p in lc_paragraphs(lc_html) if not p.struck and p.text]
    lc_effects = lc_effects_for(lc.records, lc_texts)

    records = ec.records + lc.records
    corrections = load_corrections(corrections_text)
    effects = apply_corrections({**ec_effects.by_version, **lc_effects.by_version}, corrections)

    methods = Counter(e.metodo for e in effects.values())
    indeterminate = sorted(f"{rid} ({versao})" for (rid, versao), e in effects.items() if e.metodo == "indeterminado")
    warnings = ec.warnings + ec_effects.warnings + lc.warnings + lc_effects.warnings
    report = [
        f"dispositivos: {len(records)} versões, {len({r.id for r in records})} ids",
        "por norma: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.norma for r in records).items())),
        "por método: " + ", ".join(f"{k} {v}" for k, v in sorted(methods.items())),
        f"correções aplicadas: {len(corrections)}",
        f"revogações (EC 132, art. 22): {len(ec_effects.revocations)}",
        f"LC 214: {len(lc.records)} registros, {lc.struck} parágrafos tachados descartados, vetados: {', '.join(lc.vetoed) or 'nenhum'}",
        f"indeterminados: {len(indeterminate)}",
        *[f"  - {i}" for i in indeterminate],
        f"avisos: {len(warnings)}",
        *[f"  - {w}" for w in warnings],
    ]
    metas = {"ec132-2023": ec_meta, "lc214-2025": lc_meta}
    return BuildResult(text=render(records, effects, metas), report=report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taxlaw.ingest.build")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="não grava; sai com 1 se o arquivo estiver desatualizado")
    args = parser.parse_args(argv)

    try:
        corrections_text = args.corrections.read_text(encoding="utf-8") if args.corrections.is_file() else ""
        result = build(args.raw_dir, corrections_text)
    except BuildError as exc:
        print("build abortado; nada foi gravado:", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("\n".join(result.report))
    current = args.output.read_text(encoding="utf-8") if args.output.is_file() else None
    if args.check:
        if current == result.text:
            print(f"{args.output.name} em dia")
            return 0
        print(f"{args.output.name} desatualizado: rode o build sem --check", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.text, encoding="utf-8")
    print(f"gravado: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: regenere o corpus.** `uv run python -m taxlaw.ingest.build`. Esperado no relatório: `dispositivos: 649 versões, 636 ids`, `por norma: ADCT 132, CF 196, EC132 159, LC214 162`, `por método: automatico 645, indeterminado 4`, `avisos: 0`. Depois, `uv run python -m taxlaw.ingest.build --check` → `dispositivos.json em dia`.

- [ ] **Step 7: rode e veja passar.** `uv run pytest -q` → 431 passed.

- [ ] **Step 8: nota do passo.** Crie `docs/steps/13b-lc214-efeitos-build.md`:

````markdown
# Passo 13b: efeitos do art. 544 e o corpus com duas fontes

## O que mudou

- **`ingest/lc_effects.py`** (novo) lê o art. 544 da LC 214 e calcula vigor e efeitos de cada registro da LC:
  - **vigor** = data de publicação (1ª nota "DOU de 16.1.2025");
  - **efeitos** = a data do inciso que alcança o artigo, ou o inciso VI ("demais dispositivos": 2026-01-01);
  - o inciso I ("primeiro dia do quarto mês subsequente") é calculado: 2025-05-01;
  - **travas, as mesmas da EC:**
    - um inciso não reconhecido bloqueia a regra dos demais;
    - um artigo citado com ressalva ("58, caput", "450, exceto os §§ 1º e 5º") ou em dois incisos fica `indeterminado`;
    - um dispositivo com redação dada ou incluído pela LC 227/2026 fica com vigor e efeitos nulos.
- **Build com duas fontes.** `ec132-2023` e `lc214-2025` conferem o próprio sha256, e o erro de qualquer uma aborta o build. O cabeçalho `fonte` virou **`fontes`**, chaveado pelo nome da fonte.
- **`corpus.py`:** `source_of(row)` deduz a fonte pelo prefixo da `versao`, e `coletado_em` é a coleta **mais antiga** entre as fontes.
- **`tools.py`:** o `fonte_url` vem da norma do dispositivo. O schema das ferramentas não mudou.
- **`corpus/dispositivos.json`:** 649 versões e 636 ids. As 487 linhas da EC são idênticas às de antes, e as 162 da LC vêm depois.
- **7 casos da LC conferidos à mão pelo usuário em 2026-11-09:** arts. 125, 127, II, 128, I, 126, § 6º, 142, II, 422, § 2º, e 419.

## Como rodar

```
uv run python -m taxlaw.ingest.build
uv run pytest tests/test_lc_effects.py tests/test_build.py tests/test_build_real.py -v
uv run python client/taxlaw_client.py obter LC214.art128.incI --data 2025-06-01
uv run python client/taxlaw_client.py buscar "cesta básica"
```

## O que observar

- **Vigor e efeitos se separam pela primeira vez.** O art. 128, I (serviços de educação, redução de 60%), está em vigor desde 2025-01-16, mas só produz efeitos a partir de 2026-01-01. Em 2025-06-01, a ferramenta responde "produz efeitos na data: não". É por isso que a spec manteve os dois campos desde o passo 05.
- **"Não sei" continua sendo resposta.** Os 4 dispositivos tocados pela LC 227 respondem `produz_efeitos_na_data: null`. A data deles está em outra lei, e o corpus não a inventa.
- **A LC usa as siglas que a EC não usa.** "IBS" e "CBS" sozinhos agora acham dispositivos, mas **só da LC**. A Constituição continua precisando da tabela "usuário diz → busque" da skill, e o teste da skill foi ajustado para dizer exatamente isso.
- **A busca já acha a LC sem recalibrar.** "cesta básica" traz a EC, art. 8º, e a LC, art. 125, entre os 3 primeiros; "redução de 30% advogados" traz o art. 127, II, em 1º. O limiar de 0,15 continuou separando as consultas do tema das de fora. A recalibração formal e a skill ficam para o 13c.

## Pergunta de previsão

O art. 544 escalona os efeitos por **artigo**. O art. 450 aparece com ressalva em dois incisos ("exceto os §§ 1º e 5º" no III; "§§ 1º e 5º" no IV): os parágrafos 1º e 5º seguem uma data, o resto do artigo segue outra. O parser marca o artigo inteiro como `indeterminado`. O que seria preciso para acertar a data parágrafo por parágrafo, e por que vale (ou não) a pena fazer isso agora?
````

- [ ] **Step 9: commit.** `git add src/taxlaw/ingest/build.py src/taxlaw/corpus.py src/taxlaw/tools.py corpus/dispositivos.json tests/test_build.py tests/test_build_real.py tests/test_search.py tests/test_tools.py tests/test_tools_real.py tests/test_skill.py docs/steps/13b-lc214-efeitos-build.md && git commit -m "feat(step-13b): corpus com EC 132 e LC 214 (cabeçalho fontes)"`

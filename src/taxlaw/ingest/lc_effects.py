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

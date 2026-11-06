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

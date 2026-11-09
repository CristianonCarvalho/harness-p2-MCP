"""HTML de uma lei complementar no Planalto → registros (puro: sem rede, sem relógio).

Diferente da EC 132 (`structure.py`), que cita dispositivos da CF entre aspas,
aqui o texto é a própria lei, e a página é a **versão compilada**: as
alterações posteriores (ex.: LC 227/2026) já estão aplicadas, e a redação
antiga continua na página, tachada (spec do passo 13, seção 2):

- a redação antiga vem inteira dentro de um elemento com
  `text-decoration:line-through` (ou `<strike>`/`<s>`/`<del>`), logo antes da
  nova. Parágrafo inteiramente tachado é descartado; parágrafo **parcialmente**
  tachado é erro, porque não dá para saber qual é o texto vigente;
- a redação nova termina com uma marca "(Redação dada pela Lei Complementar nº
  227, de 2026)" ou "(Incluído pela ...)". A marca vira `alteracao`/`origem` e
  sai do `texto`;
- títulos (LIVRO, TÍTULO, CAPÍTULO, Seção, Subseção) e o nome que vem no
  parágrafo seguinte não viram registro;
- dispositivo "(VETADO)" não tem texto normativo: não vira registro, só é
  contado.

Só os artigos do escopo geram registros (a LC 214 tem mais de 500 artigos;
o passo 13 traz alguns capítulos). Artigo do escopo ausente é erro. Um mesmo
id duas vezes também é erro: seria a redação antiga que escapou do tachado.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser

from taxlaw.ingest.structure import Record, _Context, _label

# Elementos que não fecham (não entram na pilha de estilos).
_VOID = frozenset({"br", "img", "hr", "meta", "link", "input", "wbr"})
_STRIKE_TAGS = frozenset({"strike", "s", "del"})

# Marcas de alteração no fim do parágrafo. Podem vir várias seguidas, e o
# Planalto às vezes deixa o texto solto de um link ("Vigência", "Produção de
# efeitos") colado no fim.
_MARK = re.compile(r"\((Redação dada|Incluíd[oa]|Promulgação partes vetadas|Vide|Vigência|Produção de efeitos)[^()]*\)\s*$")
_LOOSE_LINK = re.compile(r"\s*(Vigência|Produção de efeitos)\s*$")
_LC_AMENDMENT = re.compile(r"Lei Complementar nº (\d+), de (\d{4})")
_HEADING = re.compile(r"^(LIVRO|TÍTULO|CAPÍTULO|Seção|Subseção)\s+[IVXLCDM]+(?:-[A-Z])?\b", re.IGNORECASE)
_VETOED = re.compile(r"\(VETADO\)[.;]?$")


# Escopo do passo 13 (spec 2026-11-09, seção 3): cesta básica (art. 125),
# regimes diferenciados e reduções de 30% e 60% (arts. 126 a 142) e alíquotas
# do Imposto Seletivo (arts. 419 a 423).
LC214_SCOPE = frozenset(f"art{n}" for n in [*range(125, 143), *range(419, 424)])


@dataclass(frozen=True)
class LcParagraph:
    text: str  # texto limpo, sem a parte tachada
    struck: bool  # o parágrafo inteiro estava tachado
    partly_struck: bool  # parte tachada, parte não


class _LcCollector(HTMLParser):
    """Junta o texto de cada <p>, separando o que está tachado do que não está."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[LcParagraph] = []
        self._stack: list[tuple[str, bool]] = []  # (tag, este elemento tacha?)
        self._plain: list[str] | None = None
        self._struck: list[str] | None = None

    def _striking(self) -> bool:
        return any(strikes for _, strikes in self._stack)

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._close()
            # <p> sem </p>: o que estava aberto no parágrafo anterior (inclusive
            # um tachado) termina aqui, senão vazaria para este.
            for i in range(len(self._stack) - 1, -1, -1):
                if self._stack[i][0] == "p":
                    del self._stack[i:]
                    break
            self._plain, self._struck = [], []
        if tag == "br" and self._plain is not None:
            (self._struck if self._striking() else self._plain).append(" ")
        if tag in _VOID:
            return
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        self._stack.append((tag, tag in _STRIKE_TAGS or "text-decoration:line-through" in style))

    def handle_endtag(self, tag):
        # HTML do FrontPage nem sempre fecha tudo: desempilha até a tag que fecha.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if tag == "p":
            self._close()

    def handle_data(self, data):
        if self._plain is not None:
            (self._struck if self._striking() else self._plain).append(data)

    def _close(self) -> None:
        if self._plain is None:
            return
        plain = _clean("".join(self._plain))
        struck = _clean("".join(self._struck or []))
        if plain or struck:
            self.paragraphs.append(LcParagraph(text=plain, struck=bool(struck) and not plain, partly_struck=bool(struck) and bool(plain)))
        self._plain, self._struck = None, None

    def close(self):
        super().close()
        self._close()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def lc_paragraphs(html: str) -> list[LcParagraph]:
    """Parágrafos não vazios, em ordem, com a marcação de tachado."""
    collector = _LcCollector()
    collector.feed(html)
    collector.close()
    return collector.paragraphs


@dataclass
class LcParseResult:
    records: list[Record] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    struck: int = 0  # parágrafos de redação antiga descartados (no escopo)
    vetoed: list[str] = field(default_factory=list)  # ids vetados, sem registro


def _split_marks(text: str) -> tuple[str, list[str]]:
    """Separa as marcas de alteração do fim do texto. Devolve (texto, marcas)."""
    marks: list[str] = []
    while True:
        text = _LOOSE_LINK.sub("", text)
        m = _MARK.search(text)
        if not m:
            return text.strip(), marks
        marks.insert(0, m.group(0))
        text = text[: m.start()].rstrip()


def _amendment(marks: list[str], base: str) -> tuple[str, str, bool]:
    """(alteracao, origem, promulgado_depois_de_veto) a partir das marcas."""
    promulgated = any("Promulgação partes vetadas" in m for m in marks)
    for mark in marks:
        if m := _LC_AMENDMENT.search(mark):
            law = f"LC {m.group(1)}/{m.group(2)}"
            if mark.startswith("(Redação dada"):
                return "alterado", f"{base}, com redação dada pela {law}", promulgated
            if mark.startswith("(Incluíd"):
                return "incluido", f"{base}, incluído pela {law}", promulgated
    if promulgated:
        # A origem marca o caso; os efeitos (passo 13b) ficam indeterminados.
        return "original", f"{base}, parte promulgada após veto", True
    return "original", base, False


def _in_scope(article_id: str, norma: str, scope: set[str]) -> bool:
    return article_id.removeprefix(f"{norma}.") in scope


def parse_lc(html: str, *, norma: str, scope: Iterable[str]) -> LcParseResult:
    """Registros dos artigos do escopo (ex.: {"art125", "art126", ...}).

    `versao` é a própria norma (uma versão só: a redação atual compilada).
    """
    scope = set(scope)
    base = {"LC214": "LC 214/2025"}[norma]
    result = LcParseResult()
    ctx = _Context()
    current_article: str | None = None
    seen_articles: set[str] = set()
    seen_ids: set[str] = set()
    after_heading = False

    for paragraph in lc_paragraphs(html):
        text = paragraph.text
        if _HEADING.match(text):
            after_heading = True
            continue
        in_scope = current_article is not None and _in_scope(current_article, norma, scope)
        if paragraph.struck:
            result.struck += in_scope
            continue
        if after_heading:
            after_heading = False
            if _label(text, norma, _Context(art=ctx.art)) is None:
                continue  # nome do título/capítulo/seção
        text, marks = _split_marks(text)
        probe = _Context(art=ctx.art, par=ctx.par, inc=ctx.inc, ali=ctx.ali)
        labeled = _label(text, norma, probe)
        if labeled and labeled[2] is None:  # um artigo novo
            current_article = labeled[0]
            in_scope = _in_scope(current_article, norma, scope)
        if not in_scope:
            if labeled:
                ctx = probe
            continue
        if paragraph.partly_struck:
            result.errors.append(f"parágrafo parcialmente tachado em {current_article}: {text[:60]!r}")
            continue
        if labeled is None:
            result.warnings.append(f"parágrafo sem rótulo em {current_article}: {text[:60]!r}")
            continue
        ctx = probe
        rid, citacao, pai = labeled
        if rid.startswith(current_article) and pai is None:
            seen_articles.add(rid.removeprefix(f"{norma}."))
        if _VETOED.search(text) and len(text) < 40:
            result.vetoed.append(rid)
            continue
        if rid in seen_ids:
            result.errors.append(f"id repetido {rid}: redação antiga fora do tachado?")
            continue
        seen_ids.add(rid)
        alteracao, origem, promulgated = _amendment(marks, base)
        if promulgated:
            result.warnings.append(f"{rid}: promulgado depois de veto; efeitos ficam indeterminados")
        result.records.append(
            Record(id=rid, citacao=citacao, norma=norma, pai=pai, versao=norma, origem=origem, alteracao=alteracao, texto=text)
        )

    for missing in sorted(scope - seen_articles):
        result.errors.append(f"artigo do escopo não encontrado: {norma}.{missing}")
    return result

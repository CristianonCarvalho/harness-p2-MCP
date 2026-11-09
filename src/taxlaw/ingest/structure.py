"""HTML da EC 132 → registros de dispositivo (puro: sem rede, sem relógio).

Formato do Planalto (conferido no arquivo real, spec seção 3):
- cada dispositivo é um <p>; os artigos da EC têm âncora <a name="artN">;
- o caput do artigo da EC diz qual norma ele altera (CF ou ADCT);
- o texto citado da CF/ADCT vem entre aspas; o parágrafo que fecha o bloco
  termina com `" (NR)` (redação nova → "alterado") ou só com `"` (→ "incluido");
- linhas só de pontos marcam texto omitido: posicionam a hierarquia, mas não
  viram registro.

Um mesmo dispositivo citado em dois artigos da EC gera dois registros, um por
`versao` (spec seção 5). O que o parser não reconhece vai para `warnings`:
nunca é descartado em silêncio nem colado no dispositivo anterior.

`errors` é para o que torna o resultado errado, não só incompleto: uma âncora
<a name="artN"> cujo caput não foi reconhecido faria os filhos do art. N serem
registrados no artigo anterior, sem nenhum aviso (achado do passo 05). O build
aborta se houver erro.

O texto normativo termina em "Brasília, em <data>": o que vem depois
(assinaturas, aviso do DOU) não é norma e é ignorado sem aviso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

DEFAULT_ENCODING = "windows-1252"


@dataclass(frozen=True)
class Record:
    """Um dispositivo numa versão. Os campos de efeito chegam no passo 06."""

    id: str
    citacao: str
    norma: str  # "CF" | "ADCT" | "EC132"
    pai: str | None
    versao: str  # artigo da EC que traz este texto, ex.: "EC132.art3"
    origem: str  # ex.: "EC 132/2023, art. 3º"
    alteracao: str  # "incluido" | "alterado" | "original" (texto da própria EC)
    texto: str


@dataclass
class ParseResult:
    records: list[Record] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def decode_html(raw: bytes) -> str:
    """Decodifica pelo charset declarado no <meta>; sem declaração, windows-1252."""
    match = re.search(rb"charset=[\"']?([A-Za-z0-9_-]+)", raw[:4096])
    encoding = match.group(1).decode("ascii") if match else DEFAULT_ENCODING
    return raw.decode(encoding)


# ---------------------------------------------------------------- parágrafos


class _ParagraphCollector(HTMLParser):
    """Junta o texto de cada <p> e anota a âncora <a name="artN"> que houver nele."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # &quot; → ", &nbsp; → \xa0
        self.paragraphs: list[tuple[str | None, str]] = []
        self._parts: list[str] | None = None
        self._anchor: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._close()
            self._parts, self._anchor = [], None
        elif tag == "a" and self._parts is not None:
            name = dict(attrs).get("name")
            if name and re.fullmatch(r"art\d+", name):
                self._anchor = name
        elif tag == "br" and self._parts is not None:
            self._parts.append(" ")

    def handle_endtag(self, tag):
        if tag == "p":
            self._close()

    def handle_data(self, data):
        if self._parts is not None:
            self._parts.append(data)

    def _close(self) -> None:
        if self._parts is not None:
            text = re.sub(r"\s+", " ", "".join(self._parts).replace("\xa0", " ")).strip()
            if text:
                self.paragraphs.append((self._anchor, text))
        self._parts, self._anchor = None, None

    def close(self):
        super().close()
        self._close()


def paragraphs(html: str) -> list[tuple[str | None, str]]:
    """(âncora ou None, texto limpo) de cada <p> não vazio, em ordem."""
    collector = _ParagraphCollector()
    collector.feed(html)
    collector.close()
    return collector.paragraphs


# ------------------------------------------------------------------ rótulos

# O ponto depois do número pode vir colado no texto: o FrontPage gerou
# "Art. 12.Fica instituído..." (arts. 12 e 17 da EC no arquivo real).
_ART = re.compile(r"^Art\. (\d+)(?:º|o)?(-[A-Z])?(?:\.|(?=\s|$))")
_PAR = re.compile(r"^§ (\d+)(?:º|o)?(?=\s|\.|$)")
_PAR_UNICO = re.compile(r"^Parágrafo único\.?", re.IGNORECASE)
_INC = re.compile(r"^([IVXLCDM]+) ?[-–—](?=\s|\.|$)")
_ALI = re.compile(r"^([a-z])\)")
_ITEM = re.compile(r"^(\d+)\.(?=\s)")
_HEADING = re.compile(r"^(TÍTULO|CAPÍTULO|Seção|Subseção)\b", re.IGNORECASE)
_DOTS = re.compile(r"^[.…\s]*$")
_BLOCK_END = re.compile(r'"\s*(\(NR\))?\s*$')
_VIGENCIA = re.compile(r"\s*Vigência\s*$")
_END_OF_TEXT = re.compile(r"^Brasília, (em )?\d")


def _ordinal(n: int) -> str:
    """Convenção legislativa: ordinal de 1 a 9 (1º), cardinal a partir de 10."""
    return f"{n}º" if n < 10 else str(n)


@dataclass
class _Context:
    """Onde estamos na hierarquia: um id por nível (None = nível ainda não visto)."""

    art: tuple[str, str] | None = None  # (id, citação)
    par: tuple[str, str] | None = None
    inc: tuple[str, str] | None = None
    ali: tuple[str, str] | None = None

    def reset(self) -> None:
        self.art = self.par = self.inc = self.ali = None


def _label(text: str, norma: str, ctx: _Context) -> tuple[str, str, str | None] | None:
    """Reconhece o rótulo, atualiza o contexto e devolve (id, citação, pai).

    None se o parágrafo não começa com rótulo conhecido.
    """
    # LC214: passo 13 (lc_structure.py reaproveita estes rótulos).
    prefix = {"CF": "CF", "ADCT": "ADCT", "EC132": "EC 132/2023", "LC214": "LC 214/2025"}[norma]
    if m := _ART.match(text):
        number, suffix = int(m.group(1)), m.group(2) or ""
        ctx.reset()
        ctx.art = (f"{norma}.art{number}{suffix}", f"{prefix}, art. {_ordinal(number)}{suffix}")
        return ctx.art[0], ctx.art[1], None
    if ctx.art is None:
        return None
    if m := _PAR.match(text):
        number = int(m.group(1))
        ctx.par, ctx.inc, ctx.ali = (f"{ctx.art[0]}.par{number}", f"{ctx.art[1]}, § {_ordinal(number)}"), None, None
        return ctx.par[0], ctx.par[1], ctx.art[0]
    if _PAR_UNICO.match(text):
        ctx.par, ctx.inc, ctx.ali = (f"{ctx.art[0]}.parunico", f"{ctx.art[1]}, parágrafo único"), None, None
        return ctx.par[0], ctx.par[1], ctx.art[0]
    if m := _INC.match(text):
        parent = ctx.par or ctx.art
        ctx.inc, ctx.ali = (f"{parent[0]}.inc{m.group(1)}", f"{parent[1]}, {m.group(1)}"), None
        return ctx.inc[0], ctx.inc[1], parent[0]
    if (m := _ALI.match(text)) and ctx.inc is not None:
        ctx.ali = (f"{ctx.inc[0]}.ali{m.group(1)}", f"{ctx.inc[1]}, {m.group(1)}")
        return ctx.ali[0], ctx.ali[1], ctx.inc[0]
    if (m := _ITEM.match(text)) and ctx.ali is not None:
        return f"{ctx.ali[0]}.item{m.group(1)}", f"{ctx.ali[1]}, item {m.group(1)}", ctx.ali[0]
    return None


def _is_omitted(text: str) -> bool:
    """Só pontos, ou rótulo seguido só de pontos ("I - ....", "Art. 105. ....")."""
    rest = re.sub(r"^(Art\. \d+(?:º|o)?(?:-[A-Z])?\.?|§ \d+(?:º|o)?|Parágrafo único\.?|"
                  r"[IVXLCDM]+ ?[-–—]|[a-z]\)|\d+\.)", "", text, flags=re.IGNORECASE)
    return bool(_DOTS.match(rest)) and "." in text


# -------------------------------------------------------------------- parse


def parse(html: str) -> ParseResult:
    """Percorre os parágrafos e monta os registros de todas as versões."""
    result = ParseResult()
    seen: set[tuple[str, str]] = set()
    ec_article: int | None = None  # artigo da EC em que estamos
    target: str | None = None  # norma alterada pelo artigo da EC atual
    in_block = False
    alteracao = "incluido"
    block_paragraphs: list[str] = []
    ec_ctx, block_ctx = _Context(), _Context()

    def add(record: Record) -> None:
        key = (record.id, record.versao)
        if key in seen:
            result.warnings.append(f"duplicado na mesma versão: {record.id} ({record.versao})")
            return
        seen.add(key)
        result.records.append(record)

    def flush_block() -> None:
        """Fecha o bloco citado: agora sabemos se é (NR) e criamos os registros."""
        assert ec_article is not None
        versao, origem = f"EC132.art{ec_article}", f"EC 132/2023, art. {_ordinal(ec_article)}"
        if target is None:
            result.warnings.append(f"bloco citado sem norma identificada no art. {ec_article} da EC")
            return
        block_ctx.reset()
        after_heading = False
        for text in block_paragraphs:
            if _HEADING.match(text):
                block_ctx.reset()
                after_heading = True
                continue
            omitted = _is_omitted(text)
            label = _label(text, target, block_ctx)
            if omitted:
                after_heading = False
                continue  # posiciona o contexto (feito em _label), sem registro
            if label is None:
                if after_heading:  # nome da seção, logo depois de "Seção V-A"
                    after_heading = False
                    continue
                result.warnings.append(f"parágrafo sem rótulo no bloco do art. {ec_article} da EC: {text[:60]}")
                continue
            after_heading = False
            rid, citacao, pai = label
            add(Record(rid, citacao, target, pai, versao, origem, alteracao, text))

    for anchor, text in paragraphs(html):
        if in_block:
            closes = _BLOCK_END.search(text)
            if closes:
                alteracao = "alterado" if closes.group(1) else "incluido"
                text = text[: closes.start()].rstrip()
            block_paragraphs.append(text)
            if closes:
                flush_block()
                in_block, block_paragraphs = False, []
            continue

        if ec_article is not None and text.startswith('"'):
            in_block, block_paragraphs = True, []
            text = text[1:].lstrip()
            closes = _BLOCK_END.search(text)
            if closes:  # bloco de um parágrafo só
                alteracao = "alterado" if closes.group(1) else "incluido"
                block_paragraphs.append(text[: closes.start()].rstrip())
                flush_block()
                in_block, block_paragraphs = False, []
            else:
                block_paragraphs.append(text)
            continue

        text = _VIGENCIA.sub("", text)
        if ec_article is not None and _END_OF_TEXT.match(text):
            break  # fim do texto normativo: assinaturas e aviso do DOU não são norma
        m = _ART.match(text)
        if anchor is not None:
            # A âncora prova que ali começa o art. N da EC. Se o caput não bate,
            # seguir em frente registraria os filhos dele no artigo anterior.
            if m is None:
                result.errors.append(f"âncora {anchor} sem caput de artigo reconhecido: {text[:60]}")
                continue
            if int(m.group(1)) != int(anchor[3:]):
                result.errors.append(f"âncora {anchor} com caput do art. {m.group(1)}: {text[:60]}")
                continue
        if anchor is not None and m:
            ec_article = int(m.group(1))
            if "Ato das Disposições Constitucionais Transitórias" in text:
                target = "ADCT"
            elif "Constituição Federal" in text:
                target = "CF"
            else:
                target = None
        if ec_article is None:
            continue  # cabeçalho, ementa e preâmbulo: antes do art. 1º
        label = _label(text, "EC132", ec_ctx)
        if label is None:
            result.warnings.append(f"parágrafo fora de bloco sem rótulo: {text[:60]}")
            continue
        rid, citacao, pai = label
        add(Record(rid, citacao, "EC132", pai, f"EC132.art{ec_article}",
                   f"EC 132/2023, art. {_ordinal(ec_article)}", "original", text))

    if in_block:
        result.warnings.append(f"bloco citado aberto e não fechado no art. {ec_article} da EC")
    return result

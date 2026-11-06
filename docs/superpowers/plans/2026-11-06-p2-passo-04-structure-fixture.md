# P2, passo 04: structure com fixture sintética (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-06-p2-passo-04-structure-fixture.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um parser `taxlaw.ingest.structure`, puro, que transforma o HTML da EC 132 em registros de dispositivo, com hierarquia (`pai`), `alteracao` pela marca de fechamento e um registro por versão, testado contra uma fixture sintética no formato do Planalto.

**Architecture:** `HTMLParser` da biblioteca padrão junta o texto de cada `<p>` e a âncora `<a name="artN">`. Um laço percorre os parágrafos: o caput de cada artigo da EC define a norma alterada (CF ou ADCT), os blocos entre aspas são acumulados até o fechamento (`" (NR)` → `alterado`; só `"` → `incluido`), e os rótulos (`Art.`, `§`, `Parágrafo único`, inciso, alínea, item) atualizam um contexto de hierarquia. Linhas de pontos só posicionam o contexto. O que não é reconhecido vira `warnings`, nunca é descartado em silêncio.

**Tech Stack:** Python 3.13 (biblioteca padrão: `html.parser`, `re`, `dataclasses`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seções 3, 5 e 9, atualizadas em 2026-11-06: regra de `alteracao`, versões, ancestral omitido)

## Global Constraints

- Só biblioteca padrão; nenhuma dependência nova no `pyproject.toml`.
- `structure.py` é puro: não lê arquivo, não acessa rede, não usa relógio. Recebe `str` (ou `bytes` em `decode_html`).
- Testes 100% offline; nenhum teste depende do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes. Os testes deste passo **não** leem `corpus/raw/` (o arquivo real é o passo 05).
- A fixture é sintética: texto normativo inventado, com o formato real.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `pyproject.toml`, `corpus/`, nem os módulos existentes (`guard.py`, `synthetic_ids.py`, `ingest/fetch.py`, `ingest/__init__.py`).
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (conferidos em 2026-11-06 no arquivo real `corpus/raw/ec132-2023.html`)

- Dispositivos em `<p class="dou-paragraph" style="...">`, com `<font>`, `<span>`, `<strong>` e `<a href>` só de formatação; texto citado entre `&quot;`.
- Artigos da EC com âncora `<a name="art1">` a `art23`; os arts. 3º, 4º e 5º têm um link "Vigência" no fim do caput.
- Blocos citados: 39 fecham com `" (NR)` (já existiam → `alterado`) e 19 só com `"` (novos → `incluido`); "(AC)" não aparece.
- Linhas só de pontos, ou rótulo seguido de pontos (`§ 1º .....`), marcam texto omitido.
- Títulos dentro de blocos (`Seção V-A`) seguidos do nome da seção (`Do Imposto sobre Bens e Serviços`).
- O mesmo dispositivo em mais de um artigo da EC: 9 casos (ex.: `CF.art156-A.par1.incIX` nos arts. 1º, 3º e 4º).
- Formato de id: `CF.art156-A.par1.incIX`, `CF.art149-B.parunico`, `CF.art149-B.incII.alia`, `ADCT.art125`, `EC132.art10.par1`. Citação: `CF, art. 156-A, § 1º, IX`; ordinal de 1 a 9 (`art. 1º`, `§ 4º`), cardinal a partir de 10 (`art. 10`).

## Review Focus

- Bloco que não fecha, bloco sem norma identificável e parágrafo sem rótulo dentro de bloco viram `warnings` com mensagem exata; o texto solto nunca é colado ao dispositivo anterior (testes `test_unclosed_block_is_a_warning`, `test_block_without_identified_norma_is_a_warning`, `test_unlabeled_paragraph_inside_block_is_a_warning_not_glued`).
- O mesmo `id` em dois artigos da EC gera dois registros, cada um com seu texto; o mesmo (`id`, `versao`) duas vezes gera aviso e fica a primeira (testes `test_two_versions_keep_their_own_text` e `test_duplicate_in_same_version_is_a_warning_and_first_wins`).
- Linhas de pontos e títulos de seção não viram registro, mas a linha de pontos posiciona a hierarquia: `CF.art43.par4` tem `pai` `CF.art43` (testes `test_omitted_lines_and_headings_are_not_records` e `test_records_ids_hierarchy_versions_and_alteracao`).
- Entidades (`&quot;`, `&nbsp;`), tags de formatação e o link "Vigência" não sobram no texto (testes `test_texts_are_clean`, `test_vigencia_link_is_removed_from_ec_caput`, `test_paragraphs_capture_anchor_and_clean_text`).
- Charset: windows-1252 declarado, UTF-8 declarado e ausência de declaração (teste `test_decode_html_follows_declared_charset_and_defaults_to_windows_1252`).

---

### Task 1: Parser structure, fixture sintética e nota do passo

**Files:**
- Create: `src/taxlaw/ingest/structure.py`
- Test: `tests/test_structure.py`
- Create: `docs/steps/04-structure-fixture.md`

**Interfaces:**
- Consumes: nada dos módulos anteriores (o `fetch` grava os bytes; quem lê o arquivo é o build, no passo 07).
- Produces (usados pelos passos 05 a 07): `Record(id: str, citacao: str, norma: str, pai: str | None, versao: str, origem: str, alteracao: str, texto: str)` (dataclass congelada; `norma` em `"CF" | "ADCT" | "EC132"`; `alteracao` em `"incluido" | "alterado" | "original"`); `ParseResult(records: list[Record], warnings: list[str])`; `decode_html(raw: bytes) -> str`; `paragraphs(html: str) -> list[tuple[str | None, str]]`; `parse(html: str) -> ParseResult`.

- [ ] **Step 1: testes que falham.** Crie `tests/test_structure.py`:

```python
"""Testes do structure (passo 04) contra uma fixture sintética.

A fixture imita o formato real do Planalto (spec seção 3): <p class=
"dou-paragraph"> com style enorme e <font>, âncora <a name="artN">, &quot;,
blocos fechados com (NR) ou só com a aspa, linhas de pontos, título de seção,
link "Vigência" e o mesmo dispositivo em dois artigos da EC. Todo o texto
normativo é inventado: não é a EC 132 real.
"""

import pytest

from taxlaw.ingest.structure import Record, decode_html, paragraphs, parse

STYLE = 'class="dou-paragraph" style="box-sizing: border-box; text-align: justify; text-indent: 38px"'


def p(inner: str) -> str:
    """Um parágrafo no formato do Planalto, com <font> em volta, como no arquivo real."""
    return f'<p {STYLE}><font face="Arial" size="2">{inner}</font></p>\n'


FIXTURE = (
    '<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252"></head><body>\n'
    '<p align="center"><font color="#800000">EMENDA CONSTITUCIONAL Nº 132, DE 20 DE DEZEMBRO DE 2023</font></p>\n'
    + p('Texto sintético de preâmbulo, antes do art. 1º.')
    + p('<a name="art1"></a>Art. 1º A Constituição Federal passa a vigorar com as seguintes alterações:')
    + p('&quot;Art. 43. ..................................................')
    + p('...................................................................')
    + p('<a href="../../Constituicao.htm#art43§4">§ 4º</a> Texto sintético do parágrafo quarto.&quot; (NR)')
    + p('&quot;Art. 149-B. Texto sintético de artigo novo:')
    + p('I - primeiro inciso sintético;')
    + p('II - segundo inciso sintético, com alíneas:')
    + p('a) alínea sintética;')
    + p('b) outra alínea sintética.')
    + p('Parágrafo único. Parágrafo único sintético.&quot;')
    + p('&quot;Seção V-A')
    + p('Do Imposto Sintético')
    + p('<a href="../../Constituicao.htm#art156a">Art. 156-A.</a> Caput sintético do imposto.')
    + p('§ 1º O imposto do<strong class="dou-strong"> caput </strong>atenderá ao seguinte:')
    + p('IX - redação original sintética do inciso nove;')
    + p('X - inciso&nbsp;dez sintético.&quot;')
    + p('<a name="art2"></a>Art. 2º O <a href="../../Constituicao.htm#adct">Ato das Disposições Constitucionais Transitórias</a> passa a vigorar com as seguintes alterações:')
    + p('&quot;Art. 125. Em 2026, texto sintético de transição.&quot;')
    + p('<a name="art3"></a>Art. 3º A Constituição Federal passa a vigorar com as seguintes alterações: <a href="#art23">Vigência</a>')
    + p('&quot;Art. 156-A. ...............................................')
    + p('§ 1º ............................................................')
    + p('...................................................................')
    + p('IX - redação nova sintética do inciso nove, a partir de 2027;')
    + p('...................................................................&quot; (NR)')
    + p('<a name="art10"></a>Art. 10. Texto sintético de artigo autônomo da EC:')
    + p('I - inciso autônomo sintético;')
    + p('§ 1º Parágrafo sintético do artigo dez.')
    + p('<a name="art23"></a>Art. 23. Esta Emenda entra em vigor na data de sua publicação (texto sintético).')
    + '<p align="center">Brasília, em 20 de dezembro de 2023</p>\n'
    '</body></html>\n'
)

# (id, norma, pai, versao, alteracao), na ordem em que o parser gera.
EXPECTED = [
    ("EC132.art1", "EC132", None, "EC132.art1", "original"),
    ("CF.art43.par4", "CF", "CF.art43", "EC132.art1", "alterado"),
    ("CF.art149-B", "CF", None, "EC132.art1", "incluido"),
    ("CF.art149-B.incI", "CF", "CF.art149-B", "EC132.art1", "incluido"),
    ("CF.art149-B.incII", "CF", "CF.art149-B", "EC132.art1", "incluido"),
    ("CF.art149-B.incII.alia", "CF", "CF.art149-B.incII", "EC132.art1", "incluido"),
    ("CF.art149-B.incII.alib", "CF", "CF.art149-B.incII", "EC132.art1", "incluido"),
    ("CF.art149-B.parunico", "CF", "CF.art149-B", "EC132.art1", "incluido"),
    ("CF.art156-A", "CF", None, "EC132.art1", "incluido"),
    ("CF.art156-A.par1", "CF", "CF.art156-A", "EC132.art1", "incluido"),
    ("CF.art156-A.par1.incIX", "CF", "CF.art156-A.par1", "EC132.art1", "incluido"),
    ("CF.art156-A.par1.incX", "CF", "CF.art156-A.par1", "EC132.art1", "incluido"),
    ("EC132.art2", "EC132", None, "EC132.art2", "original"),
    ("ADCT.art125", "ADCT", None, "EC132.art2", "incluido"),
    ("EC132.art3", "EC132", None, "EC132.art3", "original"),
    ("CF.art156-A.par1.incIX", "CF", "CF.art156-A.par1", "EC132.art3", "alterado"),
    ("EC132.art10", "EC132", None, "EC132.art10", "original"),
    ("EC132.art10.incI", "EC132", "EC132.art10", "EC132.art10", "original"),
    ("EC132.art10.par1", "EC132", "EC132.art10", "EC132.art10", "original"),
    ("EC132.art23", "EC132", None, "EC132.art23", "original"),
]


@pytest.fixture(scope="module")
def result():
    return parse(FIXTURE)


def by_key(result, rid: str, versao: str) -> Record:
    return next(r for r in result.records if r.id == rid and r.versao == versao)


def test_records_ids_hierarchy_versions_and_alteracao(result):
    got = [(r.id, r.norma, r.pai, r.versao, r.alteracao) for r in result.records]
    assert got == EXPECTED


def test_citations(result):
    assert by_key(result, "CF.art43.par4", "EC132.art1").citacao == "CF, art. 43, § 4º"
    assert by_key(result, "CF.art149-B.incII.alib", "EC132.art1").citacao == "CF, art. 149-B, II, b"
    assert by_key(result, "CF.art149-B.parunico", "EC132.art1").citacao == "CF, art. 149-B, parágrafo único"
    assert by_key(result, "CF.art156-A.par1.incIX", "EC132.art3").citacao == "CF, art. 156-A, § 1º, IX"
    assert by_key(result, "ADCT.art125", "EC132.art2").citacao == "ADCT, art. 125"
    assert by_key(result, "EC132.art1", "EC132.art1").citacao == "EC 132/2023, art. 1º"
    assert by_key(result, "EC132.art10", "EC132.art10").citacao == "EC 132/2023, art. 10"


def test_origem_uses_legislative_ordinal(result):
    assert by_key(result, "CF.art156-A", "EC132.art1").origem == "EC 132/2023, art. 1º"
    assert by_key(result, "EC132.art10.par1", "EC132.art10").origem == "EC 132/2023, art. 10"


def test_two_versions_keep_their_own_text(result):
    first = by_key(result, "CF.art156-A.par1.incIX", "EC132.art1")
    second = by_key(result, "CF.art156-A.par1.incIX", "EC132.art3")
    assert first.texto == "IX - redação original sintética do inciso nove;"
    assert second.texto == "IX - redação nova sintética do inciso nove, a partir de 2027;"


def test_texts_are_clean(result):
    # sem aspas de bloco, sem (NR), sem tags, entidades e espaços resolvidos
    assert by_key(result, "CF.art43.par4", "EC132.art1").texto == "§ 4º Texto sintético do parágrafo quarto."
    assert by_key(result, "CF.art156-A.par1", "EC132.art1").texto == "§ 1º O imposto do caput atenderá ao seguinte:"
    assert by_key(result, "CF.art156-A.par1.incX", "EC132.art1").texto == "X - inciso dez sintético."
    assert by_key(result, "CF.art149-B", "EC132.art1").texto == "Art. 149-B. Texto sintético de artigo novo:"


def test_vigencia_link_is_removed_from_ec_caput(result):
    texto = by_key(result, "EC132.art3", "EC132.art3").texto
    assert texto == "Art. 3º A Constituição Federal passa a vigorar com as seguintes alterações:"


def test_omitted_lines_and_headings_are_not_records(result):
    textos = [r.texto for r in result.records]
    assert not any(set(t) <= set(". ") for t in textos)
    assert not any(t.startswith(("Seção", "Do Imposto")) for t in textos)
    assert not any(r.id == "CF.art43" for r in result.records)


def test_preamble_is_ignored_and_signature_is_reported(result):
    assert not any("preâmbulo" in r.texto for r in result.records)
    assert result.warnings == ["parágrafo fora de bloco sem rótulo: Brasília, em 20 de dezembro de 2023"]


def test_parse_is_deterministic(result):
    assert parse(FIXTURE) == result


def ec_article(inner_paragraphs: str, caput: str = "A Constituição Federal passa a vigorar com as seguintes alterações:") -> str:
    return p(f'<a name="art1"></a>Art. 1º {caput}') + inner_paragraphs


def test_unlabeled_paragraph_inside_block_is_a_warning_not_glued():
    html = ec_article(p("&quot;Art. 50. Caput sintético.") + p("texto solto sem rótulo") + p("I - inciso.&quot; (NR)"))
    result = parse(html)
    assert [r.id for r in result.records] == ["EC132.art1", "CF.art50", "CF.art50.incI"]
    assert result.warnings == ["parágrafo sem rótulo no bloco do art. 1 da EC: texto solto sem rótulo"]
    assert all("solto" not in r.texto for r in result.records)


def test_unclosed_block_is_a_warning():
    result = parse(ec_article(p("&quot;Art. 50. Caput sintético sem fechamento.")))
    assert result.warnings == ["bloco citado aberto e não fechado no art. 1 da EC"]


def test_block_without_identified_norma_is_a_warning():
    html = ec_article(p("&quot;Art. 50. Caput sintético.&quot; (NR)"), caput="A Lei sintética passa a vigorar com:")
    result = parse(html)
    assert [r.id for r in result.records] == ["EC132.art1"]
    assert result.warnings == ["bloco citado sem norma identificada no art. 1 da EC"]


def test_duplicate_in_same_version_is_a_warning_and_first_wins():
    html = ec_article(p("&quot;Art. 50. Primeira redação.&quot; (NR)") + p("&quot;Art. 50. Segunda redação.&quot; (NR)"))
    result = parse(html)
    assert [r.texto for r in result.records if r.id == "CF.art50"] == ["Art. 50. Primeira redação."]
    assert result.warnings == ["duplicado na mesma versão: CF.art50 (EC132.art1)"]


def test_decode_html_follows_declared_charset_and_defaults_to_windows_1252():
    text = "<p>Constituição</p>"
    assert decode_html(('<meta charset="utf-8">' + text).encode("utf-8")).endswith(text)
    assert decode_html(('<meta content="text/html; charset=windows-1252">' + text).encode("windows-1252")).endswith(text)
    assert decode_html(text.encode("windows-1252")) == text


def test_paragraphs_capture_anchor_and_clean_text():
    got = paragraphs(p('<a name="art7"></a>Art. 7º Texto&nbsp;com &quot;aspas&quot; e <strong>negrito</strong>.'))
    assert got == [("art7", 'Art. 7º Texto com "aspas" e negrito.')]
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_structure.py -v` → erro de import (`taxlaw.ingest.structure` não existe).

- [ ] **Step 3: implemente.** Crie `src/taxlaw/ingest/structure.py`:

```python
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

_ART = re.compile(r"^Art\. (\d+)(?:º|o)?(-[A-Z])?\.?(?=\s|$)")
_PAR = re.compile(r"^§ (\d+)(?:º|o)?(?=\s|\.|$)")
_PAR_UNICO = re.compile(r"^Parágrafo único\.?", re.IGNORECASE)
_INC = re.compile(r"^([IVXLCDM]+) ?[-–—](?=\s|\.|$)")
_ALI = re.compile(r"^([a-z])\)")
_ITEM = re.compile(r"^(\d+)\.(?=\s)")
_HEADING = re.compile(r"^(TÍTULO|CAPÍTULO|Seção|Subseção)\b", re.IGNORECASE)
_DOTS = re.compile(r"^[.…\s]*$")
_BLOCK_END = re.compile(r'"\s*(\(NR\))?\s*$')
_VIGENCIA = re.compile(r"\s*Vigência\s*$")


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
    prefix = {"CF": "CF", "ADCT": "ADCT", "EC132": "EC 132/2023"}[norma]
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
        m = _ART.match(text)
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
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_structure.py -v` → 15 passed.

- [ ] **Step 5: nota do passo.** Crie `docs/steps/04-structure-fixture.md`:

```markdown
# Passo 04: structure com fixture sintética

## O que mudou

- `src/taxlaw/ingest/structure.py`: transforma o HTML da EC em registros `Record(id, citacao, norma, pai, versao, origem, alteracao, texto)`.
  - `decode_html` lê o charset declarado; sem declaração, usa windows-1252.
  - `paragraphs` extrai o texto limpo de cada `<p>` e a âncora `artN`, se houver.
  - `parse` monta os registros e uma lista de `warnings`.
- Testado só contra uma **fixture sintética** que imita o formato real (`dou-paragraph`, `<font>`, `&quot;`, `(NR)`, linhas de pontos, título de seção, link "Vigência", o mesmo inciso em dois artigos da EC). O arquivo real fica para o passo 05.

## Como rodar

    uv run pytest tests/test_structure.py -v

Para espiar o arquivo real (sem teste ainda, é o passo 05):

    uv run python -c "from taxlaw.ingest.structure import decode_html, parse; r = parse(decode_html(open('corpus/raw/ec132-2023.html','rb').read())); print(len(r.records), 'registros;', len(r.warnings), 'avisos'); print(*r.warnings[:5], sep='\n')"

## O que observar

- **A marca está no fechamento, não na abertura:** só ao chegar em `" (NR)` ou `"` o parser sabe se o bloco inteiro é `alterado` ou `incluido`. Por isso ele acumula os parágrafos do bloco e só cria os registros no fim (`flush_block`).
- **Linha de pontos posiciona, mas não registra:** em `"Art. 156-A. ....."`, `§ 1º .....`, `IX - texto novo`, o inciso IX ganha o `pai` certo (`CF.art156-A.par1`) mesmo sem registros para o artigo e o parágrafo nessa versão. Consequência: um `pai` pode não ter registro próprio (spec seção 9: "ancestral omitido").
- **Versões:** o mesmo `id` aparece com `versao` `EC132.art1` e `EC132.art3`, cada um com seu texto. No arquivo real são 9 dispositivos assim.
- **Avisos em vez de silêncio:** um parágrafo sem rótulo dentro de um bloco não é colado no anterior. Vira aviso, e o build (passo 07) decide o que fazer.
- **Ordinal legislativo:** art. 1º a 9º, art. 10 em diante sem "º".

## Pergunta de previsão

Rodando o parser no arquivo real, o protótipo deste passo gerou 485 registros e 21 avisos. Antes de rodar: que tipos de parágrafo você acha que viraram aviso? Dica: pense no que vem depois do art. 23 e em como o FrontPage às vezes cola o número do artigo no texto.
```

- [ ] **Step 6: commit.** `git add src/taxlaw/ingest/structure.py tests/test_structure.py docs/steps/04-structure-fixture.md` e `git commit -m "feat(step-04): structure com fixture sintética"`.

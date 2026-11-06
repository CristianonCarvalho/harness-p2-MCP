# P2, passo 05: structure no HTML real (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-06-p2-passo-05-structure-real.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O `taxlaw.ingest.structure` passa a processar o arquivo real da EC 132 sem erros nem avisos, com os 23 artigos da EC e as versões corretas, e com testes que fixam esse resultado contra `corpus/raw/ec132-2023.html`.

**Architecture:** Três correções no parser do passo 04, todas achadas rodando no arquivo real: (1) o regex de artigo aceita o ponto colado ao texto (`Art. 12.Fica`); (2) `ParseResult` ganha `errors`, e uma âncora `artN` sem caput reconhecido (ou com caput de outro número) é erro, porque seguir em frente atribuiria os filhos do art. N ao artigo anterior; (3) "Brasília, em <data>" encerra o texto normativo. Os testes novos leem o arquivo real pelo caminho do próprio teste e conferem o sha256 antes.

**Tech Stack:** Python 3.13 (biblioteca padrão), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seções 3, 5 e 9)

## Global Constraints

- Só biblioteca padrão; nenhuma dependência nova no `pyproject.toml`.
- `structure.py` continua puro: não lê arquivo, não acessa rede, não usa relógio. Quem lê o arquivo real são os testes.
- Testes 100% offline e independentes do diretório atual (caminho via `Path(__file__)`); nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes.
- Não alterar `corpus/`: os testes leem o arquivo versionado e conferem o sha256 com `taxlaw.ingest.fetch.verify`.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório. Os testes sintéticos continuam com texto inventado.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `pyproject.toml`, `corpus/`, nem `guard.py`, `synthetic_ids.py`, `ingest/fetch.py`, `ingest/__init__.py`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (conferidos em 2026-11-06 no arquivo real)

- Arts. 12 e 17 da EC: caput `Art. 12.Fica instituído...` e `Art. 17.A alteração...`, sem espaço depois do ponto. Com o parser do passo 04, os 22 filhos do art. 12 eram registrados como `EC132.art11.*`, e os do art. 17 como `EC132.art16.*`, sem aviso.
- O documento termina com o art. 23 (caput + incisos I a III), seguido de "Brasília, em 20 de dezembro de 2023", das assinaturas das Mesas, de "Este texto não substitui o publicado no DOU 21.12.2023" e de um `*`.
- Com as correções: 487 registros (CF 196, EC132 159, ADCT 132; incluido 236, original 159, alterado 92), 0 erros, 0 avisos, os 23 artigos da EC, 9 dispositivos com mais de uma versão.
- O art. 156-A, § 1º, IX: versão do art. 1º cita o PIS; a do art. 3º não; a do art. 4º tem texto idêntico ao do art. 3º (a EC republica com outra data de efeito). O mesmo ocorre com o art. 195, § 17.
- Textos de `KNOWN` comparados com a impressão em PDF da página feita pelo navegador.

## Review Focus

- Âncora `artN` com caput não reconhecido ou de outro número vira erro, e o caput não é registrado (testes `test_anchor_without_recognized_caput_is_an_error` e `test_anchor_number_must_match_caput_number`).
- Os filhos de um artigo com número colado no texto ficam no artigo certo (testes `test_article_number_glued_to_text_is_recognized` e `test_children_of_art12_are_not_glued_to_art11`).
- Nada depois de "Brasília, em <data>" vira registro ou aviso, mesmo que pareça dispositivo (teste `test_text_after_brasilia_is_not_parsed`).
- Corpus alterado ou corrompido não passa despercebido: o fixture do teste real confere o sha256 com o meta antes de tudo (fixture `result` em `test_structure_real.py`).
- Versões com texto idêntico continuam sendo versões distintas (teste `test_versions_of_art156a_par1_inc_ix`).

---

### Task 1: structure no arquivo real e nota do passo

**Files:**
- Modify: `src/taxlaw/ingest/structure.py`
- Modify: `tests/test_structure.py`
- Test: `tests/test_structure_real.py`
- Create: `docs/steps/05-structure-real.md`

**Interfaces:**
- Consumes: `SOURCE_NAME` e `verify(raw_dir, name) -> bool` de `taxlaw.ingest.fetch` (passo 03), só nos testes; o arquivo `corpus/raw/ec132-2023.html` (passo 03).
- Produces (usados pelos passos 06 e 07): as mesmas interfaces do passo 04 (`Record`, `decode_html`, `paragraphs`, `parse`), e `ParseResult` agora com `errors: list[str]` além de `records` e `warnings`.

- [ ] **Step 1: testes que falham.** Substitua `tests/test_structure.py` inteiro por:

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
    '<p align="center">Assinatura sintética depois do fim do texto</p>\n'
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


def test_preamble_is_ignored_and_text_ends_at_brasilia(result):
    # Passo 05: "Brasília, em <data>" encerra o texto normativo; o que vem
    # depois (assinaturas, aviso do DOU) não é norma e não gera aviso.
    assert not any("preâmbulo" in r.texto for r in result.records)
    assert not any("Brasília" in r.texto or "Assinatura" in r.texto for r in result.records)
    assert result.warnings == []
    assert result.errors == []


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


# ---- passo 05: casos achados no arquivo real, reproduzidos com texto sintético


def test_article_number_glued_to_text_is_recognized():
    # No arquivo real: "Art. 12.Fica instituído..." (sem espaço depois do ponto).
    html = p('<a name="art12"></a>Art. 12.Texto sintético colado ao número:') + p("§ 1º Parágrafo sintético.")
    result = parse(html)
    assert [(r.id, r.versao) for r in result.records] == [
        ("EC132.art12", "EC132.art12"),
        ("EC132.art12.par1", "EC132.art12"),
    ]
    assert result.errors == [] and result.warnings == []


def test_anchor_without_recognized_caput_is_an_error():
    html = (
        p('<a name="art11"></a>Art. 11. Caput sintético.')
        + p('<a name="art12"></a>Artigo doze sem rótulo reconhecível')
        + p("§ 1º Parágrafo sintético.")
    )
    result = parse(html)
    assert result.errors == ["âncora art12 sem caput de artigo reconhecido: Artigo doze sem rótulo reconhecível"]


def test_anchor_number_must_match_caput_number():
    result = parse(p('<a name="art5"></a>Art. 6º Caput sintético.'))
    assert result.errors == ["âncora art5 com caput do art. 6: Art. 6º Caput sintético."]
    assert result.records == []


def test_text_after_brasilia_is_not_parsed():
    html = (
        p('<a name="art1"></a>Art. 1º Caput sintético.')
        + p("Brasília, em 1º de janeiro de 2000")
        + p("Assinatura sintética")
        + p("§ 1º Parece dispositivo, mas vem depois do fim do texto.")
    )
    result = parse(html)
    assert [r.id for r in result.records] == ["EC132.art1"]
    assert result.warnings == [] and result.errors == []
```

E crie `tests/test_structure_real.py`:

```python
"""Testes do structure no arquivo real da EC 132 (passo 05).

Leem `corpus/raw/ec132-2023.html` pelo caminho do próprio teste (funciona de
qualquer diretório) e conferem antes o sha256 com o meta: se o arquivo mudar,
estes números precisam ser revistos de propósito, não por acaso.

Os textos conferidos aqui foram comparados, em 2026-11-06, com a impressão em
PDF da mesma página feita pelo navegador (fonte independente do parser).
"""

from collections import Counter, defaultdict
from pathlib import Path

import pytest

from taxlaw.ingest.fetch import SOURCE_NAME, verify
from taxlaw.ingest.structure import decode_html, parse

RAW_DIR = Path(__file__).resolve().parents[1] / "corpus" / "raw"

MULTI_VERSION = {
    "ADCT.art104.incIV",
    "CF.art146.incIII.alid",
    "CF.art153.par6.incIV",
    "CF.art156-A.par1.incIX",
    "CF.art159.par3",
    "CF.art195.par17",
    "CF.art195.par19",
    "CF.art212-A.incII.alic",
    "CF.art225.par1.incVIII",
}

# (id, versao) → (alteracao, início do texto), conferidos no PDF da página.
KNOWN = {
    ("CF.art156-A", "EC132.art1"): ("incluido", "Art. 156-A. Lei complementar instituirá imposto sobre bens e serviços de competência compartilhada"),
    ("CF.art149-A", "EC132.art1"): ("alterado", "Art. 149-A. Os Municípios e o Distrito Federal poderão instituir contribuição"),
    ("ADCT.art125", "EC132.art2"): ("incluido", "Art. 125. Em 2026, o imposto previsto no art. 156-A será cobrado à alíquota estadual de 0,1%"),
    ("EC132.art12", "EC132.art12"): ("original", "Art. 12.Fica instituído o Fundo de Compensação de Benefícios Fiscais ou Financeiro-Fiscais"),
    ("EC132.art23.incI", "EC132.art23"): ("original", "I - em 2027, em relação aos arts. 3º e 11;"),
    ("CF.art195.par17", "EC132.art3"): ("alterado", "§ 17. A contribuição prevista no inciso V do caput não integrará sua própria base de cálculo"),
}


@pytest.fixture(scope="module")
def result():
    assert verify(RAW_DIR, SOURCE_NAME), "corpus/raw/ec132-2023.html não bate com o sha256 do meta"
    return parse(decode_html((RAW_DIR / f"{SOURCE_NAME}.html").read_bytes()))


def test_no_errors_and_no_warnings(result):
    assert result.errors == []
    assert result.warnings == []


def test_all_23_ec_articles_are_present(result):
    articles = {r.id for r in result.records if r.norma == "EC132" and r.pai is None}
    assert articles == {f"EC132.art{n}" for n in range(1, 24)}


def test_totals(result):
    # Âncoras de regressão: mudaram? Entenda o porquê antes de atualizar.
    assert len(result.records) == 487
    assert Counter(r.alteracao for r in result.records) == {"incluido": 236, "original": 159, "alterado": 92}
    assert Counter(r.norma for r in result.records) == {"CF": 196, "EC132": 159, "ADCT": 132}


def test_children_of_art12_are_not_glued_to_art11(result):
    # Antes da correção do passo 05, os 22 filhos do art. 12 iam para o art. 11.
    per_version = Counter(r.versao for r in result.records)
    assert per_version["EC132.art11"] == 1
    assert per_version["EC132.art12"] == 23
    assert per_version["EC132.art17"] == 1


def test_dispositivos_with_more_than_one_version(result):
    versions = defaultdict(list)
    for r in result.records:
        versions[r.id].append(r.versao)
    assert {rid for rid, vs in versions.items() if len(vs) > 1} == MULTI_VERSION


def test_versions_of_art156a_par1_inc_ix(result):
    records = [r for r in result.records if r.id == "CF.art156-A.par1.incIX"]
    assert [(r.versao, r.alteracao) for r in records] == [
        ("EC132.art1", "incluido"),
        ("EC132.art3", "alterado"),
        ("EC132.art4", "alterado"),
    ]
    original, from_2027, from_2033 = (r.texto for r in records)
    assert "Programa de Integração Social" in original
    assert "Programa de Integração Social" not in from_2027
    # A própria EC republica o mesmo texto no art. 4º: muda só a data de efeito.
    assert from_2033 == from_2027


def test_known_texts(result):
    index = {(r.id, r.versao): r for r in result.records}
    for key, (alteracao, start) in KNOWN.items():
        assert index[key].alteracao == alteracao, key
        assert index[key].texto.startswith(start), key


def test_pai_is_id_without_last_segment(result):
    for r in result.records:
        norma, path = r.id.split(".", 1)
        expected = r.id.rsplit(".", 1)[0] if "." in path else None
        assert r.pai == expected, r.id


def test_no_leftover_marks_in_texts(result):
    for r in result.records:
        assert "(NR)" not in r.texto, r.id
        assert not r.texto.startswith('"'), r.id
        assert not r.texto.endswith("Vigência"), r.id
        assert set(r.texto) - set(". "), r.id


def test_parse_is_deterministic(result):
    again = parse(decode_html((RAW_DIR / f"{SOURCE_NAME}.html").read_bytes()))
    assert again == result
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_structure.py tests/test_structure_real.py -v` → 10 failed, 19 passed (com o parser do passo 04).

- [ ] **Step 3: implemente.** Substitua `src/taxlaw/ingest/structure.py` inteiro por:

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
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_structure.py tests/test_structure_real.py -v` → 29 passed.

- [ ] **Step 5: nota do passo.** Crie `docs/steps/05-structure-real.md`:

```markdown
# Passo 05: structure no HTML real

## O que mudou

- `src/taxlaw/ingest/structure.py`, três correções achadas ao rodar no arquivo real:
  1. **Número colado no texto:** `Art. 12.Fica instituído...` (arts. 12 e 17 da EC) agora é reconhecido como artigo.
  2. **`errors` novo em `ParseResult`:** uma âncora `<a name="artN">` sem caput reconhecido, ou com caput de outro número, vira erro. O build (passo 07) aborta com erro.
  3. **Fim do texto:** "Brasília, em <data>" encerra a norma. Assinaturas e o aviso do DOU deixam de gerar aviso.
- `tests/test_structure_real.py`: 10 testes contra `corpus/raw/ec132-2023.html`, conferindo antes o sha256 com o meta.
- `tests/test_structure.py`: o teste da assinatura passou a esperar zero avisos, e há 4 testes sintéticos novos, um para cada caso real.

## Como rodar

    uv run pytest tests/test_structure.py tests/test_structure_real.py -v

## O que observar

- **O bug que o aviso escondia:** antes, `Art. 12.Fica` gerava um aviso só na linha do caput. Mas o parser continuava "dentro" do art. 11, e os 22 filhos do art. 12 eram registrados como `EC132.art11.par...` **sem nenhum aviso**. O teste `test_children_of_art12_are_not_glued_to_art11` fixa isso. Lição: um aviso no ponto do problema não basta quando o erro se propaga para o que vem depois. Por isso a âncora sem caput virou erro, não aviso.
- **Fonte independente:** os textos de `KNOWN` foram comparados com a impressão em PDF da mesma página. O parser e o navegador concordam.
- **A EC repete texto:** o art. 4º republica o art. 156-A, § 1º, IX, e o art. 195, § 17, com o mesmo texto do art. 3º. Só a data de efeito muda (2033 em vez de 2027). A versão importa mesmo com texto idêntico.
- **Números como âncora de regressão:** 487 registros, 23 artigos da EC, 9 dispositivos com várias versões. Se o corpus mudar, esses testes quebram de propósito.

## Pergunta de previsão

O art. 3º da EC tira do inciso IX a menção à contribuição para o PIS, a partir de 2027. Se alguém perguntar ao server, com `data_referencia` 2026-06-01, se o IBS integra a base do PIS, qual versão o server deve citar? E o que muda se a data for 2028-06-01?
```

- [ ] **Step 6: commit.** `git add src/taxlaw/ingest/structure.py tests/test_structure.py tests/test_structure_real.py docs/steps/05-structure-real.md` e `git commit -m "feat(step-05): structure no HTML real da EC 132"`.

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

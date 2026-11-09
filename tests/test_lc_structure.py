"""Testes do parser de lei complementar (passo 13a) com HTML sintético.

O HTML imita o formato do Planalto para leis compiladas (spec do passo 13,
seção 2): <p class=MsoNormal>, âncoras por dispositivo, redação antiga em
<span style="...text-decoration:line-through">, marcas "(Redação dada pela
...)" no fim e títulos de capítulo/seção em parágrafos próprios. Os textos
são inventados.
"""

import pytest

from taxlaw.ingest.lc_structure import LcParagraph, lc_paragraphs, parse_lc


def p(text: str, *, struck: bool = False, anchor: str | None = None) -> str:
    style = "font-family: Arial,sans-serif" + ("; text-decoration:line-through" if struck else "")
    name = f'<a name="{anchor}"></a>' if anchor else ""
    return f'<p class=MsoNormal><span style="{style}"><font size="2">{name}{text}</font></span></p>\n'


def page(*paragraphs: str) -> str:
    return "<html><head><title>Lcp 999</title></head><body>" + "".join(paragraphs) + "</body></html>"


MARK_227 = "(Redação dada pela Lei Complementar nº 227, de 2026)"
INCLUDED_227 = "(Incluído pela Lei Complementar nº 227, de 2026)"

HTML = page(
    p("TÍTULO III"),
    p("DOS GIRASSÓIS"),
    p("CAPÍTULO II"),
    p("DA REDUÇÃO DOS GIRASSÓIS"),
    p("Art. 10. Ficam reduzidas em 60% as alíquotas sobre girassóis:", anchor="art10"),
    p("I - girassóis amarelos;"),
    p("II - girassóis antigos;", struck=True),
    p(f"II - girassóis novos; {MARK_227}"),
    p("a) de jardim;"),
    p("III - (VETADO)."),
    p("§ 1º Regulamento disporá sobre girassóis."),
    p(f"§ 2º Tulipas também. {INCLUDED_227}"),
    p("Seção I"),
    p("Disposições Gerais"),
    p("Art. 11. Este artigo está fora do escopo."),
    p("§ 1º Também fora."),
    p("Art. 12. Ficam reduzidas a zero as alíquotas sobre cactos. Vigência"),
    p("Parágrafo único. Aplica-se o art. 10. (Vide Decreto nº 1, de 2026)"),
)
SCOPE = {"art10", "art12"}


def parse(html=HTML, scope=SCOPE):
    return parse_lc(html, norma="LC214", scope=scope)


def by_id(result):
    return {r.id: r for r in result.records}


def test_paragraphs_separate_struck_text():
    paragraphs = lc_paragraphs(page(p("velho", struck=True), p("novo"), '<p><span style="text-decoration: line-through">meio</span> e meio</p>'))
    assert paragraphs == [
        LcParagraph("", True, False),
        LcParagraph("novo", False, False),
        LcParagraph("e meio", False, True),
    ]


def test_strike_tags_also_count():
    assert lc_paragraphs("<p><strike>velho</strike></p><p><s>velho</s></p><p><del>velho</del></p>") == [LcParagraph("", True, False)] * 3


def test_records_ids_citations_and_parents():
    records = by_id(parse())
    assert list(records) == [
        "LC214.art10", "LC214.art10.incI", "LC214.art10.incII", "LC214.art10.incII.alia",
        "LC214.art10.par1", "LC214.art10.par2", "LC214.art12", "LC214.art12.parunico",
    ]
    assert records["LC214.art10.incII.alia"].citacao == "LC 214/2025, art. 10, II, a"
    assert records["LC214.art10.incII.alia"].pai == "LC214.art10.incII"
    assert records["LC214.art12.parunico"].citacao == "LC 214/2025, art. 12, parágrafo único"
    assert {r.norma for r in records.values()} == {"LC214"} and {r.versao for r in records.values()} == {"LC214"}


def test_struck_old_wording_is_dropped_and_counted():
    result = parse()
    assert by_id(result)["LC214.art10.incII"].texto == "II - girassóis novos;"
    assert result.struck == 1
    assert all("antigos" not in r.texto for r in result.records)


def test_amendment_marks_become_alteracao_and_origem_and_leave_the_text():
    records = by_id(parse())
    altered, included, plain = records["LC214.art10.incII"], records["LC214.art10.par2"], records["LC214.art10.incI"]
    assert (altered.alteracao, altered.origem) == ("alterado", "LC 214/2025, com redação dada pela LC 227/2026")
    assert (included.alteracao, included.origem) == ("incluido", "LC 214/2025, incluído pela LC 227/2026")
    assert (plain.alteracao, plain.origem) == ("original", "LC 214/2025")
    assert included.texto == "§ 2º Tulipas também."


def test_loose_link_text_and_vide_marks_are_removed():
    records = by_id(parse())
    assert records["LC214.art12"].texto.endswith("sobre cactos.")
    assert records["LC214.art12.parunico"].texto == "Parágrafo único. Aplica-se o art. 10."
    assert records["LC214.art12.parunico"].alteracao == "original"


def test_vetoed_has_no_record_but_is_listed():
    result = parse()
    assert "LC214.art10.incIII" not in by_id(result)
    assert result.vetoed == ["LC214.art10.incIII"]


def test_headings_and_their_names_are_not_records_nor_warnings():
    result = parse()
    assert result.warnings == [] and result.errors == []
    assert all("GIRASSÓIS" not in r.texto and "Disposições" not in r.texto for r in result.records)


def test_out_of_scope_articles_are_skipped():
    assert not any(r.id.startswith("LC214.art11") for r in parse().records)


def test_missing_scope_article_is_an_error():
    assert parse(scope=SCOPE | {"art99"}).errors == ["artigo do escopo não encontrado: LC214.art99"]


def test_partly_struck_paragraph_in_scope_is_an_error():
    html = page(p("Art. 10. Caput."), '<p><span style="text-decoration:line-through">I - velho</span> I - novo</p>')
    errors = parse(html, {"art10"}).errors
    assert len(errors) == 1 and errors[0].startswith("parágrafo parcialmente tachado em LC214.art10")


def test_partly_struck_paragraph_out_of_scope_is_ignored():
    html = page(p("Art. 10. Caput."), p("Art. 11. Fora."), '<p><span style="text-decoration:line-through">I - velho</span> I - novo</p>')
    assert parse(html, {"art10"}).errors == []


def test_repeated_id_is_an_error_old_wording_that_escaped():
    html = page(p("Art. 10. Caput."), p("I - redação antiga sem tachado;"), p(f"I - redação nova; {MARK_227}"))
    assert parse(html, {"art10"}).errors == ["id repetido LC214.art10.incI: redação antiga fora do tachado?"]


def test_unlabeled_paragraph_in_scope_is_a_warning():
    html = page(p("Art. 10. Caput:"), p("texto solto sem rótulo"))
    result = parse(html, {"art10"})
    assert result.warnings == ["parágrafo sem rótulo em LC214.art10: 'texto solto sem rótulo'"]


def test_promulgated_after_veto_is_marked_in_origem():
    html = page(p("Art. 10. Caput:"), p("V - fundos de investimento; (Promulgação partes vetadas)"))
    result = parse(html, {"art10"})
    record = by_id(result)["LC214.art10.incV"]
    assert record.origem == "LC 214/2025, parte promulgada após veto" and record.texto == "V - fundos de investimento;"
    assert result.warnings == ["LC214.art10.incV: promulgado depois de veto; efeitos ficam indeterminados"]


@pytest.mark.parametrize("unclosed", ["<font size=2>", "<span>"])
def test_unclosed_tags_do_not_leak_strike_into_next_paragraph(unclosed):
    html = page(f'<p><span style="text-decoration:line-through">{unclosed}velho</span></p>', p("Art. 10. Caput."))
    assert [x.text for x in lc_paragraphs(html)] == ["", "Art. 10. Caput."]


def test_unclosed_paragraph_does_not_carry_strike_into_the_next():
    # FrontPage às vezes não fecha o <p>: o tachado do anterior não pode vazar.
    html = '<p><span style="text-decoration:line-through">velho<p>Art. 10. Caput.</p>'
    assert [(x.text, x.struck) for x in lc_paragraphs(html)] == [("", True), ("Art. 10. Caput.", False)]

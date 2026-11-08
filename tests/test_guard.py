"""Testes da guarda de CPF/CNPJ (passo 02).

Números válidos são gerados em tempo de execução a partir de bases
inventadas (taxlaw.synthetic_ids). Nenhum documento válido fica escrito aqui.
"""

import pytest

from taxlaw.guard import Finding, describe_findings, find_taxpayer_ids
from taxlaw.synthetic_ids import make_cnpj, make_cpf

CPF = make_cpf("123456789")
CPF_FMT = make_cpf("123456789", formatted=True)
CNPJ = make_cnpj("123456780001")
CNPJ_FMT = make_cnpj("123456780001", formatted=True)
CNPJ_ALNUM = make_cnpj("ABCDEFGH0001")
CNPJ_ALNUM_FMT = make_cnpj("ABCDEFGH0001", formatted=True)


def wrong_last_digit(number: str) -> str:
    """Mesmo número com o último DV trocado: nunca é válido (o DV é único)."""
    return number[:-1] + str((int(number[-1]) + 1) % 10)


@pytest.mark.parametrize(
    ("number", "kind"),
    [
        (CPF, "cpf"),
        (CPF_FMT, "cpf"),
        (CNPJ, "cnpj"),
        (CNPJ_FMT, "cnpj"),
        (CNPJ_ALNUM, "cnpj"),
        (CNPJ_ALNUM_FMT, "cnpj"),
        (CNPJ_ALNUM_FMT.lower(), "cnpj"),
    ],
)
def test_finds_valid_number_and_its_position(number, kind):
    text = f"Consulta sobre o contribuinte {number}, art. 156-A."
    findings = find_taxpayer_ids(text)
    assert [f.kind for f in findings] == [kind]
    assert text[findings[0].start : findings[0].end] == number


def test_partial_mask_from_rfb_examples():
    # Máscara só com barra e hífen, como "AA345678/0003-29" na pergunta 23.
    compact = make_cnpj("AA3456780003")
    partial = f"{compact[:8]}/{compact[8:12]}-{compact[12:]}"
    assert [f.kind for f in find_taxpayer_ids(f"filial {partial}")] == ["cnpj"]


@pytest.mark.parametrize("number", [CPF, CPF_FMT, CNPJ_FMT, CNPJ_ALNUM])
def test_wrong_check_digit_is_not_a_finding(number):
    assert find_taxpayer_ids(f"número {wrong_last_digit(number)}") == []


@pytest.mark.parametrize(
    "text",
    ["000.000.000-00", "11111111111", "999.999.999-99", "00.000.000/0000-00", "00000000000000"],
)
def test_repeated_single_character_is_discarded(text):
    assert find_taxpayer_ids(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Art. 156-A. Lei complementar instituirá imposto sobre bens e serviços.",
        "Lei Complementar nº 214, de 16 de janeiro de 2025.",
        "EC 132/2023, publicada no DOU de 21/12/2023.",
        "Processo nº 10880.721234/2023-11.",
        "Processo 0001234-56.2023.8.26.0100.",
        "Telefone (61) 3412-3456.",
        "Valor de R$ 1.234.567.890,12.",
        "",
    ],
)
def test_legal_text_without_ids_has_no_findings(text):
    assert find_taxpayer_ids(text) == []


def test_valid_number_glued_to_more_digits_is_not_a_finding():
    # "9" + CPF + "9" é outro número, de 13 dígitos: não é este CPF.
    assert find_taxpayer_ids(f"9{CPF}9") == []
    assert find_taxpayer_ids(f"1.{CPF_FMT}") == []


@pytest.mark.parametrize("wrapper", ["({})", "CPF:{}", "{}.", "{};", '"{}"', "\n{}\n"])
def test_punctuation_around_number_still_finds_it(wrapper):
    assert [f.kind for f in find_taxpayer_ids(wrapper.format(CPF_FMT))] == ["cpf"]


def test_non_ascii_digits_are_ignored_without_error():
    arabic = CPF.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    fullwidth = CPF.translate(str.maketrans("0123456789", "０１２３４５６７８９"))
    assert find_taxpayer_ids(arabic) == []
    assert find_taxpayer_ids(fullwidth) == []


def test_several_findings_sorted_by_position():
    text = f"{CNPJ_ALNUM_FMT} e depois {CPF} e {CNPJ}"
    findings = find_taxpayer_ids(text)
    assert [f.kind for f in findings] == ["cnpj", "cpf", "cnpj"]
    assert [f.start for f in findings] == sorted(f.start for f in findings)


def test_finding_and_message_never_contain_the_number():
    text = f"{CPF_FMT} e {CNPJ_ALNUM_FMT}"
    findings = find_taxpayer_ids(text)
    exposed = repr(findings) + str(findings) + describe_findings(findings)
    for secret in (CPF, CPF_FMT, CPF[:9], CNPJ_ALNUM, CNPJ_ALNUM_FMT, CNPJ_ALNUM[:12]):
        assert secret not in exposed
    assert describe_findings(findings) == "possível dado de contribuinte: 1 CPF e 1 CNPJ (números omitidos)"


def test_message_when_nothing_found():
    assert describe_findings([]) == "nenhum CPF ou CNPJ encontrado"


def test_finding_is_immutable():
    finding = Finding(kind="cpf", start=0, end=11)
    with pytest.raises(AttributeError):
        finding.start = 1


@pytest.mark.parametrize(
    "template",
    [
        "https://exemplo.invalid/{}",
        "https://exemplo.invalid/{}/detalhes",
        "https://exemplo.invalid/2024/{}",
        "/consulta/cpf-{}",
        "doc.{}",
    ],
)
def test_number_inside_url_or_slug_is_found(template):
    # Passo 11: o WebFetch recebe URLs. A "/" separa campos, e letra do outro
    # lado de "." ou "-" não continua o número.
    assert [f.kind for f in find_taxpayer_ids(template.format(CPF))] == ["cpf"]
    assert [f.kind for f in find_taxpayer_ids(template.format(CNPJ))] == ["cnpj"]


def test_formatted_cnpj_between_slashes_is_found():
    assert [f.kind for f in find_taxpayer_ids(f"pasta/{CNPJ_FMT}/arquivo")] == ["cnpj"]

"""Testes dos dígitos verificadores e do gerador sintético (passo 02).

Nenhum CPF/CNPJ válido aparece escrito aqui: só bases inventadas, e os
números completos são gerados em tempo de execução.
"""

from pathlib import Path
import random
import re
import sys

# Garante que o pacote em src/ seja encontrado mesmo quando o pytest é
# invocado a partir do ambiente virtual do repositório base durante o gate.
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

if "taxlaw" in sys.modules:
    mod = sys.modules["taxlaw"]
    if getattr(mod, "__file__", None) and not mod.__file__.startswith(_SRC):
        del sys.modules["taxlaw"]

import pytest

from taxlaw.guard import cnpj_check_digits, cpf_check_digits
from taxlaw.synthetic_ids import make_cnpj, make_cpf


def reference_mod11(values: list[int], *, cycle: bool) -> int:
    """Referência independente, escrita do jeito "da direita para a esquerda".

    Pesos começam em 2 no último caractere e crescem para a esquerda: no CPF
    sem limite (2, 3, ..., 11); no CNPJ voltam a 2 depois de 9 (2..9, 2..).
    É outra formulação da mesma regra, para pegar erro de peso ou de ordem.
    """
    total = 0
    for i, value in enumerate(reversed(values)):
        weight = 2 + (i % 8 if cycle else i)
        total += value * weight
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def reference_cpf(base9: str) -> str:
    values = [int(c) for c in base9]
    dv1 = reference_mod11(values, cycle=False)
    dv2 = reference_mod11(values + [dv1], cycle=False)
    return f"{dv1}{dv2}"


def reference_cnpj(base12: str) -> str:
    values = [ord(c) - 48 for c in base12]
    dv1 = reference_mod11(values, cycle=True)
    dv2 = reference_mod11(values + [dv1], cycle=True)
    return f"{dv1}{dv2}"


def test_cnpj_matches_rfb_worked_example():
    # Exemplo resolvido no "Perguntas & Respostas: CNPJ alfanumérico" da RFB,
    # pergunta 14: base 12.ABC.345/01DE, somas 459 e 424, DVs 3 e 5.
    assert cnpj_check_digits("12ABC34501DE") == "35"


def test_cpf_matches_reference_on_many_bases():
    rng = random.Random(2)
    for _ in range(2000):
        base = "".join(rng.choice("0123456789") for _ in range(9))
        assert cpf_check_digits(base) == reference_cpf(base), base


def test_cnpj_matches_reference_on_many_bases():
    rng = random.Random(2)
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for _ in range(2000):
        base = "".join(rng.choice(alphabet) for _ in range(12))
        assert cnpj_check_digits(base) == reference_cnpj(base), base


def test_numeric_cnpj_keeps_digit_values():
    # Para dígitos, ASCII - 48 é o próprio dígito: o CNPJ numérico de sempre
    # continua com os mesmos DVs.
    base = "123456780001"
    assert cnpj_check_digits(base) == reference_cnpj(base)
    assert [ord(c) - 48 for c in base] == [int(c) for c in base]


@pytest.mark.parametrize("bad", ["12345678", "1234567890", "12345678a", "١٢٣٤٥٦٧٨٩", ""])
def test_cpf_rejects_bad_base(bad):
    with pytest.raises(ValueError):
        cpf_check_digits(bad)


@pytest.mark.parametrize("bad", ["12ABC34501D", "12ABC34501DE0", "12abc34501de", "12ABC345-1DE"])
def test_cnpj_rejects_bad_base(bad):
    with pytest.raises(ValueError):
        cnpj_check_digits(bad)


def test_make_cpf_compact_and_formatted():
    compact = make_cpf("123456789")
    assert re.fullmatch(r"[0-9]{11}", compact)
    assert compact[9:] == cpf_check_digits("123456789")
    formatted = make_cpf("123456789", formatted=True)
    assert re.fullmatch(r"[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", formatted)
    assert formatted.replace(".", "").replace("-", "") == compact


def test_make_cnpj_compact_and_formatted():
    compact = make_cnpj("ABCDEFGH0001")
    assert re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", compact)
    formatted = make_cnpj("ABCDEFGH0001", formatted=True)
    assert re.fullmatch(r"[0-9A-Z]{2}\.[0-9A-Z]{3}\.[0-9A-Z]{3}/[0-9A-Z]{4}-[0-9]{2}", formatted)
    assert re.sub(r"[./-]", "", formatted) == compact

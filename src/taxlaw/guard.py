"""Guarda de CPF/CNPJ: acha números de contribuinte num texto sem nunca repeti-los.

É o ponto único usado pelo hook do Claude Code (passo 11) e pelo server
(passo 10). Um "achado" exige formato E dígitos verificadores corretos: só a
regex confundiria números de processo, datas e artigos com documentos.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

Kind = Literal["cpf", "cnpj"]

# Pesos do módulo 11 do CNPJ ("Perguntas & Respostas: CNPJ alfanumérico" da
# RFB, pergunta 14). Valem igual para o CNPJ numérico e o alfanumérico.
CNPJ_DV1_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
CNPJ_DV2_WEIGHTS = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _mod11_digit(values: list[int], weights: tuple[int, ...]) -> int:
    """Um dígito verificador: soma ponderada, resto por 11; resto 0 ou 1 vira 0."""
    remainder = sum(v * w for v, w in zip(values, weights, strict=True)) % 11
    return 0 if remainder < 2 else 11 - remainder


def cpf_check_digits(base9: str) -> str:
    """Os 2 DVs do CPF para uma base de 9 dígitos (pesos 10..2 e depois 11..2)."""
    if not re.fullmatch(r"[0-9]{9}", base9):
        raise ValueError("a base do CPF deve ter exatamente 9 dígitos de 0 a 9")
    values = [int(c) for c in base9]
    dv1 = _mod11_digit(values, tuple(range(10, 1, -1)))
    dv2 = _mod11_digit(values + [dv1], tuple(range(11, 1, -1)))
    return f"{dv1}{dv2}"


def cnpj_check_digits(base12: str) -> str:
    """Os 2 DVs do CNPJ para uma base de 12 caracteres (0-9 e A-Z maiúsculas).

    Cada caractere vale o código ASCII menos 48: os dígitos mantêm o valor de
    sempre ('7' -> 7) e as letras passam a valer 17 ('A') a 42 ('Z').
    """
    if not re.fullmatch(r"[0-9A-Z]{12}", base12):
        raise ValueError("a base do CNPJ deve ter 12 caracteres entre 0-9 e A-Z")
    values = [ord(c) - 48 for c in base12]
    dv1 = _mod11_digit(values, CNPJ_DV1_WEIGHTS)
    dv2 = _mod11_digit(values + [dv1], CNPJ_DV2_WEIGHTS)
    return f"{dv1}{dv2}"


@dataclass(frozen=True)
class Finding:
    """Um achado: só o tipo e a posição no texto. Nunca guarda o número."""

    kind: Kind
    start: int
    end: int


# Fronteiras: o candidato não pode estar colado a letra/dígito, nem a um
# separador seguido de letra/dígito. Assim "1.234.567.890-12" não vira o CPF
# "234.567.890-12", mas "CPF 000.000.000-00." (ponto final) ainda é candidato.
# [0-9] e não \d: em Python, \d também casa dígitos de outros alfabetos.
_BEFORE = r"(?<![0-9A-Za-z])(?<![0-9A-Za-z][./-])"
_AFTER = r"(?![0-9A-Za-z])(?![./-][0-9A-Za-z])"
# Cada separador é opcional sozinho: a RFB mostra máscaras parciais como
# "AA345678/0003-29" (Perguntas & Respostas, pergunta 23).
_CPF_RE = re.compile(_BEFORE + r"[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}" + _AFTER)
# IGNORECASE: a RFB só emite maiúsculas, mas a guarda prefere bloquear um
# "ab.cde.fgh/0001-xx" digitado em minúsculas a deixá-lo passar.
_CNPJ_RE = re.compile(
    _BEFORE + r"[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?[0-9]{2}" + _AFTER,
    re.IGNORECASE,
)
_SEPARATORS = re.compile(r"[./-]")


def _is_valid(compact: str, kind: Kind) -> bool:
    """DVs corretos e não é um caractere repetido (000..., 111...: DV "válido" por acaso)."""
    if len(set(compact)) == 1:
        return False
    if kind == "cpf":
        return compact[9:] == cpf_check_digits(compact[:9])
    return compact[12:] == cnpj_check_digits(compact[:12])


def find_taxpayer_ids(text: str) -> list[Finding]:
    """Todos os CPF/CNPJ com DV válido em `text`, em ordem de posição."""
    findings: list[Finding] = []
    for kind, pattern in (("cpf", _CPF_RE), ("cnpj", _CNPJ_RE)):
        for match in pattern.finditer(text):
            compact = _SEPARATORS.sub("", match.group()).upper()
            if _is_valid(compact, kind):
                findings.append(Finding(kind=kind, start=match.start(), end=match.end()))
    return sorted(findings, key=lambda f: f.start)


def describe_findings(findings: list[Finding]) -> str:
    """Mensagem para humano ou modelo: quantos e de que tipo, sem nenhum número."""
    if not findings:
        return "nenhum CPF ou CNPJ encontrado"
    counts = Counter(f.kind for f in findings)
    parts = [f"{counts[k]} {k.upper()}" for k in ("cpf", "cnpj") if counts[k]]
    return "possível dado de contribuinte: " + " e ".join(parts) + " (números omitidos)"


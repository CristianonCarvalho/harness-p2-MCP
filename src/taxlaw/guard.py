"""Guarda de CPF/CNPJ: acha números de contribuinte num texto sem nunca repeti-los.

É o ponto único usado pelo hook do Claude Code (passo 11) e pelo server
(passo 10). Um "achado" exige formato E dígitos verificadores corretos: só a
regex confundiria números de processo, datas e artigos com documentos.
"""

from __future__ import annotations

import re
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

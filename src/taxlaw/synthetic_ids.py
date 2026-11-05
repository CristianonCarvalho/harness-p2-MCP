"""Gerador de CPF e CNPJ sintéticos, só para testes.

Regra do projeto: nenhum CPF/CNPJ válido fica escrito no repositório. Os
testes escrevem só a base (9 ou 12 caracteres inventados) e geram o número
completo em tempo de execução, calculando os DVs com a mesma função da guarda.
"""

from __future__ import annotations

from taxlaw.guard import cnpj_check_digits, cpf_check_digits


def make_cpf(base9: str, *, formatted: bool = False) -> str:
    """CPF válido a partir de 9 dígitos; `formatted` usa a máscara 000.000.000-00."""
    number = base9 + cpf_check_digits(base9)
    if not formatted:
        return number
    return f"{number[:3]}.{number[3:6]}.{number[6:9]}-{number[9:]}"


def make_cnpj(base12: str, *, formatted: bool = False) -> str:
    """CNPJ válido a partir de 12 caracteres; `formatted` usa a máscara XX.XXX.XXX/XXXX-00."""
    number = base12 + cnpj_check_digits(base12)
    if not formatted:
        return number
    return f"{number[:2]}.{number[2:5]}.{number[5:8]}/{number[8:12]}-{number[12:]}"

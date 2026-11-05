# P2, passo 02: guarda de CPF/CNPJ (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-05-p2-passo-02-guarda-cpf-cnpj.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma guarda única que acha CPF, CNPJ numérico e CNPJ alfanumérico num texto, validando os dígitos verificadores, e devolve só tipo e posição, nunca o número; mais um gerador de números sintéticos para os testes.

**Architecture:** `src/taxlaw/guard.py` tem duas camadas: o cálculo dos DVs (módulo 11) e a varredura do texto (regex de candidatos com fronteiras + validação de DV + descarte de repetidos). `src/taxlaw/synthetic_ids.py` gera números válidos a partir de bases inventadas, para que nenhum documento válido fique escrito no repositório. Hook (passo 11) e server (passo 10) vão importar a mesma `guard.py`.

**Tech Stack:** Python 3.13 (biblioteca padrão), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seções 3, 7 e 9)

## Global Constraints

- Só biblioteca padrão; nenhuma dependência nova no `pyproject.toml`.
- Testes 100% offline; nenhum teste depende do diretório atual; nada de `conftest.py`.
- **Nenhum CPF/CNPJ válido escrito no repositório** (código, testes, notas, mensagens de commit). Testes escrevem só bases e geram o número completo em tempo de execução com `taxlaw.synthetic_ids`.
- `Finding`, `repr`, `str` e qualquer mensagem da guarda nunca contêm o número encontrado.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/` nem `pyproject.toml`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (conferidos em 2026-11-05)

Fonte: RFB, "Perguntas & Respostas: CNPJ alfanumérico" (gov.br/receitafederal, PDF).

- CNPJ: 14 posições, `XX.XXX.XXX/XXXX-DV`; as 12 primeiras podem ter dígitos e letras **maiúsculas** A–Z; os 2 DVs são numéricos (perguntas 2 e 21). Vale a partir de julho de 2026; o numérico continua válido (perguntas 4 e 7).
- DV pelo módulo 11; cada caractere vale **código ASCII − 48** ('0'..'9' → 0..9, 'A' → 17, 'Z' → 42). Pesos do 1º DV: 5,4,3,2,9,8,7,6,5,4,3,2; do 2º DV (com o 1º DV anexado): 6,5,4,3,2,9,8,7,6,5,4,3,2. Resto < 2 → DV 0; senão DV = 11 − resto (pergunta 14).
- Exemplo resolvido da RFB: base `12ABC34501DE` → somas 459 e 424 → DVs `35` (pergunta 14).
- Máscaras parciais existem nos exemplos, como `AA345678/0003-29` (pergunta 23): cada separador é opcional de forma independente.
- CPF: base de 9 dígitos; 1º DV com pesos 10..2; 2º DV com pesos 11..2 sobre base + 1º DV; mesma regra do resto.

## Review Focus

- Dígitos não ASCII (árabe-índicos, largura total) não viram achado nem quebram o cálculo: usar `[0-9]`, nunca `\d` (teste `test_non_ascii_digits_are_ignored_without_error`, Task 2).
- Número válido colado a mais dígitos ou a separador + dígito (`9<CPF>9`, `1.<CPF formatado>`) não é achado; o mesmo número cercado de pontuação comum (parênteses, aspas, ponto final, `CPF:`) é (testes de fronteira, Task 2).
- CNPJ alfanumérico em minúsculas ainda é achado: a guarda prefere bloquear a deixar passar (caso `.lower()` no teste parametrizado, Task 2).
- O número não vaza por `repr`, `str` nem pela mensagem, nem em parte (base de 9/12 caracteres) (teste `test_finding_and_message_never_contain_the_number`, Task 2).
- Base de tamanho errado, com minúsculas ou separador vira `ValueError` explícito em vez de DV errado (testes `test_*_rejects_bad_base`, Task 1).

---

### Task 1: Dígitos verificadores e gerador sintético

**Files:**
- Create: `src/taxlaw/guard.py`
- Create: `src/taxlaw/synthetic_ids.py`
- Test: `tests/test_check_digits.py`

**Interfaces:**
- Consumes: pacote `taxlaw` instalado pelo `uv` (passo 00).
- Produces: `cpf_check_digits(base9: str) -> str`; `cnpj_check_digits(base12: str) -> str` (ambos devolvem os 2 DVs como string e levantam `ValueError` para base inválida); constantes `CNPJ_DV1_WEIGHTS`, `CNPJ_DV2_WEIGHTS`; tipo `Kind = Literal["cpf", "cnpj"]`; `make_cpf(base9: str, *, formatted: bool = False) -> str`; `make_cnpj(base12: str, *, formatted: bool = False) -> str`.

- [ ] **Step 1: testes que falham.** Crie `tests/test_check_digits.py`:

```python
"""Testes dos dígitos verificadores e do gerador sintético (passo 02).

Nenhum CPF/CNPJ válido aparece escrito aqui: só bases inventadas, e os
números completos são gerados em tempo de execução.
"""

import random
import re

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
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_check_digits.py -v` → erro de import (`taxlaw.guard` não existe).

- [ ] **Step 3: implemente.** Crie `src/taxlaw/guard.py`:

```python
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
```

E `src/taxlaw/synthetic_ids.py`:

```python
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
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_check_digits.py -v` → 15 passed.

- [ ] **Step 5: commit.** `git add src/taxlaw/guard.py src/taxlaw/synthetic_ids.py tests/test_check_digits.py` e `git commit -m "feat(step-02): dígitos verificadores de CPF/CNPJ e gerador sintético"`.

### Task 2: Varredura de texto e nota do passo

**Files:**
- Modify: `src/taxlaw/guard.py`
- Test: `tests/test_guard.py`
- Create: `docs/steps/02-guarda-cpf-cnpj.md`

**Depends on:** Task 1

**Interfaces:**
- Consumes: `cpf_check_digits`, `cnpj_check_digits`, `Kind` (Task 1, em `taxlaw.guard`); `make_cpf`, `make_cnpj` (Task 1, em `taxlaw.synthetic_ids`).
- Produces: `Finding(kind: Kind, start: int, end: int)` (dataclass congelada); `find_taxpayer_ids(text: str) -> list[Finding]` (ordenada por `start`); `describe_findings(findings: list[Finding]) -> str`. O hook (passo 11) e `tools.py` (passo 09) importam esses três.

- [ ] **Step 1: testes que falham.** Crie `tests/test_guard.py`:

```python
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
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_guard.py -v` → erro de import (`Finding` não existe).

- [ ] **Step 3: implemente.** Em `src/taxlaw/guard.py`, acrescente `from collections import Counter` aos imports (depois de `import re`) e, no fim do arquivo, o bloco:

```python
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
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_check_digits.py tests/test_guard.py -v` → 52 passed.

- [ ] **Step 5: nota do passo.** Crie `docs/steps/02-guarda-cpf-cnpj.md`:

```markdown
# Passo 02: guarda de CPF/CNPJ

## O que mudou

- `src/taxlaw/guard.py`: `find_taxpayer_ids(text)` acha CPF, CNPJ numérico e CNPJ alfanumérico num texto e devolve só o tipo e a posição (`Finding`). `describe_findings` monta a mensagem sem nenhum número. Também calcula os dígitos verificadores (`cpf_check_digits`, `cnpj_check_digits`).
- `src/taxlaw/synthetic_ids.py`: `make_cpf` e `make_cnpj` geram números válidos a partir de bases inventadas, em tempo de execução. Nenhum CPF/CNPJ válido fica escrito no repositório.
- É a peça que o hook (passo 11) e o server (passo 10) vão chamar: uma guarda só, no ponto por onde tudo passa.

## Como rodar

    uv run pytest tests/test_check_digits.py tests/test_guard.py -v

Para brincar no terminal:

    uv run python -c "from taxlaw.synthetic_ids import make_cnpj; from taxlaw.guard import find_taxpayer_ids, describe_findings; t = 'empresa ' + make_cnpj('ABCDEFGH0001', formatted=True); f = find_taxpayer_ids(t); print(f, describe_findings(f))"

## O que observar

- **Regex não basta:** a regex só acha candidatos. O que separa um CPF de um número de processo é o dígito verificador. Por isso "Processo 0001234-56.2023.8.26.0100" não vira achado.
- **CNPJ alfanumérico:** cada caractere vale o código ASCII menos 48 ('A' = 17). Para dígitos isso dá o próprio dígito, então o CNPJ numérico de sempre continua com os mesmos DVs. Conferido no exemplo resolvido da RFB ("Perguntas & Respostas: CNPJ alfanumérico", pergunta 14).
- **Fronteiras:** `1.` + um CPF formatado não é achado, porque o número continua para a esquerda. Já um CPF seguido de ponto final é.
- **`[0-9]` e não `\d`:** em Python, `\d` casa dígitos de outros alfabetos (árabe, largura total), e `ord(c) - 48` daria lixo.
- **O número nunca sai da guarda:** `Finding` guarda tipo e posição; a mensagem diz "1 CPF e 1 CNPJ (números omitidos)". Se o motivo do bloqueio repetisse o número, o log do hook vazaria exatamente o que ele deveria barrar.
- **Repetidos:** `000.000.000-00` tem DV "válido" pela conta, mas é descartado.

## Pergunta de previsão

O resto 0 e o resto 1 viram o mesmo DV (0). Então trocar um único dígito da base sempre muda o DV? Pense num caso em que a soma muda de resto 0 para resto 1. E o que isso diz sobre usar o DV como prova de que o número é "real"?
```

- [ ] **Step 6: commit.** `git add src/taxlaw/guard.py tests/test_guard.py docs/steps/02-guarda-cpf-cnpj.md` e `git commit -m "feat(step-02): guarda de CPF/CNPJ no texto"`.

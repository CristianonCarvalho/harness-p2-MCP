# P2, passo 08: cabeçalho `fonte` e busca com limiar (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-07-p2-passo-08-search.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) `dispositivos.json` com `fonte_url` e `coletado_em` num cabeçalho único `fonte`; (2) um leitor do corpus e uma busca BM25 com limiar de relevância calibrado, em que "não encontrei" é uma resposta explícita com motivo.

**Architecture:** Task 1 muda só o `render` do build (cabeçalho `fonte`), os testes do passo 07 e o arquivo gerado. Task 2 cria `taxlaw.corpus` (lê o JSON, `versao` = sha256 do arquivo, versões por id) e `taxlaw.search` (um documento por id, tokenizador de português, BM25 com K1 1,5 e B 0,75, relevância = pontuação / teto da consulta, limiar 0,15).

**Tech Stack:** Python 3.13 (biblioteca padrão: `json`, `hashlib`, `math`, `unicodedata`, `re`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seções 5, 6, 9 e 10; formato do arquivo decidido em 2026-11-07)

## Global Constraints

- Nenhuma dependência nova (BM25 escrito à mão, biblioteca padrão).
- Busca determinística: mesma consulta, mesmo resultado; empates pelo id; nada de aleatoriedade.
- Busca e corpus são só leitura e offline; o texto das normas é dado a pontuar, nunca interpretado.
- `search` nunca devolve resultado abaixo do limiar; "não encontrei" vem com `reason`.
- Testes 100% offline e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes. Não alterar `corpus/raw/` nem `corpus/efeitos_correcoes.yaml`.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `pyproject.toml`, `uv.lock`, `corpus/raw/`, `corpus/efeitos_correcoes.yaml`, nem `guard.py`, `synthetic_ids.py`, `ingest/__init__.py`, `ingest/fetch.py`, `ingest/structure.py`, `ingest/effects.py`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-07 no corpus)

- Com o cabeçalho `fonte`, o `dispositivos.json` tem 7.801 linhas (antes, 8.768); o `fonte` tem `url`, `coletado_em` e `sha256_html` do `.meta.json`.
- Pontuação BM25 absoluta não separa os grupos (dentro do tema: "art. 156-A" = 2,17; fora: "horário de funcionamento do banco" = 5,81).
- Relevância (pontuação / teto, termos desconhecidos com idf máximo): fora do tema de 0 a 0,130 (11 consultas); dentro do tema, com vocabulário do texto, de 0,180 a 0,625 (14 consultas). Limiar 0,15.
- "transição ICMS ISS extinção" (0,091) e "split payment recolhimento" (0,120) ficam abaixo: a EC não usa essas palavras.

## Review Focus

- Consulta vazia, só de palavras vazias ou sem termos no corpus devolve `found=False` com motivo explícito, nunca exceção (teste `test_not_found_has_explicit_reason`).
- Uma palavra conhecida no meio de várias desconhecidas não passa o limiar (teste `test_one_known_word_among_many_unknown_is_below_threshold` e os 10 casos de `OFF_TOPIC`).
- Versões do mesmo id viram um resultado só, e o texto de qualquer versão conta (teste `test_versions_are_grouped_in_one_hit_and_both_texts_count`).
- `156-A` é um termo só (teste `test_tokenize_normalizes_accents_plural_and_stopwords` e `test_article_number_with_letter`).
- O `dispositivos.json` versionado continua igual ao build de hoje, agora com o cabeçalho (testes `test_header_fonte_matches_the_meta` e `test_committed_dispositivos_is_exactly_what_build_generates_today`).

---

### Task 1: Cabeçalho `fonte` no dispositivos.json

**Files:**
- Modify: `src/taxlaw/ingest/build.py`
- Modify: `tests/test_build.py`
- Modify: `tests/test_build_real.py`
- Modify: `corpus/dispositivos.json`

**Interfaces:**
- Consumes: o build do passo 07.
- Produces: `corpus/dispositivos.json` no formato `{"fonte": {"url", "coletado_em", "sha256_html"}, "dispositivos": [registros com 14 campos]}` (os 16 da spec menos `fonte_url` e `coletado_em`). `render(records, effects, meta)` agora exige `meta["sha256"]`.

- [ ] **Step 1: testes que falham.** Substitua `tests/test_build.py` inteiro por:

```python
"""Testes do build (passo 07): correções, estrutura mínima, render e CLI.

As partes puras usam dados sintéticos. Os testes da CLI usam o corpus/raw
real como entrada (só leitura) e gravam sempre em tmp_path.
"""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from taxlaw.ingest.build import (
    BuildError,
    Correction,
    apply_corrections,
    check_minimum,
    load_corrections,
    main,
    render,
)
from taxlaw.ingest.effects import Effects
from taxlaw.ingest.structure import Record

RAW_DIR = Path(__file__).resolve().parents[1] / "corpus" / "raw"
PUB = date(2023, 12, 21)
AUTO = Effects(PUB, PUB, None, "EC 132/2023, art. 23, III", "automatico")


def rec(rid: str, art: int = 1, pai: str | None = None) -> Record:
    return Record(rid, f"citação de {rid}", rid.split(".", 1)[0], pai, f"EC132.art{art}", f"EC 132/2023, art. {art}º", "incluido", "texto sintético")


# ---------------------------------------------------------------- correções


def test_empty_or_commented_file_has_no_corrections():
    assert load_corrections("") == []
    assert load_corrections("# só comentário\ncorrecoes: []\n") == []


def test_valid_correction_accepts_dates_with_or_without_quotes():
    text = """
correcoes:
  - id: CF.art10
    versao: EC132.art1
    efeitos_desde: 2024-01-01
    efeitos_ate: "2025-12-31"
    fundamento: "fundamento sintético"
"""
    assert load_corrections(text) == [Correction("CF.art10", "EC132.art1", date(2024, 1, 1), date(2025, 12, 31), "fundamento sintético")]


def test_invalid_corrections_report_every_problem_at_once():
    text = """
correcoes:
  - id: CF.art10
    versao: EC132.art1
    efeitos_desde: 2024-01-01
    fundamento: "   "
  - id: CF.art11
    versao: EC132.art1
    efeitos_desde: 2026-01-01
    efeitos_ate: 2025-01-01
    fundamento: f
    observacao: campo que não existe
  - id: CF.art12
    versao: EC132.art1
    efeitos_desde: "31/12/2025"
    fundamento: f
  - id: CF.art12
    versao: EC132.art1
    fundamento: f
  - versao: EC132.art1
    fundamento: f
"""
    with pytest.raises(BuildError) as exc:
        load_corrections(text)
    assert exc.value.errors == [
        "correção 1 (CF.art10, EC132.art1): 'fundamento' é obrigatório",
        "correção 2: campo desconhecido observacao",
        "correção 2 (CF.art11, EC132.art1): efeitos_ate antes de efeitos_desde",
        "correção 3: data inválida '31/12/2025' (use AAAA-MM-DD ou null)",
        "correção 4 (CF.art12, EC132.art1): correção duplicada",
        "correção 5: 'id' e 'versao' são obrigatórios",
    ]


def test_wrong_top_level_shape_is_an_error():
    with pytest.raises(BuildError) as exc:
        load_corrections("- id: CF.art10\n")
    assert exc.value.errors == ["efeitos_correcoes.yaml: esperado 'correcoes:' com uma lista"]


def test_correction_wins_over_automatic():
    by_version = {("CF.art10", "EC132.art1"): AUTO, ("CF.art11", "EC132.art1"): AUTO}
    fixed = apply_corrections(by_version, [Correction("CF.art10", "EC132.art1", date(2024, 1, 1), date(2025, 12, 31), "fundamento sintético")])
    assert fixed[("CF.art10", "EC132.art1")] == Effects(
        date(2024, 1, 1), date(2024, 1, 1), date(2025, 12, 31), "fundamento sintético", "correcao", "fundamento sintético"
    )
    assert fixed[("CF.art11", "EC132.art1")] == AUTO
    assert by_version[("CF.art10", "EC132.art1")] == AUTO  # a entrada não é alterada


def test_correction_for_unknown_version_is_an_error():
    with pytest.raises(BuildError) as exc:
        apply_corrections({("CF.art10", "EC132.art1"): AUTO}, [Correction("CF.art10", "EC132.art3", None, None, "f")])
    assert exc.value.errors == ["correção para versão inexistente: CF.art10 (EC132.art3)"]


# ---------------------------------------------------------- estrutura mínima


def test_minimum_structure():
    complete = [rec(i) for i in ("CF.art149-B", "CF.art156-A", "ADCT.art125")] + [rec(f"EC132.art{n}", n) for n in range(1, 24)]
    assert check_minimum(complete) == []
    missing = [r for r in complete if r.id not in ("CF.art156-A", "EC132.art7")]
    assert check_minimum(missing) == ["estrutura mínima ausente: CF.art156-A", "artigo da EC ausente: EC132.art7"]


# -------------------------------------------------------------------- render

META = {"url": "https://exemplo.invalid/ec", "coletado_em": "2026-11-06", "sha256": "ab" * 32}


def test_render_orders_by_id_then_ec_article_and_uses_spec_fields():
    records = [rec("CF.art10", 10), rec("CF.art10", 3), rec("ADCT.art1", 2)]
    effects = {(r.id, r.versao): AUTO for r in records}
    document = json.loads(render(records, effects, META))
    assert document["fonte"] == {"url": "https://exemplo.invalid/ec", "coletado_em": "2026-11-06", "sha256_html": "ab" * 32}
    rows = document["dispositivos"]
    # art. 3 antes do art. 10: ordem numérica, não alfabética ("art10" < "art3" como texto)
    assert [(r["id"], r["versao"]) for r in rows] == [("ADCT.art1", "EC132.art2"), ("CF.art10", "EC132.art3"), ("CF.art10", "EC132.art10")]
    assert list(rows[0]) == [
        "id", "citacao", "norma", "pai", "versao", "origem", "alteracao", "texto", "vigor_desde", "efeitos_desde",
        "efeitos_ate", "fundamento_efeitos", "fundamento_ate", "metodo",
    ]
    assert rows[0]["efeitos_desde"] == "2023-12-21" and rows[0]["efeitos_ate"] is None


def test_render_is_byte_stable_and_keeps_accents():
    records = [rec("CF.art10")]
    text = render(records, {(r.id, r.versao): AUTO for r in records}, META)
    assert text == render(records, {(r.id, r.versao): AUTO for r in records}, META)
    assert "citação" in text and text.endswith("}\n")


# ----------------------------------------------------------------------- CLI


def run(tmp_path: Path, *extra: str, raw_dir: Path = RAW_DIR, corrections: str = "correcoes: []\n") -> int:
    corrections_path = tmp_path / "efeitos_correcoes.yaml"
    corrections_path.write_text(corrections, encoding="utf-8")
    return main(["--raw-dir", str(raw_dir), "--corrections", str(corrections_path), "--output", str(tmp_path / "out.json"), *extra])


def test_cli_writes_report_and_file(tmp_path, capsys):
    assert run(tmp_path) == 0
    out = capsys.readouterr().out
    assert "dispositivos: 487 versões, 474 ids" in out
    assert "indeterminados: 0" in out and "avisos: 0" in out
    document = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert len(document["dispositivos"]) == 487
    assert document["fonte"]["coletado_em"] == "2026-11-06"


def test_cli_is_deterministic_and_check_mode(tmp_path, capsys):
    assert run(tmp_path) == 0
    first = (tmp_path / "out.json").read_bytes()
    assert run(tmp_path) == 0
    assert (tmp_path / "out.json").read_bytes() == first
    assert run(tmp_path, "--check") == 0
    (tmp_path / "out.json").write_text("[]\n", encoding="utf-8")
    assert run(tmp_path, "--check") == 1
    assert (tmp_path / "out.json").read_text(encoding="utf-8") == "[]\n"  # --check não grava
    assert "desatualizado" in capsys.readouterr().err


def test_cli_invalid_correction_aborts_without_writing(tmp_path, capsys):
    bad = "correcoes:\n  - id: CF.art156-A\n    versao: EC132.art1\n    efeitos_desde: 2024-01-01\n"
    assert run(tmp_path, corrections=bad) == 1
    assert not (tmp_path / "out.json").exists()
    assert "'fundamento' é obrigatório" in capsys.readouterr().err


def test_cli_corrupted_source_aborts_without_writing(tmp_path, capsys):
    raw = tmp_path / "raw"
    shutil.copytree(RAW_DIR, raw)
    (raw / "ec132-2023.html").write_bytes(b"corrompido")
    assert run(tmp_path, raw_dir=raw) == 1
    assert not (tmp_path / "out.json").exists()
    assert "sha256" in capsys.readouterr().err


def test_cli_applies_a_real_correction(tmp_path, capsys):
    fix = (
        "correcoes:\n  - id: ADCT.art125\n    versao: EC132.art2\n    efeitos_desde: 2026-01-01\n"
        "    efeitos_ate: null\n    fundamento: \"teste sintético de correção\"\n"
    )
    assert run(tmp_path, corrections=fix) == 0
    assert "correções aplicadas: 1" in capsys.readouterr().out
    rows = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))["dispositivos"]
    row = next(r for r in rows if r["id"] == "ADCT.art125")
    assert (row["efeitos_desde"], row["metodo"], row["fundamento_efeitos"]) == ("2026-01-01", "correcao", "teste sintético de correção")
```

E `tests/test_build_real.py` inteiro por:

```python
"""O corpus versionado (passo 07): em dia com o build e conferido pelo usuário."""

import json
from pathlib import Path

import pytest

from taxlaw.ingest.build import DEFAULT_CORRECTIONS, DEFAULT_OUTPUT, build

ROOT = Path(__file__).resolve().parents[1]
DISPOSITIVOS = ROOT / "corpus" / "dispositivos.json"

# Conferidos à mão pelo usuário contra o texto oficial da EC 132, em 2026-11-07.
# (id, versao): (alteracao, efeitos_desde, efeitos_ate, fundamento_efeitos, fundamento_ate, início do texto)
CHECKED_BY_USER = {
    ("CF.art149-B", "EC132.art1"): ("incluido", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                    "Art. 149-B. Os tributos previstos nos arts. 156-A e 195, V, observarão"),
    ("CF.art155.par3", "EC132.art1"): ("alterado", "2023-12-21", "2032-12-31", "EC 132/2023, art. 23, III", "EC 132/2023, art. 22, II, a",
                                       "§ 3º À exceção dos impostos de que tratam o inciso II do caput"),
    ("CF.art158.incIV.alib", "EC132.art1"): ("alterado", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                             "b) do produto da arrecadação do imposto previsto no art. 156-A"),
    ("CF.art156-A.par1.incIX", "EC132.art1"): ("incluido", "2023-12-21", "2026-12-31", "EC 132/2023, art. 23, III", None,
                                               "IX - não integrará sua própria base de cálculo nem a dos tributos previstos nos arts. 153, VIII, e 195, I, \"b\", IV e V"),
    ("CF.art156-A.par1.incIX", "EC132.art3"): ("alterado", "2027-01-01", "2032-12-31", "EC 132/2023, art. 23, I", None,
                                               "IX - não integrará sua própria base de cálculo nem a dos tributos previstos nos arts. 153, VIII, e 195, V;"),
    ("CF.art156-A.par1.incIX", "EC132.art4"): ("alterado", "2033-01-01", None, "EC 132/2023, art. 23, II", None,
                                               "IX - não integrará sua própria base de cálculo nem a dos tributos previstos nos arts. 153, VIII, e 195, V;"),
    ("ADCT.art125", "EC132.art2"): ("incluido", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                    "Art. 125. Em 2026, o imposto previsto no art. 156-A será cobrado à alíquota estadual de 0,1%"),
    ("ADCT.art82.par2", "EC132.art5"): ("alterado", "2033-01-01", None, "EC 132/2023, art. 23, II", None, "§ 2º (Revogado)."),
    ("EC132.art11", "EC132.art11"): ("original", "2027-01-01", None, "EC 132/2023, art. 23, I", None,
                                     "Art. 11. A revogação do art. 195, I, \"b\", não produzirá efeitos"),
    ("EC132.art12", "EC132.art12"): ("original", "2023-12-21", None, "EC 132/2023, art. 23, III", None,
                                     "Art. 12.Fica instituído o Fundo de Compensação de Benefícios Fiscais"),
}


@pytest.fixture(scope="module")
def document():
    return json.loads(DISPOSITIVOS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(document):
    return {(r["id"], r["versao"]): r for r in document["dispositivos"]}


def test_header_fonte_matches_the_meta(document):
    meta = json.loads((ROOT / "corpus" / "raw" / "ec132-2023.meta.json").read_text(encoding="utf-8"))
    assert document["fonte"] == {"url": meta["url"], "coletado_em": meta["coletado_em"], "sha256_html": meta["sha256"]}
    assert document["fonte"]["url"].startswith("https://www.planalto.gov.br/")


def test_default_paths_point_to_the_repo_corpus():
    assert DEFAULT_OUTPUT == DISPOSITIVOS
    assert DEFAULT_CORRECTIONS == ROOT / "corpus" / "efeitos_correcoes.yaml"


def test_committed_dispositivos_is_exactly_what_build_generates_today():
    # Se falhar: alguém mudou parser, effects, correções ou o HTML e não rodou o build.
    fresh = build(ROOT / "corpus" / "raw", DEFAULT_CORRECTIONS.read_text(encoding="utf-8"))
    assert DISPOSITIVOS.read_text(encoding="utf-8") == fresh.text


def test_cases_checked_by_user(rows):
    for key, (alteracao, desde, ate, fundamento, fundamento_ate, start) in CHECKED_BY_USER.items():
        row = rows[key]
        assert (row["alteracao"], row["efeitos_desde"], row["efeitos_ate"]) == (alteracao, desde, ate), key
        assert (row["fundamento_efeitos"], row["fundamento_ate"]) == (fundamento, fundamento_ate), key
        assert row["texto"].startswith(start), key


def test_corpus_invariants(rows):
    assert len(rows) == 487
    for (rid, versao), row in rows.items():
        assert row["metodo"] in {"automatico", "correcao", "indeterminado"}, rid
        assert "fonte_url" not in row and "coletado_em" not in row, rid
        if row["metodo"] == "indeterminado":
            assert row["efeitos_desde"] is None, rid
        if row["efeitos_ate"] is not None:
            assert row["efeitos_ate"] >= row["efeitos_desde"], rid
```

`uv run pytest tests/test_build.py tests/test_build_real.py -v` → falham os testes de formato.

- [ ] **Step 2: implemente.** Substitua `src/taxlaw/ingest/build.py` inteiro por:

```python
"""Build do corpus: structure + effects + correções → corpus/dispositivos.json.

Uso:
    uv run python -m taxlaw.ingest.build            # gera e imprime o relatório
    uv run python -m taxlaw.ingest.build --check    # só confere se o arquivo está em dia

Regras (spec, seção 5):
- lê `coletado_em` e a URL do `.meta.json`, nunca do relógio;
- aborta, sem gravar nada, se o HTML não bater com o sha256 do meta, se o
  structure tiver erros, se faltar a estrutura mínima ou se alguma correção
  for inválida;
- correções de `efeitos_correcoes.yaml` vencem o automático e exigem
  `fundamento`;
- saída determinística: mesma entrada, mesmos bytes (o teste confere que o
  `dispositivos.json` versionado é exatamente o que o build gera hoje);
- `fonte_url` e `coletado_em` ficam uma vez só, no cabeçalho `fonte` (spec,
  seção 5, decisão de 2026-11-07): repetidos em cada registro, uma recoleta
  que muda uma vírgula mudaria 487 linhas e esconderia a mudança no diff.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

import yaml

from taxlaw.ingest.effects import Effects, effects_for, find_publication_date
from taxlaw.ingest.fetch import DEFAULT_RAW_DIR, SOURCE_NAME, paths_for, verify
from taxlaw.ingest.structure import Record, decode_html, paragraphs, parse

CORPUS_DIR = DEFAULT_RAW_DIR.parent
DEFAULT_CORRECTIONS = CORPUS_DIR / "efeitos_correcoes.yaml"
DEFAULT_OUTPUT = CORPUS_DIR / "dispositivos.json"

# Dispositivos que a EC traz por inteiro (novos) e o art. 23: se faltar
# algum, o corpus está quebrado, mesmo que o parser não reclame. (O caput do
# art. 195 não serve: no texto da EC ele aparece só como linha de pontos.)
MINIMUM_IDS = ("CF.art149-B", "CF.art156-A", "ADCT.art125", "EC132.art23")
EC_ARTICLES = range(1, 24)

_CORRECTION_KEYS = {"id", "versao", "efeitos_desde", "efeitos_ate", "fundamento"}


class BuildError(Exception):
    """Motivos para não gravar nada. Cada item é uma linha do relatório."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Correction:
    id: str
    versao: str
    efeitos_desde: date | None
    efeitos_ate: date | None
    fundamento: str


@dataclass
class BuildResult:
    text: str  # conteúdo de dispositivos.json
    report: list[str] = field(default_factory=list)


def _as_date(value: object, where: str, errors: list[str]) -> date | None:
    """YAML devolve `date` para 2027-01-01 sem aspas e `str` com aspas: aceita os dois."""
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    errors.append(f"{where}: data inválida {value!r} (use AAAA-MM-DD ou null)")
    return None


def load_corrections(text: str) -> list[Correction]:
    """Lê o YAML de correções. Junta todos os problemas antes de falhar."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict) or not isinstance(data.get("correcoes", []), list):
        raise BuildError(["efeitos_correcoes.yaml: esperado 'correcoes:' com uma lista"])
    errors: list[str] = []
    corrections: list[Correction] = []
    seen: set[tuple[str, str]] = set()
    for n, item in enumerate(data.get("correcoes") or [], start=1):
        where = f"correção {n}"
        if not isinstance(item, dict):
            errors.append(f"{where}: esperado um mapa com id, versao, efeitos_desde, efeitos_ate, fundamento")
            continue
        unknown = sorted(set(item) - _CORRECTION_KEYS)
        if unknown:
            errors.append(f"{where}: campo desconhecido {', '.join(unknown)}")
        rid, versao = item.get("id"), item.get("versao")
        if not isinstance(rid, str) or not isinstance(versao, str):
            errors.append(f"{where}: 'id' e 'versao' são obrigatórios")
            continue
        fundamento = item.get("fundamento")
        if not isinstance(fundamento, str) or not fundamento.strip():
            errors.append(f"{where} ({rid}, {versao}): 'fundamento' é obrigatório")
        desde = _as_date(item.get("efeitos_desde"), where, errors)
        ate = _as_date(item.get("efeitos_ate"), where, errors)
        if desde and ate and ate < desde:
            errors.append(f"{where} ({rid}, {versao}): efeitos_ate antes de efeitos_desde")
        if (rid, versao) in seen:
            errors.append(f"{where} ({rid}, {versao}): correção duplicada")
        seen.add((rid, versao))
        corrections.append(Correction(rid, versao, desde, ate, str(fundamento or "").strip()))
    if errors:
        raise BuildError(errors)
    return corrections


def apply_corrections(
    by_version: dict[tuple[str, str], Effects], corrections: list[Correction]
) -> dict[tuple[str, str], Effects]:
    """Correção vence o automático. Correção para versão inexistente é erro."""
    errors = [f"correção para versão inexistente: {c.id} ({c.versao})" for c in corrections if (c.id, c.versao) not in by_version]
    if errors:
        raise BuildError(errors)
    out = dict(by_version)
    for c in corrections:
        out[(c.id, c.versao)] = Effects(
            vigor_desde=c.efeitos_desde,
            efeitos_desde=c.efeitos_desde,
            efeitos_ate=c.efeitos_ate,
            fundamento=c.fundamento,
            metodo="correcao",
            fundamento_ate=c.fundamento if c.efeitos_ate else None,
        )
    return out


def check_minimum(records: list[Record]) -> list[str]:
    """Estrutura mínima esperada: se faltar, o parser perdeu algo grande."""
    ids = {r.id for r in records}
    errors = [f"estrutura mínima ausente: {rid}" for rid in MINIMUM_IDS if rid not in ids]
    errors += [f"artigo da EC ausente: EC132.art{n}" for n in EC_ARTICLES if f"EC132.art{n}" not in ids]
    return errors


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def render(records: list[Record], effects: dict[tuple[str, str], Effects], meta: dict) -> str:
    """JSON determinístico: cabeçalho `fonte` + registros ordenados por (id, artigo da EC)."""
    ordered = sorted(records, key=lambda r: (r.id, int(r.versao.removeprefix("EC132.art"))))
    rows = []
    for r in ordered:
        e = effects[(r.id, r.versao)]
        rows.append({
            "id": r.id,
            "citacao": r.citacao,
            "norma": r.norma,
            "pai": r.pai,
            "versao": r.versao,
            "origem": r.origem,
            "alteracao": r.alteracao,
            "texto": r.texto,
            "vigor_desde": _iso(e.vigor_desde),
            "efeitos_desde": _iso(e.efeitos_desde),
            "efeitos_ate": _iso(e.efeitos_ate),
            "fundamento_efeitos": e.fundamento,
            "fundamento_ate": e.fundamento_ate,
            "metodo": e.metodo,
        })
    document = {
        "fonte": {"url": meta["url"], "coletado_em": meta["coletado_em"], "sha256_html": meta["sha256"]},
        "dispositivos": rows,
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def build(raw_dir: Path, corrections_text: str) -> BuildResult:
    """Pipeline inteiro em memória. Levanta BuildError em vez de gravar algo errado."""
    html_path, meta_path = paths_for(raw_dir, SOURCE_NAME)
    if not verify(raw_dir, SOURCE_NAME):
        raise BuildError([f"{html_path.name} ausente ou diferente do sha256 em {meta_path.name}"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    html = decode_html(html_path.read_bytes())

    parsed = parse(html)
    errors = list(parsed.errors) + check_minimum(parsed.records)
    if errors:
        raise BuildError(errors)
    result = effects_for(parsed.records, find_publication_date(t for _, t in paragraphs(html)))
    corrections = load_corrections(corrections_text)
    effects = apply_corrections(result.by_version, corrections)

    methods = Counter(e.metodo for e in effects.values())
    indeterminate = sorted(f"{rid} ({versao})" for (rid, versao), e in effects.items() if e.metodo == "indeterminado")
    report = [
        f"dispositivos: {len(parsed.records)} versões, {len({r.id for r in parsed.records})} ids",
        "por norma: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.norma for r in parsed.records).items())),
        "por método: " + ", ".join(f"{k} {v}" for k, v in sorted(methods.items())),
        f"correções aplicadas: {len(corrections)}",
        f"revogações (art. 22): {len(result.revocations)}",
        f"indeterminados: {len(indeterminate)}",
        *[f"  - {i}" for i in indeterminate],
        f"avisos: {len(parsed.warnings) + len(result.warnings)}",
        *[f"  - {w}" for w in parsed.warnings + result.warnings],
    ]
    return BuildResult(text=render(parsed.records, effects, meta), report=report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taxlaw.ingest.build")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="não grava; sai com 1 se o arquivo estiver desatualizado")
    args = parser.parse_args(argv)

    try:
        corrections_text = args.corrections.read_text(encoding="utf-8") if args.corrections.is_file() else ""
        result = build(args.raw_dir, corrections_text)
    except BuildError as exc:
        print("build abortado; nada foi gravado:", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("\n".join(result.report))
    current = args.output.read_text(encoding="utf-8") if args.output.is_file() else None
    if args.check:
        if current == result.text:
            print(f"{args.output.name} em dia")
            return 0
        print(f"{args.output.name} desatualizado: rode o build sem --check", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.text, encoding="utf-8")
    print(f"gravado: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: regenere o corpus.** `uv run python -m taxlaw.ingest.build`. O relatório deve ser idêntico ao do passo 07 (487 versões, 474 ids, 0 indeterminados, 0 avisos) e `corpus/dispositivos.json` deve ficar com 7.801 linhas, começando por `{"fonte": ...`. Se algum número mudar, pare e reporte.

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_build.py tests/test_build_real.py -v` → 19 passed; `uv run python -m taxlaw.ingest.build --check` → `dispositivos.json em dia`.

- [ ] **Step 5: commit.** `git add src/taxlaw/ingest/build.py tests/test_build.py tests/test_build_real.py corpus/dispositivos.json` e `git commit -m "feat(step-08): cabeçalho fonte no dispositivos.json"`.

### Task 2: Leitor do corpus e busca com limiar

**Files:**
- Create: `src/taxlaw/corpus.py`
- Create: `src/taxlaw/search.py`
- Test: `tests/test_search.py`
- Test: `tests/test_search_real.py`
- Create: `docs/steps/08-search.md`

**Depends on:** Task 1

**Interfaces:**
- Consumes: `corpus/dispositivos.json` no formato da Task 1.
- Produces (usados pelas ferramentas no passo 09): `DEFAULT_PATH`; `Corpus(fonte: dict, dispositivos: tuple[dict, ...], versao: str)` com `ids() -> list[str]` e `versions(rid) -> list[dict]`; `load_corpus(path=DEFAULT_PATH) -> Corpus`; `THRESHOLD = 0.15`; `tokenize(text) -> list[str]`; `Hit(id, score, relevance)`; `SearchResult(found: bool, hits: list[Hit], reason: str | None)`; `Index`; `build_index(corpus) -> Index`; `score_all(index, query) -> list[Hit]`; `search(index, query, limit=5) -> SearchResult` (levanta `ValueError` se `limit` fora de 1..10).

- [ ] **Step 1: testes que falham.** Crie `tests/test_search.py`:

```python
"""Testes de corpus e search (passo 08) com um corpus sintético pequeno."""

import hashlib
import json

import pytest

from taxlaw.corpus import load_corpus
from taxlaw.search import THRESHOLD, build_index, score_all, search, tokenize


def row(rid: str, texto: str, versao: str = "EC132.art1") -> dict:
    return {"id": rid, "citacao": rid.replace(".", ", "), "versao": versao, "texto": texto}


ROWS = [
    row("CF.art1", "Texto sintético sobre o imposto de exemplo e suas alíquotas."),
    row("CF.art2", "Operações com mercadorias sintéticas e créditos do imposto."),
    row("CF.art2", "Operação com mercadoria sintética, redação nova e crédito.", "EC132.art3"),
    row("CF.art3", "Disposição sintética sobre fundos regionais de compensação."),
    row("CF.art156-A", "Artigo sintético numerado com letra."),
]


@pytest.fixture
def corpus(tmp_path):
    path = tmp_path / "dispositivos.json"
    path.write_text(json.dumps({"fonte": {"url": "https://exemplo.invalid", "coletado_em": "2026-11-06", "sha256_html": "0" * 64},
                                "dispositivos": ROWS}, ensure_ascii=False), encoding="utf-8")
    return load_corpus(path), path


def test_load_corpus_header_versions_and_hash(corpus):
    c, path = corpus
    assert c.fonte["coletado_em"] == "2026-11-06"
    assert c.versao == hashlib.sha256(path.read_bytes()).hexdigest()
    assert c.ids() == ["CF.art1", "CF.art156-A", "CF.art2", "CF.art3"]
    assert [v["versao"] for v in c.versions("CF.art2")] == ["EC132.art1", "EC132.art3"]
    assert c.versions("CF.art999") == []


def test_tokenize_normalizes_accents_plural_and_stopwords():
    assert tokenize("As Operações com Créditos do Imposto") == ["operacao", "credito", "imposto"]
    assert tokenize("alíquotas reduzidas") == ["aliquota", "reduzida"]
    assert tokenize("art. 156-A") == ["156-a"]
    assert tokenize("de da do e ou") == []


def test_versions_are_grouped_in_one_hit_and_both_texts_count(corpus):
    c, _ = corpus
    hits = score_all(build_index(c), "redação nova")
    assert [h.id for h in hits] == ["CF.art2"]  # termo só da versão do art. 3, um resultado só


def test_ranking_and_ties_are_deterministic(corpus):
    c, _ = corpus
    index = build_index(c)
    assert [h.id for h in score_all(index, "crédito mercadoria")][:1] == ["CF.art2"]
    assert score_all(index, "sintético") == score_all(index, "sintético")
    tied = [h for h in score_all(index, "sintético") if h.score == score_all(index, "sintético")[0].score]
    assert [h.id for h in tied] == sorted(h.id for h in tied)


def test_search_finds_with_relevance_between_threshold_and_one(corpus):
    c, _ = corpus
    result = search(build_index(c), "fundos regionais de compensação")
    assert result.found and result.reason is None
    assert result.hits[0].id == "CF.art3"
    assert all(THRESHOLD <= h.relevance <= 1 for h in result.hits)


def test_article_number_with_letter(corpus):
    c, _ = corpus
    assert search(build_index(c), "art. 156-A").hits[0].id == "CF.art156-A"


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("", "a consulta não tem termos pesquisáveis"),
        ("de da do", "a consulta não tem termos pesquisáveis"),
        ("futebol churrasco", "nenhum dispositivo contém os termos da consulta"),
    ],
)
def test_not_found_has_explicit_reason(corpus, query, reason):
    c, _ = corpus
    result = search(build_index(c), query)
    assert (result.found, result.hits, result.reason) == (False, [], reason)


def test_one_known_word_among_many_unknown_is_below_threshold(corpus):
    c, _ = corpus
    result = search(build_index(c), "receita de bolo de chocolate com imposto e cobertura de morango")
    assert not result.found
    assert result.reason.startswith("relevância máxima ") and result.reason.endswith(f"abaixo do limiar {THRESHOLD}")


def test_limit_is_respected_and_validated(corpus):
    c, _ = corpus
    index = build_index(c)
    assert len(search(index, "sintético", limit=1).hits) == 1
    with pytest.raises(ValueError):
        search(index, "sintético", limit=0)
    with pytest.raises(ValueError):
        search(index, "sintético", limit=11)
```

E `tests/test_search_real.py`:

```python
"""Calibração do limiar de busca no corpus real (passo 08).

Consultas medidas em 2026-11-07 (ver docstring de taxlaw.search): dentro do
tema, o dispositivo esperado aparece entre os 5 primeiros; fora do tema, a
resposta é "não encontrei". Se mudar o tokenizador, o BM25 ou o limiar, estes
casos dizem se a calibração continua de pé.
"""

import pytest

from taxlaw.corpus import load_corpus
from taxlaw.search import build_index, search


@pytest.fixture(scope="module")
def index():
    return build_index(load_corpus())


ON_TOPIC = {
    "imposto sobre bens e serviços": "CF.art156-A",
    "alíquota do IBS em 2026": "ADCT.art125",
    "imposto seletivo produtos prejudiciais à saúde": "CF.art153.incVIII",
    "Fundo de Compensação de Benefícios Fiscais": "EC132.art12",
    "devolução do imposto a pessoas físicas": "CF.art156-A.par5.incVIII",
    "zona franca de manaus": "ADCT.art92-B",
    "art. 156-A": "CF.art156-A",
    "imposto sobre heranças e doações progressivo": "CF.art155.par1.incVI",
    "regimes específicos de tributação combustíveis": "CF.art149-B.incIII",
}

OFF_TOPIC = [
    "receita de bolo de chocolate",
    "campeonato brasileiro de futebol",
    "previsão do tempo para amanhã",
    "como trocar o pneu do carro",
    "horário de funcionamento do banco",
    "divórcio guarda dos filhos",
    "aposentadoria por tempo de contribuição do INSS",
    "multa de trânsito por excesso de velocidade",
    "pena para homicídio culposo",
    "como abrir uma conta corrente",
]

# Do tema, mas com palavras que o texto da EC não usa: "não encontrei" é o
# honesto. Reformular ("art. 155, II") é papel da skill (passo 12).
VOCABULARY_GAPS = ["transição ICMS ISS extinção", "split payment recolhimento"]


@pytest.mark.parametrize(("query", "expected"), ON_TOPIC.items())
def test_on_topic_query_finds_expected_dispositivo_in_top_5(index, query, expected):
    result = search(index, query)
    assert result.found, result.reason
    assert expected in [h.id for h in result.hits], [h.id for h in result.hits]


@pytest.mark.parametrize("query", OFF_TOPIC)
def test_off_topic_query_is_not_found(index, query):
    result = search(index, query)
    assert not result.found and result.hits == []


@pytest.mark.parametrize("query", VOCABULARY_GAPS)
def test_vocabulary_absent_from_the_text_is_not_found(index, query):
    assert not search(index, query).found


def test_search_is_deterministic(index):
    assert search(index, "imposto sobre bens e serviços") == search(index, "imposto sobre bens e serviços")
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_search.py tests/test_search_real.py -v` → erro de import (`taxlaw.corpus` não existe).

- [ ] **Step 3: implemente.** Crie `src/taxlaw/corpus.py`:

```python
"""Leitura de `corpus/dispositivos.json` (gerado pelo build): só leitura, sem rede.

`versao` é o sha256 do arquivo: toda resposta das ferramentas o expõe como
`corpus.versao`, e o P3 sabe se duas execuções usaram o mesmo corpus.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# src/taxlaw/corpus.py → parents[2] é a raiz do repositório.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "corpus" / "dispositivos.json"


@dataclass(frozen=True)
class Corpus:
    fonte: dict
    dispositivos: tuple[dict, ...]
    versao: str
    _by_id: dict[str, list[dict]] = field(default_factory=dict, repr=False, compare=False)

    def ids(self) -> list[str]:
        """Ids distintos, em ordem."""
        return sorted(self._by_id)

    def versions(self, rid: str) -> list[dict]:
        """Versões de um id na ordem do arquivo (artigo da EC crescente); [] se não existe."""
        return list(self._by_id.get(rid, []))


def load_corpus(path: Path = DEFAULT_PATH) -> Corpus:
    raw = path.read_bytes()
    document = json.loads(raw)
    by_id: dict[str, list[dict]] = defaultdict(list)
    for row in document["dispositivos"]:
        by_id[row["id"]].append(row)
    return Corpus(
        fonte=document["fonte"],
        dispositivos=tuple(document["dispositivos"]),
        versao=hashlib.sha256(raw).hexdigest(),
        _by_id=dict(by_id),
    )
```

E `src/taxlaw/search.py`:

```python
"""Busca BM25 sobre o corpus, com limiar: "não encontrei" é resposta válida.

Um documento por `id` (spec, seção 6: a busca agrupa as versões): citação +
textos distintos de todas as versões. Escolher a versão pela data é trabalho
das ferramentas (passo 09), não da busca.

Limiar: a pontuação BM25 absoluta não separa consultas do tema das de fora
(medido em 2026-11-07: "art. 156-A" dá 2,2 e "horário de funcionamento do
banco" dá 5,8). Por isso o corte usa a **relevância** = pontuação / teto da
consulta, em que o teto soma idf × (K1 + 1) de cada termo da consulta, e
termos que não existem no corpus entram com o idf máximo. Medido: fora do
tema até 0,130; dentro do tema, com vocabulário do texto, a partir de 0,180.
Limiar 0,15. Consultas com palavras que a EC não usa ("ICMS", "split
payment") ficam abaixo: "não encontrei" é honesto, e reformular é papel da
skill (passo 12).

Tudo determinístico: mesma consulta, mesmo resultado, empates pelo id. O texto
das normas é tratado só como dado a pontuar; nada nele é interpretado.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from taxlaw.corpus import Corpus

K1 = 1.5
B = 0.75
THRESHOLD = 0.15

# Palavras vazias do português jurídico: aparecem em quase todo dispositivo e
# só diluiriam a pontuação.
STOPWORDS = frozenset(
    "a o as os um uma uns umas de da do das dos em na no nas nos por pela pelo pelas pelos para "
    "com sem sob sobre e ou que se seu sua seus suas ao aos a as este esta estes estas esse essa "
    "isso isto ele ela eles elas como mais menos ja nao sim ser sera serao sao e foi art arts "
    "inciso incisos alinea paragrafo caput lei forma termos qual quais quando onde".split()
)

# Plural → singular, só o necessário para "operações" achar "operação".
_PLURALS = (("coes", "cao"), ("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("res", "r"), ("s", ""))


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _singular(token: str) -> str:
    if token[0].isdigit() or len(token) <= 3 or token.endswith("ss"):
        return token
    for ending, replacement in _PLURALS:
        if token.endswith(ending) and len(token) - len(ending) >= 3:
            return token[: -len(ending)] + replacement
    return token


def tokenize(text: str) -> list[str]:
    """Minúsculas, sem acento, sem palavra vazia, plural no singular; '156-A' fica junto."""
    plain = _strip_accents(text).lower()
    tokens = re.findall(r"\d+(?:-[a-z])?|[a-z]+", plain)
    return [_singular(t) for t in tokens if t not in STOPWORDS]


@dataclass(frozen=True)
class Hit:
    id: str
    score: float  # BM25 bruto
    relevance: float = 0.0  # score / teto da consulta, entre 0 e 1


@dataclass(frozen=True)
class SearchResult:
    found: bool
    hits: list[Hit]
    reason: str | None = None  # por que não encontrou (None quando encontrou)


@dataclass
class Index:
    ids: list[str]
    term_freqs: list[Counter]
    lengths: list[int]
    idf: dict[str, float] = field(default_factory=dict)
    avg_length: float = 0.0
    max_idf: float = 0.0  # idf de um termo que não existe no corpus


def build_index(corpus: Corpus) -> Index:
    """Um documento por id: citação + textos distintos das versões."""
    ids = corpus.ids()
    term_freqs, lengths = [], []
    for rid in ids:
        versions = corpus.versions(rid)
        texts = dict.fromkeys(v["texto"] for v in versions)  # distintos, em ordem
        tokens = tokenize(versions[0]["citacao"] + " " + " ".join(texts))
        term_freqs.append(Counter(tokens))
        lengths.append(len(tokens))
    n = len(ids)
    doc_freq = Counter(term for tf in term_freqs for term in tf)
    idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in doc_freq.items()}
    max_idf = math.log(1 + (n + 0.5) / 0.5)
    return Index(ids, term_freqs, lengths, idf, sum(lengths) / n if n else 0.0, max_idf)


def score_all(index: Index, query: str) -> list[Hit]:
    """Pontuação BM25 de todos os documentos com pelo menos um termo da consulta."""
    terms = list(dict.fromkeys(tokenize(query)))
    hits = []
    for rid, tf, length in zip(index.ids, index.term_freqs, index.lengths):
        score = 0.0
        for term in terms:
            f = tf.get(term, 0)
            if f:
                norm = f * (K1 + 1) / (f + K1 * (1 - B + B * length / index.avg_length))
                score += index.idf[term] * norm
        if score > 0:
            hits.append(Hit(rid, round(score, 6)))
    return sorted(hits, key=lambda h: (-h.score, h.id))


def search(index: Index, query: str, limit: int = 5) -> SearchResult:
    """Até `limit` ids acima do limiar de relevância, ou `found=False` com o motivo."""
    if not 1 <= limit <= 10:
        raise ValueError("limit deve estar entre 1 e 10")
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        return SearchResult(False, [], "a consulta não tem termos pesquisáveis")
    hits = score_all(index, query)
    if not hits:
        return SearchResult(False, [], "nenhum dispositivo contém os termos da consulta")
    ceiling = sum(index.idf.get(t, index.max_idf) * (K1 + 1) for t in terms)
    ranked = [Hit(h.id, h.score, round(h.score / ceiling, 3)) for h in hits]
    relevant = [h for h in ranked if h.relevance >= THRESHOLD]
    if not relevant:
        return SearchResult(False, [], f"relevância máxima {ranked[0].relevance} abaixo do limiar {THRESHOLD}")
    return SearchResult(True, relevant[:limit])
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_search.py tests/test_search_real.py -v` → 33 passed.

- [ ] **Step 5: nota do passo.** Crie `docs/steps/08-search.md`:

```markdown
# Passo 08: cabeçalho `fonte` e busca com limiar

## O que mudou

- **Formato do `corpus/dispositivos.json`:** agora é `{"fonte": {url, coletado_em, sha256_html}, "dispositivos": [...]}`. `fonte_url` e `coletado_em` saíram de cada registro, e o arquivo caiu de 8.768 para 7.801 linhas. Mudaram o `build` e os testes do passo 07.
- `src/taxlaw/corpus.py`: `load_corpus()` lê o arquivo; `Corpus.versao` é o sha256 dele. `ids()` e `versions(id)`.
- `src/taxlaw/search.py`: BM25 com um documento por `id` (citação + textos distintos de todas as versões), tokenizador de português (sem acento, plural no singular, sem palavras vazias, `156-A` junto) e **limiar de relevância 0,15**. Abaixo dele: `found=False` com o motivo.

## Como rodar

    uv run pytest tests/test_search.py tests/test_search_real.py -v

Para brincar:

    uv run python -c "from taxlaw.corpus import load_corpus; from taxlaw.search import build_index, search; ix = build_index(load_corpus()); print(search(ix, 'zona franca de manaus')); print(search(ix, 'receita de bolo de chocolate'))"

## O que observar

- **Pontuação absoluta não serve de limiar:** "art. 156-A" dá 2,2 e "horário de funcionamento do banco" dá 5,8. A **relevância** divide pela pontuação máxima que a consulta poderia ter, contando as palavras que nem existem no corpus como as mais raras possíveis. Medido: fora do tema até 0,130; dentro do tema a partir de 0,180. Limiar 0,15.
- **"Não encontrei" honesto:** "transição ICMS ISS" e "split payment" ficam abaixo do limiar porque a EC não usa essas palavras. Ela diz "o imposto previsto no art. 155, II". Reformular a consulta é trabalho da skill (passo 12), e é um bom caso para o P3.
- **"receita" tem dois sentidos:** "receita de bolo" acha "receita" no sentido tributário. O limiar segura porque "bolo" e "chocolate" puxam a relevância para baixo.
- **A busca não escolhe versão:** devolve o `id`; qual redação vale na data é o passo 09.
- **Cabeçalho `fonte`:** uma recoleta que muda uma vírgula agora muda uma linha de texto e uma de `coletado_em`, não 487.

## Pergunta de previsão

A relevância de "zona franca de manaus" é 0,404, e a de "Comitê Gestor do IBS" é 0,213. Sem rodar: o que acontece com a relevância de "Comitê Gestor do IBS" se você trocar "IBS" por "imposto sobre bens e serviços"? Sobe ou desce, e por quê?
```

- [ ] **Step 6: commit.** `git add src/taxlaw/corpus.py src/taxlaw/search.py tests/test_search.py tests/test_search_real.py docs/steps/08-search.md` e `git commit -m "feat(step-08): leitor do corpus e busca BM25 com limiar"`.

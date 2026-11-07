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

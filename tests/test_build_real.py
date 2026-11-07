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

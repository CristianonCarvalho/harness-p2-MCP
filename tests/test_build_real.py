"""O corpus versionado (passos 07 e 13b): em dia com o build e conferido pelo usuário."""

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


# Conferidos à mão pelo usuário contra o texto oficial da LC 214 no Planalto, em 2026-11-09.
# id: (alteracao, origem, vigor_desde, efeitos_desde, fundamento_efeitos, metodo, início do texto)
LC_CHECKED_BY_USER = {
    "LC214.art125": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico",
                     "Art. 125. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre as vendas de produtos destinados à alimentação humana relacionados no Anexo I"),
    "LC214.art127.incII": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico", "II - advogados;"),
    "LC214.art128.incI": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico", "I - serviços de educação;"),
    "LC214.art126.par6": ("incluido", "LC 214/2025, incluído pela LC 227/2026", None, None, None, "indeterminado",
                          "§ 6º O disposto no § 1º deste artigo não se aplica às remessas internacionais sujeitas ao Regime de Tributação Simplificada (RTS)"),
    "LC214.art142.incII": ("alterado", "LC 214/2025, com redação dada pela LC 227/2026", None, None, None, "indeterminado",
                           "II - fornecimento de serviços de segurança da informação e segurança cibernética"),
    "LC214.art422.par2": ("alterado", "LC 214/2025, com redação dada pela LC 227/2026", None, None, None, "indeterminado",
                          "§ 2º As alíquotas do Imposto Seletivo respeitarão o percentual máximo de 0,25% (vinte e cinco centésimos por cento), nas operações com bens minerais extraídos."),
    "LC214.art419": ("original", "LC 214/2025", "2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI", "automatico",
                     "Art. 419. As alíquotas do Imposto Seletivo aplicáveis aos veículos"),
}


@pytest.fixture(scope="module")
def document():
    return json.loads(DISPOSITIVOS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows(document):
    return {(r["id"], r["versao"]): r for r in document["dispositivos"]}


def test_header_fontes_match_the_metas(document):
    assert list(document["fontes"]) == ["ec132-2023", "lc214-2025"]
    for name, fonte in document["fontes"].items():
        meta = json.loads((ROOT / "corpus" / "raw" / f"{name}.meta.json").read_text(encoding="utf-8"))
        assert fonte == {"url": meta["url"], "coletado_em": meta["coletado_em"], "sha256_html": meta["sha256"]}
        assert fonte["url"].startswith("https://www.planalto.gov.br/")


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


def test_lc_cases_checked_by_user(rows):
    for rid, (alteracao, origem, vigor, desde, fundamento, metodo, start) in LC_CHECKED_BY_USER.items():
        row = rows[(rid, "LC214")]
        assert (row["alteracao"], row["origem"], row["metodo"]) == (alteracao, origem, metodo), rid
        assert (row["vigor_desde"], row["efeitos_desde"], row["efeitos_ate"], row["fundamento_efeitos"]) == (vigor, desde, None, fundamento), rid
        assert row["texto"].startswith(start), rid


def test_ec_rows_are_unchanged_by_the_lc(rows):
    # A LC entrou sem mexer na EC: 487 versões, e as linhas da LC vêm depois de todas as da EC.
    norms = [row["norma"] for row in rows.values()]
    assert sum(n != "LC214" for n in norms) == 487
    assert norms.index("LC214") == 487 and set(norms[487:]) == {"LC214"}


def test_lc_effects_vigor_and_efeitos_separate(rows):
    lc = [row for (rid, versao), row in rows.items() if versao == "LC214"]
    assert len(lc) == 162
    automatic = [row for row in lc if row["metodo"] == "automatico"]
    assert len(automatic) == 158
    # Pela primeira vez no corpus, vigor e efeitos têm datas diferentes.
    assert {(row["vigor_desde"], row["efeitos_desde"], row["fundamento_efeitos"]) for row in automatic} == {
        ("2025-01-16", "2026-01-01", "LC 214/2025, art. 544, VI")
    }
    assert sorted(row["id"] for row in lc if row["metodo"] == "indeterminado") == [
        "LC214.art126.par6", "LC214.art142.incII", "LC214.art422.par2", "LC214.art422.par5",
    ]


def test_corpus_invariants(rows):
    assert len(rows) == 649
    for (rid, versao), row in rows.items():
        assert row["metodo"] in {"automatico", "correcao", "indeterminado"}, rid
        assert "fonte_url" not in row and "coletado_em" not in row, rid
        if row["metodo"] == "indeterminado":
            assert row["efeitos_desde"] is None, rid
        if row["efeitos_ate"] is not None:
            assert row["efeitos_ate"] >= row["efeitos_desde"], rid

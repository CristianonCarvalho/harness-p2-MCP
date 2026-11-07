"""As ferramentas sobre o corpus real (`corpus/dispositivos.json`, só leitura).

Casos medidos em 2026-11-07. `today` é fixo para a suíte não mudar com o
calendário.
"""

import json
from datetime import date

import pytest

from taxlaw.tools import buscar_dispositivos, load_context, obter_dispositivo

TODAY = date(2026, 11, 7)
CTX = load_context()


def obter(rid, when=None, **kwargs):
    return obter_dispositivo(CTX, rid, when, today=TODAY, **kwargs)


@pytest.mark.parametrize(
    ("when", "versao", "others"),
    [
        ("2025-01-01", "EC132.art1", ["EC132.art3", "EC132.art4"]),
        ("2030-06-01", "EC132.art3", ["EC132.art1", "EC132.art4"]),
        ("2040-01-01", "EC132.art4", ["EC132.art1", "EC132.art3"]),
    ],
)
def test_ibs_neutrality_item_ix_changes_with_the_date(when, versao, others):
    out = obter("CF.art156-A.par1.incIX", when)
    assert out["versao"] == versao and out["efeitos"]["produz_efeitos_na_data"] is True
    assert [o["versao"] for o in out["outras_versoes"]] == others


def test_children_of_paragraph_1_follow_the_date_and_legal_order():
    filhos = obter("CF.art156-A.par1", "2030-06-01")["filhos"]
    assert [f["id"].rsplit(".", 1)[1] for f in filhos] == [
        "incI", "incII", "incIII", "incIV", "incV", "incVI", "incVII", "incVIII", "incIX", "incX", "incXI", "incXII", "incXIII",
    ]
    assert {f["id"]: f["versao"] for f in filhos}["CF.art156-A.par1.incIX"] == "EC132.art3"


def test_revoked_device_is_found_with_observation():
    out = obter("CF.art155.par3", "2033-01-01")
    assert out["encontrado"] is True and out["efeitos"]["produz_efeitos_na_data"] is False
    assert out["observacao"] == "revogado a partir de 2033-01-01 (EC 132/2023, art. 22, II, a)"


def test_altered_device_before_the_ec_has_previous_wording_observation():
    out = obter("CF.art195.par17", "2023-12-01")
    assert out["versao"] == "EC132.art1" and out["efeitos"]["produz_efeitos_na_data"] is False
    assert out["observacao"] == "redação anterior não incluída no corpus"


def test_nothing_in_the_real_corpus_hits_the_ceiling():
    # Decisão de 2026-11-07: teto de 4.000 caracteres; o maior real (EC, art. 9º) tem 3.013.
    assert not any(obter(rid)["truncado"] for rid in CTX.corpus.ids())


def test_every_response_carries_the_corpus_hash_and_source():
    out = obter("EC132.art23")
    assert out["corpus"]["versao"] == CTX.corpus.versao and out["fonte_url"].startswith("https://www.planalto.gov.br/")


def test_search_on_topic_and_off_topic():
    found = buscar_dispositivos(CTX, "zona franca de manaus", today=TODAY)
    assert found["encontrado"] is True and found["resultados"][0]["id"] == "ADCT.art126.incIII.alia"
    missing = buscar_dispositivos(CTX, "receita de bolo de chocolate", today=TODAY)
    assert missing["encontrado"] is False and missing["resultados"] == [] and "limiar" in missing["motivo"]


def test_responses_are_json_serializable_and_small():
    biggest = max(len(json.dumps(obter(rid), ensure_ascii=False)) for rid in CTX.corpus.ids())
    assert biggest < 8000
    search = buscar_dispositivos(CTX, "imposto bens serviços", limite=10, today=TODAY)
    assert len(json.dumps(search, ensure_ascii=False)) < 8000

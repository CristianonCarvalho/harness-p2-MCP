"""Testes do contrato das ferramentas (spec, seção 6) com um corpus sintético.

O corpus é escrito em tmp_path no mesmo formato do `dispositivos.json` real.
Os textos são inventados; nenhum CPF/CNPJ válido aparece escrito aqui (os da
guarda são gerados em tempo de execução a partir de bases sintéticas).
"""

import json
from datetime import date

import pytest

from taxlaw.synthetic_ids import make_cnpj, make_cpf
from taxlaw.tools import (
    MAX_CHARS,
    OBS_PREVIOUS_WORDING,
    SNIPPET_CHARS,
    ToolError,
    buscar_dispositivos,
    load_context,
    obter_dispositivo,
)

TODAY = date(2030, 6, 1)


def row(rid, versao, texto, *, pai=None, alteracao="incluido", desde: str | None = "2023-12-21", ate=None, fundamento_ate=None, metodo="automatico", citacao=None):
    return {
        "id": rid,
        "citacao": citacao or rid,
        "norma": rid.split(".")[0],
        "pai": pai,
        "versao": versao,
        "origem": f"EC 132/2023, art. {versao.removeprefix('EC132.art')}",
        "alteracao": alteracao,
        "texto": texto,
        "vigor_desde": desde,
        "efeitos_desde": desde,
        "efeitos_ate": ate,
        "fundamento_efeitos": None if metodo == "indeterminado" else "EC 132/2023, art. 23, III",
        "fundamento_ate": fundamento_ate,
        "metodo": metodo,
    }


ROWS = [
    # Pai com uma versão só; o inciso IX muda em 2027 (art. 3) e não existe mais filho na versão art3 do pai.
    row("XX.art1", "EC132.art1", "Art. 1º O tributo sobre girassóis observará o seguinte:"),
    row("XX.art1.incI", "EC132.art1", "I - alíquota uniforme para girassóis;", pai="XX.art1"),
    row("XX.art1.incII", "EC132.art1", "II - crédito amplo para girassóis;", pai="XX.art1"),
    row("XX.art1.incIX", "EC132.art1", "IX - regime antigo de girassóis;", pai="XX.art1", ate="2026-12-31"),
    row("XX.art1.incIX", "EC132.art3", "IX - regime novo de girassóis;", pai="XX.art1", alteracao="alterado", desde="2027-01-01"),
    row("XX.art1.incV", "EC132.art1", "V - cobrança no destino dos girassóis;", pai="XX.art1"),
    row("XX.art1.par1", "EC132.art1", "§ 1º Lei complementar disporá sobre girassóis.", pai="XX.art1"),
    # Alterado só a partir de 2033: antes disso, "redação anterior".
    row("XX.art2", "EC132.art4", "Art. 2º Tributo das orquídeas em nova redação.", alteracao="alterado", desde="2033-01-01"),
    # Revogado ao fim de 2032.
    row("XX.art3", "EC132.art1", "Art. 3º Tributo das tulipas.", ate="2032-12-31", fundamento_ate="EC 132/2023, art. 22, II, a"),
    # Início indeterminado.
    row("XX.art4", "EC132.art9", "Art. 4º Tributo das begônias.", desde=None, metodo="indeterminado"),
    # Texto longo para trecho e truncamento.
    row("XX.art5", "EC132.art1", "Art. 5º Cactos " + "espinho " * 700),
]


@pytest.fixture
def ctx(tmp_path):
    document = {"fonte": {"url": "https://exemplo.invalid/ec", "coletado_em": "2026-11-06", "sha256_html": "ab" * 32}, "dispositivos": ROWS}
    path = tmp_path / "dispositivos.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return load_context(path)


def busca(ctx, consulta, **kwargs):
    return buscar_dispositivos(ctx, consulta, today=TODAY, **kwargs)


def obter(ctx, rid, **kwargs):
    return obter_dispositivo(ctx, rid, today=TODAY, **kwargs)


# ------------------------------------------------------------------ buscar_dispositivos


def test_search_contract_fields(ctx):
    out = busca(ctx, "girassóis alíquota uniforme")
    assert list(out) == ["encontrado", "consulta", "data_referencia", "resultados", "motivo", "corpus"]
    assert out["encontrado"] is True and out["motivo"] is None
    assert out["consulta"] == "girassóis alíquota uniforme"
    assert out["corpus"]["coletado_em"] == "2026-11-06" and len(out["corpus"]["versao"]) == 64
    first = out["resultados"][0]
    assert list(first) == ["id", "versao", "citacao", "trecho", "pontuacao", "efeitos", "outras_versoes"]
    assert first["id"] == "XX.art1.incI"
    assert list(first["efeitos"]) == ["desde", "ate", "fundamento", "fundamento_ate", "metodo", "produz_efeitos_na_data"]
    assert 0 < first["pontuacao"] <= 1


def test_reference_date_defaults_to_today_and_is_echoed(ctx):
    assert busca(ctx, "girassóis")["data_referencia"] == "2030-06-01"
    assert busca(ctx, "girassóis", data_referencia="2025-01-01")["data_referencia"] == "2025-01-01"


def test_search_groups_versions_and_shows_the_one_of_the_date(ctx):
    def inc9(when):
        out = busca(ctx, "regime girassóis", data_referencia=when, limite=10)
        return next(r for r in out["resultados"] if r["id"] == "XX.art1.incIX")

    early, late = inc9("2025-01-01"), inc9("2030-01-01")
    assert (early["versao"], early["trecho"]) == ("EC132.art1", "IX - regime antigo de girassóis;")
    assert (late["versao"], late["trecho"]) == ("EC132.art3", "IX - regime novo de girassóis;")
    assert late["outras_versoes"] == [{"versao": "EC132.art1", "efeitos": {"desde": "2023-12-21", "ate": "2026-12-31"}}]


def test_search_not_found_is_success_with_reason(ctx):
    out = busca(ctx, "receita de bolo de chocolate")
    assert out["encontrado"] is False and out["resultados"] == []
    assert out["motivo"]


def test_snippet_is_capped(ctx):
    out = busca(ctx, "cactos espinho")
    trecho = out["resultados"][0]["trecho"]
    assert len(trecho) <= SNIPPET_CHARS and trecho.endswith("…")


def test_limit_caps_results(ctx):
    assert len(busca(ctx, "girassóis", limite=2)["resultados"]) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"consulta": ""},
        {"consulta": "   "},
        {"consulta": "a" * 501},
        {"consulta": 42},
        {"consulta": "girassóis", "limite": 0},
        {"consulta": "girassóis", "limite": 11},
        {"consulta": "girassóis", "limite": True},
        {"consulta": "girassóis", "limite": "5"},
        {"consulta": "girassóis", "data_referencia": "01/06/2030"},
        {"consulta": "girassóis", "data_referencia": "20300601"},
        {"consulta": "girassóis", "data_referencia": "2030-02-30"},
    ],
)
def test_search_invalid_input(ctx, kwargs):
    with pytest.raises(ToolError) as error:
        buscar_dispositivos(ctx, today=TODAY, **kwargs)
    assert error.value.code == "entrada_invalida"


def test_query_of_exactly_500_chars_is_accepted(ctx):
    assert busca(ctx, "girassóis " + "x" * 490)["consulta"].startswith("girassóis")


# ------------------------------------------------------------------ obter_dispositivo


def test_get_contract_fields(ctx):
    out = obter(ctx, "XX.art1")
    assert list(out) == [
        "encontrado", "id", "data_referencia", "versao", "citacao", "norma", "origem", "alteracao", "texto",
        "filhos", "vigor_desde", "efeitos", "outras_versoes", "observacao", "truncado", "fonte_url", "corpus",
    ]
    assert out["encontrado"] is True and out["truncado"] is False and out["observacao"] is None
    assert out["fonte_url"] == "https://exemplo.invalid/ec"
    assert out["efeitos"]["produz_efeitos_na_data"] is True


def test_children_in_legal_order_and_each_by_date(ctx):
    out = obter(ctx, "XX.art1", data_referencia="2030-01-01")
    assert [f["id"] for f in out["filhos"]] == ["XX.art1.incI", "XX.art1.incII", "XX.art1.incV", "XX.art1.incIX", "XX.art1.par1"]
    inc9 = out["filhos"][3]
    # Decisão de 2026-11-07: a lista vem da versão do pai, o texto do filho vem da data.
    assert inc9 == {"id": "XX.art1.incIX", "versao": "EC132.art3", "citacao": "XX.art1.incIX", "texto": "IX - regime novo de girassóis;", "produz_efeitos_na_data": True}
    assert obter(ctx, "XX.art1", data_referencia="2025-01-01")["filhos"][3]["versao"] == "EC132.art1"


def test_children_can_be_left_out(ctx):
    assert obter(ctx, "XX.art1", incluir_filhos=False)["filhos"] == []


def test_unknown_id_is_success_not_found(ctx):
    out = obter(ctx, "XX.art99")
    assert out["encontrado"] is False and out["motivo"] == "id inexistente no corpus"
    assert out["data_referencia"] == "2030-06-01" and out["corpus"]["coletado_em"] == "2026-11-06"


def test_three_effect_states(ctx):
    assert obter(ctx, "XX.art1")["efeitos"]["produz_efeitos_na_data"] is True
    assert obter(ctx, "XX.art2")["efeitos"]["produz_efeitos_na_data"] is False
    unknown = obter(ctx, "XX.art4")["efeitos"]
    assert unknown["produz_efeitos_na_data"] is None and unknown["metodo"] == "indeterminado" and unknown["desde"] is None


def test_previous_wording_observation_before_an_altered_version(ctx):
    out = obter(ctx, "XX.art2")
    assert out["observacao"] == OBS_PREVIOUS_WORDING
    assert obter(ctx, "XX.art2", data_referencia="2033-01-01")["observacao"] is None


def test_included_version_before_start_has_no_previous_wording(ctx):
    out = obter(ctx, "XX.art1", data_referencia="2023-01-01")
    assert out["efeitos"]["produz_efeitos_na_data"] is False and out["observacao"] is None


def test_revoked_is_returned_with_observation(ctx):
    out = obter(ctx, "XX.art3", data_referencia="2033-01-01")
    assert out["encontrado"] is True and out["efeitos"]["produz_efeitos_na_data"] is False
    assert out["observacao"] == "revogado a partir de 2033-01-01 (EC 132/2023, art. 22, II, a)"
    assert obter(ctx, "XX.art3", data_referencia="2032-12-31")["observacao"] is None


def test_long_text_is_truncated(ctx):
    out = obter(ctx, "XX.art5")
    assert out["truncado"] is True and len(out["texto"]) <= MAX_CHARS and out["texto"].endswith("…")


def test_children_beyond_the_ceiling_keep_id_with_null_text(ctx, monkeypatch):
    monkeypatch.setattr("taxlaw.tools.MAX_CHARS", 120)
    out = obter(ctx, "XX.art1")
    assert out["truncado"] is True
    texts = [f["texto"] for f in out["filhos"]]
    assert texts[0] is not None and texts[-1] is None
    assert len(out["texto"]) + sum(len(t) for t in texts if t) <= 120
    assert len(out["filhos"]) == 5  # todos os ids continuam visíveis


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": ""},
        {"id": "x" * 201},
        {"id": None},
        {"id": "XX.art1", "incluir_filhos": "sim"},
        {"id": "XX.art1", "data_referencia": "2030-6-1"},
    ],
)
def test_get_invalid_input(ctx, kwargs):
    with pytest.raises(ToolError) as error:
        obter_dispositivo(ctx, today=TODAY, **kwargs)
    assert error.value.code == "entrada_invalida"


# ------------------------------------------------------------------ guarda de CPF/CNPJ


@pytest.mark.parametrize(
    "number",
    [make_cpf("123456789"), make_cpf("123456789", formatted=True), make_cnpj("123456780001", formatted=True), make_cnpj("ABCDEFGH0001")],
)
def test_taxpayer_id_in_query_is_blocked_without_echo(ctx, number):
    with pytest.raises(ToolError) as error:
        busca(ctx, f"girassóis do contribuinte {number}")
    assert error.value.code == "dados_de_contribuinte"
    assert number not in error.value.message and "consulta" in error.value.message
    assert number not in json.dumps(error.value.to_dict(), ensure_ascii=False)


def test_guard_runs_before_validation_and_covers_every_text_field(ctx):
    number = make_cpf("987654321")
    for call in (
        lambda: busca(ctx, "girassol " * 70 + number),  # longa demais E com CPF: a guarda vence
        lambda: busca(ctx, "girassóis", data_referencia=number),
        lambda: obter(ctx, number),
        lambda: obter(ctx, "XX.art1", data_referencia=number),
    ):
        with pytest.raises(ToolError) as error:
            call()
        assert error.value.code == "dados_de_contribuinte" and number not in error.value.message


def test_article_numbers_and_dates_are_not_blocked(ctx):
    out = busca(ctx, "art. 156-A de 2023-12-21, processo 12345678901 inválido")
    assert out["consulta"]


def test_results_are_deterministic(ctx):
    assert busca(ctx, "girassóis regime") == busca(ctx, "girassóis regime")
    assert obter(ctx, "XX.art1") == obter(ctx, "XX.art1")

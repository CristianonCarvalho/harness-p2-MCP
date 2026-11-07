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

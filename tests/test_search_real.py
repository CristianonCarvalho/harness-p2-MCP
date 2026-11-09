"""Calibração do limiar de busca no corpus real (passos 08 e 13c).

Consultas medidas em 2026-11-07 (só EC 132) e de novo em 2026-11-09 (EC 132 +
LC 214; ver docstring de taxlaw.search): dentro do tema, o dispositivo
esperado aparece entre os 5 primeiros; fora do tema, a resposta é "não
encontrei". Se mudar o tokenizador, o BM25, o limiar ou o corpus, estes casos
dizem se a calibração continua de pé.
"""

import pytest

from taxlaw.corpus import load_corpus
from taxlaw.search import K1, THRESHOLD, build_index, score_all, search, tokenize


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

# Passo 13c: consultas que só a LC 214 responde (medidas em 2026-11-09).
LC_ON_TOPIC = {
    "serviços de educação redução de 60%": "LC214.art128.incI",
    "alíquota zero cesta básica alimentação humana": "LC214.art125",
    "imposto seletivo bens minerais alíquota máxima": "LC214.art422.par2",
    "redução de 30% advogados": "LC214.art127.incII",
    "dispositivos médicos redução de alíquota": "LC214.art128.incIII",
    "alíquotas do imposto seletivo veículos lei ordinária": "LC214.art419",
}


def top_relevance(index, query):
    """Relevância do 1º resultado, como em `search`, mas sem aplicar o limiar."""
    hits = score_all(index, query)
    terms = list(dict.fromkeys(tokenize(query)))
    if not hits or not terms:
        return 0.0
    ceiling = sum(index.idf.get(t, index.max_idf) * (K1 + 1) for t in terms)
    return hits[0].score / ceiling


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


@pytest.mark.parametrize(("query", "expected"), LC_ON_TOPIC.items())
def test_lc_query_finds_expected_dispositivo_in_top_5(index, query, expected):
    result = search(index, query)
    assert result.found, result.reason
    assert expected in [h.id for h in result.hits], [h.id for h in result.hits]


def test_threshold_still_separates_the_groups_with_margin(index):
    # Medido em 2026-11-09 com EC + LC: fora do tema até 0,138 ("campeonato
    # brasileiro de futebol" encosta num artigo da LC); dentro do tema a partir
    # de 0,248. Se a folga sumir, o limiar precisa ser recalibrado.
    off = max(top_relevance(index, q) for q in OFF_TOPIC + VOCABULARY_GAPS)
    on = min(top_relevance(index, q) for q in [*ON_TOPIC, *LC_ON_TOPIC])
    assert off < THRESHOLD - 0.005 and on > THRESHOLD + 0.05, (off, on)


def test_search_is_deterministic(index):
    assert search(index, "imposto sobre bens e serviços") == search(index, "imposto sobre bens e serviços")

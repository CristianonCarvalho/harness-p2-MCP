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
    fontes = {"ec132-2023": {"url": "https://exemplo.invalid", "coletado_em": "2026-11-06", "sha256_html": "0" * 64}}
    path.write_text(json.dumps({"fontes": fontes, "dispositivos": ROWS}, ensure_ascii=False), encoding="utf-8")
    return load_corpus(path), path


def test_load_corpus_header_versions_and_hash(corpus):
    c, path = corpus
    assert c.coletado_em == "2026-11-06"
    assert c.source_of(c.versions("CF.art2")[0])["url"] == "https://exemplo.invalid"
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

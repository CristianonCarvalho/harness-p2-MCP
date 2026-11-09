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
Limiar 0,15. Remedido no passo 13c (2026-11-09), com a LC 214 no corpus: fora
do tema até 0,138; dentro do tema (EC e LC) a partir de 0,248. O limiar ficou
(`test_threshold_still_separates_the_groups_with_margin` vigia a folga).
Consultas com palavras que a EC não usa ("ICMS", "split payment") ficam
abaixo: "não encontrei" é honesto, e reformular é papel da skill (passo 12).

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

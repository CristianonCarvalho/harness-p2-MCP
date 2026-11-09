"""O parser de LC no HTML real da LC 214/2025 (corpus/raw, só leitura).

Números medidos em 2026-11-09 no arquivo de sha256 0301816c…: 162 registros
nos 23 artigos do escopo, 4 dispositivos tocados pela LC 227/2026, 3
parágrafos tachados descartados e 2 vetados sem registro.
"""

import re
from collections import Counter
from pathlib import Path

from taxlaw.ingest.fetch import verify
from taxlaw.ingest.lc_structure import LC214_SCOPE, _LcCollector, parse_lc
from taxlaw.ingest.structure import decode_html

RAW_DIR = Path(__file__).resolve().parents[1] / "corpus" / "raw"
HTML = decode_html((RAW_DIR / "lc214-2025.html").read_bytes())
RESULT = parse_lc(HTML, norma="LC214", scope=LC214_SCOPE)
RECORDS = {r.id: r for r in RESULT.records}


def struck_texts(html: str) -> set[str]:
    """Todos os trechos tachados do documento inteiro."""
    found: list[str] = []

    class Spy(_LcCollector):
        def _close(self):
            if self._struck:
                found.append(re.sub(r"\s+", " ", "".join(self._struck).replace("\xa0", " ")).strip())
            super()._close()

    spy = Spy()
    spy.feed(html)
    spy.close()
    return {t for t in found if t}


def test_raw_file_matches_its_meta():
    assert verify(RAW_DIR, "lc214-2025")


def test_scope_is_the_23_articles_of_the_spec():
    assert len(LC214_SCOPE) == 23
    assert {i.split(".")[1] for i in RECORDS} == set(LC214_SCOPE)


def test_parses_cleanly():
    assert RESULT.errors == [] and RESULT.warnings == []
    assert len(RESULT.records) == 162 and RESULT.struck == 3


def test_no_struck_text_leaked_into_the_corpus():
    struck = struck_texts(HTML)
    assert len(struck) > 1000  # a página tem muita redação antiga
    assert not [r.id for r in RESULT.records if r.texto in struck]


def test_lc_227_amendments_in_scope():
    touched = {r.id: (r.alteracao, r.origem) for r in RESULT.records if r.alteracao != "original"}
    assert touched == {
        "LC214.art126.par6": ("incluido", "LC 214/2025, incluído pela LC 227/2026"),
        "LC214.art142.incII": ("alterado", "LC 214/2025, com redação dada pela LC 227/2026"),
        "LC214.art422.par2": ("alterado", "LC 214/2025, com redação dada pela LC 227/2026"),
        "LC214.art422.par5": ("alterado", "LC 214/2025, com redação dada pela LC 227/2026"),
    }
    assert RECORDS["LC214.art422.par2"].texto.endswith("nas operações com bens minerais extraídos.")


def test_vetoed_devices_have_no_record():
    assert RESULT.vetoed == ["LC214.art138.par4", "LC214.art138.par9.incII"]
    assert not set(RESULT.vetoed) & set(RECORDS)


def test_ids_unique_and_parents_exist():
    assert len(RECORDS) == len(RESULT.records)
    assert [r.id for r in RESULT.records if r.pai and r.pai not in RECORDS] == []


def test_no_amendment_mark_or_link_text_left_in_texto():
    leftover = re.compile(r"\((Redação|Incluíd|Vide|Vigência|Produção|Revogad|Promulga)|(Vigência|Produção de efeitos)$")
    assert [r.id for r in RESULT.records if leftover.search(r.texto)] == []


def test_known_texts():
    assert RECORDS["LC214.art125"].texto.startswith("Art. 125. Ficam reduzidas a zero as alíquotas do IBS e da CBS incidentes sobre as vendas de produtos destinados à alimentação humana")
    assert RECORDS["LC214.art128.incI"].texto == "I - serviços de educação;"
    assert RECORDS["LC214.art127.incII"].texto == "II - advogados;"
    assert RECORDS["LC214.art128"].citacao == "LC 214/2025, art. 128"


def test_label_kinds():
    kinds = Counter(re.match(r"art|parunico|par|inc|ali", r.id.split(".")[-1]).group(0) for r in RESULT.records)
    assert set(kinds) == {"art", "par", "parunico", "inc", "ali"}

# P2, passo 13a: coleta e estrutura da LC 214 (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-09-p2-passo-13a-lc214-estrutura.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** coletar a LC 214/2025 no `corpus/raw` com o `fetch` generalizado para várias fontes, e transformar os 23 artigos do escopo em registros com um parser de lei compilada que descarta a redação antiga tachada.

**Architecture:** Task 1 troca as constantes de fonte única do `fetch.py` por um registro `SOURCES` (com o `<title>` como prova de que a página é a norma certa) e grava `corpus/raw/lc214-2025.*`. Task 2 cria `ingest/lc_structure.py`, que lê os `<p>` separando o texto tachado, reaproveita os rótulos do `structure.py` e devolve `Record`s do escopo `LC214_SCOPE`. O build, os efeitos e o `dispositivos.json` não mudam neste passo (são o 13b).

**Tech Stack:** Python 3.13 (biblioteca padrão: `html.parser`, `re`, `dataclasses`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-09-lc214-capitulos-design.md` (seções 2, 3, 4, 6 e 8), sobre a principal `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md`.

## Global Constraints

- Nenhuma dependência nova; nenhum acesso à rede em testes (o `fetch` usa `--from-file`).
- `fetch` continua sendo o único módulo que importa bibliotecas de rede; sem `--source`, o comportamento do passo 03 não muda (a EC 132 é a fonte padrão, e `SOURCE_NAME`/`SOURCE_URL` continuam exportados).
- O HTML coletado é gravado byte a byte: sha256 `0301816c65aef305df1824ef625b29acbc8fe964ece88cbb4f54efaeabd36685`, 5.403.923 bytes.
- Parágrafo inteiramente tachado é descartado; parcialmente tachado no escopo é erro; id repetido é erro; artigo do escopo ausente é erro. Nunca descartar texto em silêncio.
- Não alterar `build.py`, `effects.py`, `corpus.py`, `search.py`, `tools.py`, `server.py`, `corpus/dispositivos.json`, `corpus/raw/ec132-2023.*` nem `corpus/efeitos_correcoes.yaml`. Em `structure.py`, só a linha do dicionário de prefixos.
- Testes 100% offline e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês. Comentários didáticos: o porquê de cada bloco.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `.claude/`, `.kiro/`, `hooks/`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-09 no protótipo)

- Títulos das páginas: EC 132 → `Emenda Constitucional nº 132`; LC 214 → `Lcp 214`. A LC 214 contém "emenda constitucional" e "132" no corpo (cita a EC): só os marcadores do corpo aceitavam a página da LC como EC e sobrescreviam `ec132-2023.html` (bug achado no protótipo).
- Redação antiga: parágrafo inteiro em `<span style="…; text-decoration:line-through">`; no documento, 1.884 parágrafos inteiramente tachados e 66 parcialmente (nenhum parcial no escopo).
- `parse_lc` no HTML real com `LC214_SCOPE`: 162 registros, 0 erros, 0 avisos, 3 tachados descartados no escopo, vetados `LC214.art138.par4` e `LC214.art138.par9.incII`; alterações: `LC214.art126.par6` (incluído), `LC214.art142.incII`, `LC214.art422.par2`, `LC214.art422.par5` (redação dada), todas pela LC 227/2026. Nenhum texto tachado igual a um `texto`; nenhuma marca residual; ids únicos; todo `pai` existe.
- `_label` do `structure.py` já produz `parunico` → `parágrafo único`, `76-A`, alíneas `ali<x>` com pai no inciso, e cardinal a partir de 10 (`art. 128`).

## Review Focus

- A página de uma norma aceita como outra (o bug do título) (testes `test_lc_page_is_not_accepted_as_the_ec` e `test_ec_page_is_not_accepted_as_the_lc`).
- `<p>` sem `</p>` ou tags não fechadas fazem o tachado vazar para o parágrafo seguinte (testes `test_unclosed_paragraph_does_not_carry_strike_into_the_next` e `test_unclosed_tags_do_not_leak_strike_into_next_paragraph`).
- Redação antiga repetida sem tachado entra como registro duplicado (teste `test_repeated_id_is_an_error_old_wording_that_escaped`).
- Nome de capítulo/seção vira registro ou aviso (teste `test_headings_and_their_names_are_not_records_nor_warnings`).
- Algum texto tachado do HTML real chega ao `texto` de um registro (teste `test_no_struck_text_leaked_into_the_corpus`).

---

### Task 1: `fetch` com várias fontes e coleta da LC 214

**Files:**
- Modify: `src/taxlaw/ingest/fetch.py`
- Modify: `tests/test_fetch.py`
- Create: `corpus/raw/lc214-2025.html`
- Create: `corpus/raw/lc214-2025.meta.json`

**Interfaces:**
- Consumes: o `fetch.py` do passo 03.
- Produces: `fetch.Source(name, url, markers, label, title_number)`; `fetch.SOURCES: dict[str, Source]` com `"ec132-2023"` e `"lc214-2025"`; `fetch.DEFAULT_SOURCE = "ec132-2023"`; `SOURCE_NAME`/`SOURCE_URL` mantidos; `check_looks_like_source(content, source=None)`; CLI `--source {ec132-2023,lc214-2025}`; `corpus/raw/lc214-2025.html` (+ `.meta.json`).

- [ ] **Step 1: testes que falham.** Substitua `tests/test_fetch.py` inteiro por (os testes novos são os da seção "várias fontes", no fim):

```python
"""Testes do fetch (passo 03). Nenhum teste acessa a rede: o `get` é falso."""

import ast
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from taxlaw.ingest import fetch
from taxlaw.ingest.fetch import (
    SOURCE_NAME,
    SOURCE_URL,
    Download,
    FetchError,
    build_meta,
    check_looks_like_source,
    main,
    verify,
)

# Página sintética em windows-1252 ("Constituição" com ç e ã de 1 byte cada).
PAGE = (
    "<html><head><meta charset=windows-1252></head><body>"
    "<p>EMENDA CONSTITUCIONAL Nº 132, DE 20 DE DEZEMBRO DE 2023</p>"
    "<p>Altera o Sistema Tributário Nacional. Constituição.</p></body></html>"
).encode("windows-1252")
TODAY = date(2026, 11, 6)


def fake_get(content: bytes = PAGE, content_type: str | None = "text/html; charset=windows-1252"):
    calls: list[str] = []

    def get(url: str) -> Download:
        calls.append(url)
        return Download(content, content_type)

    get.calls = calls
    return get


def failing_get(url: str) -> Download:
    raise FetchError(f"não consegui baixar {url} (timeout). Salve a página pelo navegador e rode de novo com --from-file CAMINHO.")


def run(tmp_path: Path, *extra: str, get=None) -> int:
    return main(["--raw-dir", str(tmp_path / "raw"), *extra], get=get or fake_get(), today=lambda: TODAY)


def read_meta(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "raw" / f"{SOURCE_NAME}.meta.json").read_text(encoding="utf-8"))


def test_download_saves_exact_bytes_and_meta(tmp_path):
    get = fake_get()
    assert run(tmp_path, get=get) == 0
    assert get.calls == [SOURCE_URL]
    assert (tmp_path / "raw" / f"{SOURCE_NAME}.html").read_bytes() == PAGE
    assert read_meta(tmp_path) == {
        "url": SOURCE_URL,
        "coletado_em": "2026-11-06",
        "metodo_coleta": "http",
        "sha256": hashlib.sha256(PAGE).hexdigest(),
        "tamanho_bytes": len(PAGE),
        "content_type": "text/html; charset=windows-1252",
    }
    assert verify(tmp_path / "raw", SOURCE_NAME)


def test_from_file_records_official_url_and_never_calls_network(tmp_path):
    saved = tmp_path / "pagina.htm"
    saved.write_bytes(PAGE)
    get = fake_get()
    assert run(tmp_path, "--from-file", str(saved), get=get) == 0
    assert get.calls == []
    meta = read_meta(tmp_path)
    assert meta["url"] == SOURCE_URL
    assert meta["metodo_coleta"] == "arquivo"
    assert meta["content_type"] is None
    assert (tmp_path / "raw" / f"{SOURCE_NAME}.html").read_bytes() == PAGE


def test_network_failure_returns_2_with_hint_and_writes_nothing(tmp_path, capsys):
    assert run(tmp_path, get=failing_get) == 2
    assert "--from-file" in capsys.readouterr().err
    assert not (tmp_path / "raw").exists()


def test_missing_file_returns_2(tmp_path, capsys):
    assert run(tmp_path, "--from-file", str(tmp_path / "nao-existe.htm")) == 2
    assert "erro:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content",
    [b"", b"   \n", b"<html>503 Service Unavailable</html>", b"<html>Emenda Constitucional n 131</html>"],
)
def test_content_that_is_not_the_source_is_rejected(tmp_path, content):
    assert run(tmp_path, get=fake_get(content)) == 2
    assert not (tmp_path / "raw").exists()


def test_check_accepts_utf8_and_windows_1252():
    text = "<p>Emenda Constitucional nº 132 — Constituição</p>"
    check_looks_like_source(text.encode("utf-8"))
    check_looks_like_source(text.replace("—", "-").encode("windows-1252"))


def test_same_content_again_keeps_files_untouched(tmp_path, capsys):
    assert run(tmp_path) == 0
    meta_before = (tmp_path / "raw" / f"{SOURCE_NAME}.meta.json").read_text(encoding="utf-8")
    later = main(["--raw-dir", str(tmp_path / "raw")], get=fake_get(), today=lambda: date(2027, 1, 1))
    assert later == 0
    assert "sem mudança" in capsys.readouterr().out
    assert (tmp_path / "raw" / f"{SOURCE_NAME}.meta.json").read_text(encoding="utf-8") == meta_before


def test_changed_content_overwrites_and_says_so(tmp_path, capsys):
    assert run(tmp_path) == 0
    new_page = PAGE.replace(b"Nacional", b"Nacional (texto atualizado)")
    assert run(tmp_path, get=fake_get(new_page)) == 0
    assert "o texto mudou" in capsys.readouterr().out
    assert read_meta(tmp_path)["sha256"] == hashlib.sha256(new_page).hexdigest()


def test_corrupted_html_is_rewritten_even_with_same_sha_in_meta(tmp_path):
    assert run(tmp_path) == 0
    html = tmp_path / "raw" / f"{SOURCE_NAME}.html"
    html.write_bytes(b"corrompido")
    assert not verify(tmp_path / "raw", SOURCE_NAME)
    assert run(tmp_path) == 0
    assert html.read_bytes() == PAGE


def test_verify_false_when_files_missing(tmp_path):
    assert verify(tmp_path, SOURCE_NAME) is False


def test_meta_json_is_stable_text(tmp_path):
    assert run(tmp_path) == 0
    text = (tmp_path / "raw" / f"{SOURCE_NAME}.meta.json").read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert list(json.loads(text)) == sorted(json.loads(text))


def test_build_meta_uses_given_date_not_clock():
    meta = build_meta(SOURCE_URL, Download(PAGE, None), date(2000, 1, 2), "arquivo")
    assert meta["coletado_em"] == "2000-01-02"


def test_default_raw_dir_is_repo_corpus_raw():
    assert fetch.DEFAULT_RAW_DIR.parts[-2:] == ("corpus", "raw")
    assert (fetch.DEFAULT_RAW_DIR.parents[1] / "pyproject.toml").is_file()


NETWORK_MODULES = {"urllib", "http", "socket", "requests", "httpx", "aiohttp", "ssl"}


def test_fetch_is_the_only_module_that_imports_network_libraries():
    package = Path(fetch.__file__).resolve().parents[1]
    offenders = []
    for path in package.rglob("*.py"):
        if path.name == "fetch.py" and path.parent.name == "ingest":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [f"{path.name}: {n}" for n in names if n.split(".")[0] in NETWORK_MODULES]
    assert offenders == []


# ------------------------------------------------------- várias fontes (passo 13)

LC_PAGE = (
    "<html><head><meta charset=windows-1252><title>Lcp 214</title></head><body>"
    "<p>LEI COMPLEMENTAR Nº 214, DE 16 DE JANEIRO DE 2025</p>"
    "<p>Institui o IBS e a CBS; altera a Emenda Constitucional nº 132.</p></body></html>"
).encode("windows-1252")


def test_sources_registry_has_both_norms_and_default_is_ec():
    assert fetch.DEFAULT_SOURCE == SOURCE_NAME == "ec132-2023"
    assert fetch.SOURCES["lc214-2025"].url == "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"
    assert fetch.SOURCES[SOURCE_NAME].url == SOURCE_URL


def test_source_option_saves_under_its_own_name_and_url(tmp_path):
    get = fake_get(LC_PAGE)
    assert main(["--source", "lc214-2025", "--raw-dir", str(tmp_path)], get=get, today=lambda: TODAY) == 0
    assert get.calls == ["https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"]
    meta = json.loads((tmp_path / "lc214-2025.meta.json").read_text(encoding="utf-8"))
    assert meta["url"].endswith("lcp214.htm") and (tmp_path / "lc214-2025.html").read_bytes() == LC_PAGE
    assert not (tmp_path / "ec132-2023.html").exists()


def test_lc_page_is_not_accepted_as_the_ec(tmp_path, capsys):
    # A LC 214 cita a EC 132 no corpo: só o <title> distingue as duas.
    assert main(["--raw-dir", str(tmp_path)], get=fake_get(LC_PAGE), today=lambda: TODAY) == 2
    assert "título" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_ec_page_is_not_accepted_as_the_lc(tmp_path):
    ec_page = PAGE.replace(b"<head>", b"<head><title>Emenda Constitucional n\xba 132</title>")
    with pytest.raises(FetchError):
        check_looks_like_source(ec_page, fetch.SOURCES["lc214-2025"])


def test_title_number_must_be_whole():
    page = LC_PAGE.replace(b"Lcp 214", b"Lcp 2140")
    with pytest.raises(FetchError):
        check_looks_like_source(page, fetch.SOURCES["lc214-2025"])
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_fetch.py -q` → os 5 testes novos falham (`AttributeError: module 'taxlaw.ingest.fetch' has no attribute 'DEFAULT_SOURCE'` e afins); os 17 antigos passam.

- [ ] **Step 3: implemente.** Substitua `src/taxlaw/ingest/fetch.py` inteiro por:

```python
"""Coleta da fonte oficial: o único módulo do pacote com acesso à rede.

Grava os bytes exatamente como vieram (sem decodificar: o Planalto usa
encoding antigo, e decidir o encoding é trabalho do `structure`) e, ao lado,
um `.meta.json` com url, data da coleta e sha256. O build lê `coletado_em`
desse arquivo, nunca do relógio, para ser determinístico.

Uso:
    uv run python -m taxlaw.ingest.fetch                     # baixa da URL oficial
    uv run python -m taxlaw.ingest.fetch --from-file pag.htm # página salva no navegador
    uv run python -m taxlaw.ingest.fetch --source lc214-2025 --from-file lcp214.htm

As fontes conhecidas ficam em `SOURCES` (passo 13): nome, URL oficial e as
palavras que provam que o conteúdo é a norma certa. Sem `--source`, a fonte é
a EC 132, como antes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

@dataclass(frozen=True)
class Source:
    """Uma norma coletável: nome dos arquivos em corpus/raw, URL oficial e marcadores.

    `markers` são palavras em ASCII minúsculo (iguais em UTF-8 e windows-1252)
    que precisam aparecer no conteúdo: recusam página de erro ou norma errada.
    """

    name: str
    url: str
    markers: tuple[bytes, ...]
    label: str  # nome legível, para as mensagens
    # Passo 13: a LC 214 cita a EC 132 no corpo, então os marcadores do corpo
    # não bastam para distinguir as duas. Se a página tem <title>, ele precisa
    # conter este número (EC: "Emenda Constitucional nº 132"; LC: "Lcp 214").
    title_number: bytes


SOURCES = {
    "ec132-2023": Source(
        "ec132-2023",
        "https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc132.htm",
        (b"emenda constitucional", b"132"),
        "a EC 132/2023",
        b"132",
    ),
    "lc214-2025": Source(
        "lc214-2025",
        "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm",
        (b"lei complementar", b"214"),
        "a LC 214/2025",
        b"214",
    ),
}
DEFAULT_SOURCE = "ec132-2023"
# Compatibilidade com o passo 03: a fonte padrão continua exposta assim.
SOURCE_NAME = DEFAULT_SOURCE
SOURCE_URL = SOURCES[DEFAULT_SOURCE].url
# src/taxlaw/ingest/fetch.py → parents[3] é a raiz do repositório.
DEFAULT_RAW_DIR = Path(__file__).resolve().parents[3] / "corpus" / "raw"
# Cliente genérico e honesto: sem e-mail, sem se passar por navegador.
USER_AGENT = "taxlaw-p2/0.1 (projeto de estudo; dados publicos)"


class FetchError(Exception):
    """Falha de coleta com mensagem para humano (sem stack trace na CLI)."""


@dataclass(frozen=True)
class Download:
    """Bytes da fonte e o Content-Type informado (None quando veio de arquivo)."""

    content: bytes
    content_type: str | None


def http_get(url: str, timeout: float = 30.0) -> Download:
    """Baixa `url`. Qualquer falha de rede vira FetchError com dica do --from-file."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return Download(response.read(), response.headers.get("Content-Type"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(
            f"não consegui baixar {url} ({exc}). Salve a página pelo navegador "
            "e rode de novo com --from-file CAMINHO."
        ) from exc


def read_file(path: Path) -> Download:
    """Lê uma página salva à mão, byte a byte."""
    try:
        return Download(path.read_bytes(), None)
    except OSError as exc:
        raise FetchError(f"não consegui ler {path} ({exc})") from exc


def check_looks_like_source(content: bytes, source: Source | None = None) -> None:
    """Recusa o que claramente não é a norma: vazio, página de erro, captcha, norma errada.

    A busca é em bytes e só com ASCII, que é igual em UTF-8 e windows-1252.
    """
    source = source or SOURCES[DEFAULT_SOURCE]
    lowered = content.lower()
    if not content.strip():
        raise FetchError("o conteúdo está vazio")
    missing = [m.decode("ascii") for m in source.markers if m not in lowered]
    if missing:
        raise FetchError(
            f"o conteúdo não parece ser {source.label} (falta {', '.join(repr(m) for m in missing)}); "
            "confira se a página salva é a certa"
        )
    title = re.search(rb"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    if title and not re.search(rb"(?<![0-9])" + source.title_number + rb"(?![0-9])", title.group(1)):
        raise FetchError(
            f"o título da página ({title.group(1).decode('latin-1').strip()!r}) não é o esperado para {source.label}; "
            "confira se a página salva é a certa ou se --source está certo"
        )


def build_meta(url: str, download: Download, collected_at: date, method: str) -> dict:
    """Metadados da coleta. `method` é "http" ou "arquivo"."""
    return {
        "url": url,
        "coletado_em": collected_at.isoformat(),
        "metodo_coleta": method,
        "sha256": hashlib.sha256(download.content).hexdigest(),
        "tamanho_bytes": len(download.content),
        "content_type": download.content_type,
    }


def paths_for(raw_dir: Path, name: str) -> tuple[Path, Path]:
    """Caminhos do HTML bruto e do meta para uma fonte."""
    return raw_dir / f"{name}.html", raw_dir / f"{name}.meta.json"


def save(raw_dir: Path, name: str, download: Download, meta: dict) -> None:
    """Grava os bytes sem alteração e o meta em JSON estável (chaves ordenadas)."""
    html_path, meta_path = paths_for(raw_dir, name)
    raw_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_bytes(download.content)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def verify(raw_dir: Path, name: str) -> bool:
    """True se o sha256 do HTML gravado bate com o do meta (arquivo íntegro)."""
    html_path, meta_path = paths_for(raw_dir, name)
    if not html_path.is_file() or not meta_path.is_file():
        return False
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return hashlib.sha256(html_path.read_bytes()).hexdigest() == meta.get("sha256")


def main(
    argv: list[str] | None = None,
    *,
    get: Callable[[str], Download] = http_get,
    today: Callable[[], date] = date.today,
) -> int:
    """CLI. `get` e `today` são injetáveis para os testes rodarem sem rede e sem relógio."""
    parser = argparse.ArgumentParser(prog="python -m taxlaw.ingest.fetch")
    parser.add_argument("--source", choices=sorted(SOURCES), default=DEFAULT_SOURCE, help="norma a coletar")
    parser.add_argument("--from-file", type=Path, help="página salva no navegador")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)
    source = SOURCES[args.source]

    try:
        if args.from_file is not None:
            download, method = read_file(args.from_file), "arquivo"
        else:
            download, method = get(source.url), "http"
        check_looks_like_source(download.content, source)
    except FetchError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    meta = build_meta(source.url, download, today(), method)
    html_path, meta_path = paths_for(args.raw_dir, source.name)
    if meta_path.is_file():
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        if old.get("sha256") == meta["sha256"] and verify(args.raw_dir, source.name):
            # Mesmo texto: não regrava, para o git não mostrar diff só de data.
            print(f"sem mudança: {html_path.name} (sha256 {meta['sha256'][:12]}…)")
            return 0
        print(f"o texto mudou: sha256 {str(old.get('sha256'))[:12]}… → {meta['sha256'][:12]}…")
    save(args.raw_dir, source.name, download, meta)
    print(f"gravado: {html_path} ({meta['tamanho_bytes']} bytes, via {method})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: rode e veja passar.** `uv run pytest tests/test_fetch.py -q` → 22 passed.

- [ ] **Step 5: colete a LC 214.** O arquivo foi baixado pelo usuário no navegador (o Planalto derruba clientes automatizados):

```bash
uv run python -m taxlaw.ingest.fetch --source lc214-2025 --from-file "/Users/cristianocarvalho/Downloads/EC 132/lc214-2025.html"
```

Esperado: `gravado: …/corpus/raw/lc214-2025.html (5403923 bytes, via arquivo)`. Confira `corpus/raw/lc214-2025.meta.json`: `"sha256": "0301816c65aef305df1824ef625b29acbc8fe964ece88cbb4f54efaeabd36685"`, `"metodo_coleta": "arquivo"`, `"url": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm"`. Confira também que `corpus/raw/ec132-2023.*` não mudou: `git status --short corpus/raw` mostra só os dois arquivos novos. Se o arquivo de origem não existir, pare e reporte: não baixe da rede.

- [ ] **Step 6: suíte inteira.** `uv run pytest -q` → 352 passed.

- [ ] **Step 7: commit.** `git add src/taxlaw/ingest/fetch.py tests/test_fetch.py corpus/raw/lc214-2025.html corpus/raw/lc214-2025.meta.json && git commit -m "feat(step-13a): fetch com várias fontes e coleta da LC 214"`

### Task 2: Parser de lei compilada (`lc_structure`)

**Files:**
- Modify: `src/taxlaw/ingest/structure.py` (só o dicionário de prefixos da função de rótulos)
- Create: `src/taxlaw/ingest/lc_structure.py`
- Create: `tests/test_lc_structure.py`
- Create: `tests/test_lc_structure_real.py`
- Create: `docs/steps/13a-lc214-coleta-estrutura.md`

**Interfaces:**
- Consumes: `taxlaw.ingest.structure.Record`, `_Context`, `_label`, `decode_html`; `taxlaw.ingest.fetch.verify`; `corpus/raw/lc214-2025.html` (Task 1).
- Produces: `taxlaw.ingest.lc_structure.LC214_SCOPE: frozenset[str]` (23 itens `"art125"`…); `LcParagraph(text, struck, partly_struck)`; `lc_paragraphs(html) -> list[LcParagraph]`; `LcParseResult(records, warnings, errors, struck, vetoed)`; `parse_lc(html, *, norma, scope) -> LcParseResult`. Os `Record`s têm `norma="LC214"`, `versao="LC214"`, `alteracao` em `original|alterado|incluido` e `origem` `"LC 214/2025"`, `"LC 214/2025, com redação dada pela LC 227/2026"`, `"LC 214/2025, incluído pela LC 227/2026"` ou `"LC 214/2025, parte promulgada após veto"`.

- [ ] **Step 1: testes que falham.** Crie `tests/test_lc_structure.py`:

```python
"""Testes do parser de lei complementar (passo 13a) com HTML sintético.

O HTML imita o formato do Planalto para leis compiladas (spec do passo 13,
seção 2): <p class=MsoNormal>, âncoras por dispositivo, redação antiga em
<span style="...text-decoration:line-through">, marcas "(Redação dada pela
...)" no fim e títulos de capítulo/seção em parágrafos próprios. Os textos
são inventados.
"""

import pytest

from taxlaw.ingest.lc_structure import LcParagraph, lc_paragraphs, parse_lc


def p(text: str, *, struck: bool = False, anchor: str | None = None) -> str:
    style = "font-family: Arial,sans-serif" + ("; text-decoration:line-through" if struck else "")
    name = f'<a name="{anchor}"></a>' if anchor else ""
    return f'<p class=MsoNormal><span style="{style}"><font size="2">{name}{text}</font></span></p>\n'


def page(*paragraphs: str) -> str:
    return "<html><head><title>Lcp 999</title></head><body>" + "".join(paragraphs) + "</body></html>"


MARK_227 = "(Redação dada pela Lei Complementar nº 227, de 2026)"
INCLUDED_227 = "(Incluído pela Lei Complementar nº 227, de 2026)"

HTML = page(
    p("TÍTULO III"),
    p("DOS GIRASSÓIS"),
    p("CAPÍTULO II"),
    p("DA REDUÇÃO DOS GIRASSÓIS"),
    p("Art. 10. Ficam reduzidas em 60% as alíquotas sobre girassóis:", anchor="art10"),
    p("I - girassóis amarelos;"),
    p("II - girassóis antigos;", struck=True),
    p(f"II - girassóis novos; {MARK_227}"),
    p("a) de jardim;"),
    p("III - (VETADO)."),
    p("§ 1º Regulamento disporá sobre girassóis."),
    p(f"§ 2º Tulipas também. {INCLUDED_227}"),
    p("Seção I"),
    p("Disposições Gerais"),
    p("Art. 11. Este artigo está fora do escopo."),
    p("§ 1º Também fora."),
    p("Art. 12. Ficam reduzidas a zero as alíquotas sobre cactos. Vigência"),
    p("Parágrafo único. Aplica-se o art. 10. (Vide Decreto nº 1, de 2026)"),
)
SCOPE = {"art10", "art12"}


def parse(html=HTML, scope=SCOPE):
    return parse_lc(html, norma="LC214", scope=scope)


def by_id(result):
    return {r.id: r for r in result.records}


def test_paragraphs_separate_struck_text():
    paragraphs = lc_paragraphs(page(p("velho", struck=True), p("novo"), '<p><span style="text-decoration: line-through">meio</span> e meio</p>'))
    assert paragraphs == [
        LcParagraph("", True, False),
        LcParagraph("novo", False, False),
        LcParagraph("e meio", False, True),
    ]


def test_strike_tags_also_count():
    assert lc_paragraphs("<p><strike>velho</strike></p><p><s>velho</s></p><p><del>velho</del></p>") == [LcParagraph("", True, False)] * 3


def test_records_ids_citations_and_parents():
    records = by_id(parse())
    assert list(records) == [
        "LC214.art10", "LC214.art10.incI", "LC214.art10.incII", "LC214.art10.incII.alia",
        "LC214.art10.par1", "LC214.art10.par2", "LC214.art12", "LC214.art12.parunico",
    ]
    assert records["LC214.art10.incII.alia"].citacao == "LC 214/2025, art. 10, II, a"
    assert records["LC214.art10.incII.alia"].pai == "LC214.art10.incII"
    assert records["LC214.art12.parunico"].citacao == "LC 214/2025, art. 12, parágrafo único"
    assert {r.norma for r in records.values()} == {"LC214"} and {r.versao for r in records.values()} == {"LC214"}


def test_struck_old_wording_is_dropped_and_counted():
    result = parse()
    assert by_id(result)["LC214.art10.incII"].texto == "II - girassóis novos;"
    assert result.struck == 1
    assert all("antigos" not in r.texto for r in result.records)


def test_amendment_marks_become_alteracao_and_origem_and_leave_the_text():
    records = by_id(parse())
    altered, included, plain = records["LC214.art10.incII"], records["LC214.art10.par2"], records["LC214.art10.incI"]
    assert (altered.alteracao, altered.origem) == ("alterado", "LC 214/2025, com redação dada pela LC 227/2026")
    assert (included.alteracao, included.origem) == ("incluido", "LC 214/2025, incluído pela LC 227/2026")
    assert (plain.alteracao, plain.origem) == ("original", "LC 214/2025")
    assert included.texto == "§ 2º Tulipas também."


def test_loose_link_text_and_vide_marks_are_removed():
    records = by_id(parse())
    assert records["LC214.art12"].texto.endswith("sobre cactos.")
    assert records["LC214.art12.parunico"].texto == "Parágrafo único. Aplica-se o art. 10."
    assert records["LC214.art12.parunico"].alteracao == "original"


def test_vetoed_has_no_record_but_is_listed():
    result = parse()
    assert "LC214.art10.incIII" not in by_id(result)
    assert result.vetoed == ["LC214.art10.incIII"]


def test_headings_and_their_names_are_not_records_nor_warnings():
    result = parse()
    assert result.warnings == [] and result.errors == []
    assert all("GIRASSÓIS" not in r.texto and "Disposições" not in r.texto for r in result.records)


def test_out_of_scope_articles_are_skipped():
    assert not any(r.id.startswith("LC214.art11") for r in parse().records)


def test_missing_scope_article_is_an_error():
    assert parse(scope=SCOPE | {"art99"}).errors == ["artigo do escopo não encontrado: LC214.art99"]


def test_partly_struck_paragraph_in_scope_is_an_error():
    html = page(p("Art. 10. Caput."), '<p><span style="text-decoration:line-through">I - velho</span> I - novo</p>')
    errors = parse(html, {"art10"}).errors
    assert len(errors) == 1 and errors[0].startswith("parágrafo parcialmente tachado em LC214.art10")


def test_partly_struck_paragraph_out_of_scope_is_ignored():
    html = page(p("Art. 10. Caput."), p("Art. 11. Fora."), '<p><span style="text-decoration:line-through">I - velho</span> I - novo</p>')
    assert parse(html, {"art10"}).errors == []


def test_repeated_id_is_an_error_old_wording_that_escaped():
    html = page(p("Art. 10. Caput."), p("I - redação antiga sem tachado;"), p(f"I - redação nova; {MARK_227}"))
    assert parse(html, {"art10"}).errors == ["id repetido LC214.art10.incI: redação antiga fora do tachado?"]


def test_unlabeled_paragraph_in_scope_is_a_warning():
    html = page(p("Art. 10. Caput:"), p("texto solto sem rótulo"))
    result = parse(html, {"art10"})
    assert result.warnings == ["parágrafo sem rótulo em LC214.art10: 'texto solto sem rótulo'"]


def test_promulgated_after_veto_is_marked_in_origem():
    html = page(p("Art. 10. Caput:"), p("V - fundos de investimento; (Promulgação partes vetadas)"))
    result = parse(html, {"art10"})
    record = by_id(result)["LC214.art10.incV"]
    assert record.origem == "LC 214/2025, parte promulgada após veto" and record.texto == "V - fundos de investimento;"
    assert result.warnings == ["LC214.art10.incV: promulgado depois de veto; efeitos ficam indeterminados"]


@pytest.mark.parametrize("unclosed", ["<font size=2>", "<span>"])
def test_unclosed_tags_do_not_leak_strike_into_next_paragraph(unclosed):
    html = page(f'<p><span style="text-decoration:line-through">{unclosed}velho</span></p>', p("Art. 10. Caput."))
    assert [x.text for x in lc_paragraphs(html)] == ["", "Art. 10. Caput."]


def test_unclosed_paragraph_does_not_carry_strike_into_the_next():
    # FrontPage às vezes não fecha o <p>: o tachado do anterior não pode vazar.
    html = '<p><span style="text-decoration:line-through">velho<p>Art. 10. Caput.</p>'
    assert [(x.text, x.struck) for x in lc_paragraphs(html)] == [("", True), ("Art. 10. Caput.", False)]
```

E `tests/test_lc_structure_real.py`:

```python
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
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_lc_structure.py tests/test_lc_structure_real.py -q` → `ModuleNotFoundError: No module named 'taxlaw.ingest.lc_structure'`.

- [ ] **Step 3: prefixo da LC em `structure.py`.** Em `_label`, troque a linha

```python
    prefix = {"CF": "CF", "ADCT": "ADCT", "EC132": "EC 132/2023"}[norma]
```

por

```python
    # LC214: passo 13 (lc_structure.py reaproveita estes rótulos).
    prefix = {"CF": "CF", "ADCT": "ADCT", "EC132": "EC 132/2023", "LC214": "LC 214/2025"}[norma]
```

Nada mais muda em `structure.py`.

- [ ] **Step 4: implemente.** Crie `src/taxlaw/ingest/lc_structure.py`:

```python
"""HTML de uma lei complementar no Planalto → registros (puro: sem rede, sem relógio).

Diferente da EC 132 (`structure.py`), que cita dispositivos da CF entre aspas,
aqui o texto é a própria lei, e a página é a **versão compilada**: as
alterações posteriores (ex.: LC 227/2026) já estão aplicadas, e a redação
antiga continua na página, tachada (spec do passo 13, seção 2):

- a redação antiga vem inteira dentro de um elemento com
  `text-decoration:line-through` (ou `<strike>`/`<s>`/`<del>`), logo antes da
  nova. Parágrafo inteiramente tachado é descartado; parágrafo **parcialmente**
  tachado é erro, porque não dá para saber qual é o texto vigente;
- a redação nova termina com uma marca "(Redação dada pela Lei Complementar nº
  227, de 2026)" ou "(Incluído pela ...)". A marca vira `alteracao`/`origem` e
  sai do `texto`;
- títulos (LIVRO, TÍTULO, CAPÍTULO, Seção, Subseção) e o nome que vem no
  parágrafo seguinte não viram registro;
- dispositivo "(VETADO)" não tem texto normativo: não vira registro, só é
  contado.

Só os artigos do escopo geram registros (a LC 214 tem mais de 500 artigos;
o passo 13 traz alguns capítulos). Artigo do escopo ausente é erro. Um mesmo
id duas vezes também é erro: seria a redação antiga que escapou do tachado.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser

from taxlaw.ingest.structure import Record, _Context, _label

# Elementos que não fecham (não entram na pilha de estilos).
_VOID = frozenset({"br", "img", "hr", "meta", "link", "input", "wbr"})
_STRIKE_TAGS = frozenset({"strike", "s", "del"})

# Marcas de alteração no fim do parágrafo. Podem vir várias seguidas, e o
# Planalto às vezes deixa o texto solto de um link ("Vigência", "Produção de
# efeitos") colado no fim.
_MARK = re.compile(r"\((Redação dada|Incluíd[oa]|Promulgação partes vetadas|Vide|Vigência|Produção de efeitos)[^()]*\)\s*$")
_LOOSE_LINK = re.compile(r"\s*(Vigência|Produção de efeitos)\s*$")
_LC_AMENDMENT = re.compile(r"Lei Complementar nº (\d+), de (\d{4})")
_HEADING = re.compile(r"^(LIVRO|TÍTULO|CAPÍTULO|Seção|Subseção)\s+[IVXLCDM]+(?:-[A-Z])?\b", re.IGNORECASE)
_VETOED = re.compile(r"\(VETADO\)[.;]?$")


# Escopo do passo 13 (spec 2026-11-09, seção 3): cesta básica (art. 125),
# regimes diferenciados e reduções de 30% e 60% (arts. 126 a 142) e alíquotas
# do Imposto Seletivo (arts. 419 a 423).
LC214_SCOPE = frozenset(f"art{n}" for n in [*range(125, 143), *range(419, 424)])


@dataclass(frozen=True)
class LcParagraph:
    text: str  # texto limpo, sem a parte tachada
    struck: bool  # o parágrafo inteiro estava tachado
    partly_struck: bool  # parte tachada, parte não


class _LcCollector(HTMLParser):
    """Junta o texto de cada <p>, separando o que está tachado do que não está."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[LcParagraph] = []
        self._stack: list[tuple[str, bool]] = []  # (tag, este elemento tacha?)
        self._plain: list[str] | None = None
        self._struck: list[str] | None = None

    def _striking(self) -> bool:
        return any(strikes for _, strikes in self._stack)

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self._close()
            # <p> sem </p>: o que estava aberto no parágrafo anterior (inclusive
            # um tachado) termina aqui, senão vazaria para este.
            for i in range(len(self._stack) - 1, -1, -1):
                if self._stack[i][0] == "p":
                    del self._stack[i:]
                    break
            self._plain, self._struck = [], []
        if tag == "br" and self._plain is not None:
            (self._struck if self._striking() else self._plain).append(" ")
        if tag in _VOID:
            return
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        self._stack.append((tag, tag in _STRIKE_TAGS or "text-decoration:line-through" in style))

    def handle_endtag(self, tag):
        # HTML do FrontPage nem sempre fecha tudo: desempilha até a tag que fecha.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if tag == "p":
            self._close()

    def handle_data(self, data):
        if self._plain is not None:
            (self._struck if self._striking() else self._plain).append(data)

    def _close(self) -> None:
        if self._plain is None:
            return
        plain = _clean("".join(self._plain))
        struck = _clean("".join(self._struck or []))
        if plain or struck:
            self.paragraphs.append(LcParagraph(text=plain, struck=bool(struck) and not plain, partly_struck=bool(struck) and bool(plain)))
        self._plain, self._struck = None, None

    def close(self):
        super().close()
        self._close()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def lc_paragraphs(html: str) -> list[LcParagraph]:
    """Parágrafos não vazios, em ordem, com a marcação de tachado."""
    collector = _LcCollector()
    collector.feed(html)
    collector.close()
    return collector.paragraphs


@dataclass
class LcParseResult:
    records: list[Record] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    struck: int = 0  # parágrafos de redação antiga descartados (no escopo)
    vetoed: list[str] = field(default_factory=list)  # ids vetados, sem registro


def _split_marks(text: str) -> tuple[str, list[str]]:
    """Separa as marcas de alteração do fim do texto. Devolve (texto, marcas)."""
    marks: list[str] = []
    while True:
        text = _LOOSE_LINK.sub("", text)
        m = _MARK.search(text)
        if not m:
            return text.strip(), marks
        marks.insert(0, m.group(0))
        text = text[: m.start()].rstrip()


def _amendment(marks: list[str], base: str) -> tuple[str, str, bool]:
    """(alteracao, origem, promulgado_depois_de_veto) a partir das marcas."""
    promulgated = any("Promulgação partes vetadas" in m for m in marks)
    for mark in marks:
        if m := _LC_AMENDMENT.search(mark):
            law = f"LC {m.group(1)}/{m.group(2)}"
            if mark.startswith("(Redação dada"):
                return "alterado", f"{base}, com redação dada pela {law}", promulgated
            if mark.startswith("(Incluíd"):
                return "incluido", f"{base}, incluído pela {law}", promulgated
    if promulgated:
        # A origem marca o caso; os efeitos (passo 13b) ficam indeterminados.
        return "original", f"{base}, parte promulgada após veto", True
    return "original", base, False


def _in_scope(article_id: str, norma: str, scope: set[str]) -> bool:
    return article_id.removeprefix(f"{norma}.") in scope


def parse_lc(html: str, *, norma: str, scope: Iterable[str]) -> LcParseResult:
    """Registros dos artigos do escopo (ex.: {"art125", "art126", ...}).

    `versao` é a própria norma (uma versão só: a redação atual compilada).
    """
    scope = set(scope)
    base = {"LC214": "LC 214/2025"}[norma]
    result = LcParseResult()
    ctx = _Context()
    current_article: str | None = None
    seen_articles: set[str] = set()
    seen_ids: set[str] = set()
    after_heading = False

    for paragraph in lc_paragraphs(html):
        text = paragraph.text
        if _HEADING.match(text):
            after_heading = True
            continue
        in_scope = current_article is not None and _in_scope(current_article, norma, scope)
        if paragraph.struck:
            result.struck += in_scope
            continue
        if after_heading:
            after_heading = False
            if _label(text, norma, _Context(art=ctx.art)) is None:
                continue  # nome do título/capítulo/seção
        text, marks = _split_marks(text)
        probe = _Context(art=ctx.art, par=ctx.par, inc=ctx.inc, ali=ctx.ali)
        labeled = _label(text, norma, probe)
        if labeled and labeled[2] is None:  # um artigo novo
            current_article = labeled[0]
            in_scope = _in_scope(current_article, norma, scope)
        if not in_scope:
            if labeled:
                ctx = probe
            continue
        if paragraph.partly_struck:
            result.errors.append(f"parágrafo parcialmente tachado em {current_article}: {text[:60]!r}")
            continue
        if labeled is None:
            result.warnings.append(f"parágrafo sem rótulo em {current_article}: {text[:60]!r}")
            continue
        ctx = probe
        rid, citacao, pai = labeled
        if rid.startswith(current_article) and pai is None:
            seen_articles.add(rid.removeprefix(f"{norma}."))
        if _VETOED.search(text) and len(text) < 40:
            result.vetoed.append(rid)
            continue
        if rid in seen_ids:
            result.errors.append(f"id repetido {rid}: redação antiga fora do tachado?")
            continue
        seen_ids.add(rid)
        alteracao, origem, promulgated = _amendment(marks, base)
        if promulgated:
            result.warnings.append(f"{rid}: promulgado depois de veto; efeitos ficam indeterminados")
        result.records.append(
            Record(id=rid, citacao=citacao, norma=norma, pai=pai, versao=norma, origem=origem, alteracao=alteracao, texto=text)
        )

    for missing in sorted(scope - seen_articles):
        result.errors.append(f"artigo do escopo não encontrado: {norma}.{missing}")
    return result
```

- [ ] **Step 5: rode e veja passar.** `uv run pytest tests/test_lc_structure.py tests/test_lc_structure_real.py -q` → 28 passed; `uv run pytest -q` → 380 passed.

- [ ] **Step 6: nota do passo.** Crie `docs/steps/13a-lc214-coleta-estrutura.md`:

````markdown
# Passo 13a: coleta e estrutura da LC 214

## O que mudou

- **`fetch.py` com várias fontes.** O dicionário `SOURCES` guarda, para cada norma, o nome, a URL oficial, os marcadores do corpo e o número que precisa estar no `<title>`. A opção `--source` escolhe a norma; sem ela, continua sendo a EC 132.
- **Bug achado no protótipo.** Os marcadores do passo 03 ("emenda constitucional" e "132") também aparecem na LC 214, que cita a EC. Com isso, a página da LC era aceita como se fosse a EC e sobrescrevia `ec132-2023.html`. Agora, se a página tem `<title>`, ele precisa conter o número da norma.
- **`corpus/raw/lc214-2025.html` e `.meta.json`:** coletados pelo navegador (`fetch(location.href)`) e gravados com `--source lc214-2025 --from-file`. Sha256 `0301816c…`, 5,4 MB.
- **`ingest/lc_structure.py`** (novo): HTML de lei compilada → registros. Reaproveita `Record`, `_Context` e `_label` do `structure.py`, que só ganhou o prefixo `LC214 → "LC 214/2025"`. Regras:
  - descarta a redação antiga, que vem num elemento com `line-through`;
  - um parágrafo parcialmente tachado é erro;
  - um id repetido é erro: seria redação antiga que escapou do tachado;
  - "(Redação dada / Incluído pela LC 227/2026)" vira `alteracao` e `origem` e sai do `texto`;
  - "(VETADO)" não vira registro;
  - títulos e seus nomes são ignorados;
  - um artigo do escopo ausente é erro.
- **`LC214_SCOPE`:** 23 artigos, os arts. 125 a 142 e 419 a 423 (spec do passo 13, seção 3).

## Como rodar

```
uv run pytest tests/test_lc_structure.py tests/test_lc_structure_real.py tests/test_fetch.py -v
uv run python -c "from pathlib import Path; from taxlaw.ingest.structure import decode_html; from taxlaw.ingest.lc_structure import parse_lc, LC214_SCOPE; r = parse_lc(decode_html(Path('corpus/raw/lc214-2025.html').read_bytes()), norma='LC214', scope=LC214_SCOPE); print(len(r.records), r.struck, r.vetoed, r.errors)"
```

## O que observar

- **Os números do HTML real.**
  - Os 23 artigos dão **162 registros**, sem erro nem aviso.
  - **3 tachados** foram descartados: as redações antigas do art. 142, II, e do art. 422, §§ 2º e 5º.
  - **2 vetados** ficaram sem registro: o art. 138, § 4º, e o art. 138, § 9º, II.
  - **4 dispositivos** foram tocados pela LC 227, contando o art. 126, § 6º, que foi incluído.
- **A página é a versão compilada:** quase 1.900 parágrafos tachados no total. Na lei inteira há 66 parágrafos **parcialmente** tachados, nenhum no escopo. Se o escopo crescer, eles viram erro, e não um texto errado em silêncio.
- **Ainda não muda nada no `dispositivos.json` nem nas ferramentas.** O build com duas fontes e os efeitos do art. 544 são o passo 13b.
- **Uma conferência que servia para uma norma não serve para duas.** "Tem 'emenda constitucional' e '132'" distinguia a EC de uma página de erro, mas não de outra norma que a cita.

## Pergunta de previsão

O parser descarta tudo o que está tachado. Se o Planalto mudar o jeito de marcar a redação antiga (por exemplo, para uma classe CSS em vez do `style`), o que acontece: o build falha, ou a redação antiga entra no corpus em silêncio? Qual regra do parser responde a isso?
````

- [ ] **Step 7: commit.** `git add src/taxlaw/ingest/structure.py src/taxlaw/ingest/lc_structure.py tests/test_lc_structure.py tests/test_lc_structure_real.py docs/steps/13a-lc214-coleta-estrutura.md && git commit -m "feat(step-13a): parser de lei compilada para os capítulos da LC 214"`

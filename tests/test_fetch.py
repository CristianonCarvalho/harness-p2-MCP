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

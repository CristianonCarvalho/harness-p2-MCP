"""Coleta da fonte oficial: o único módulo do pacote com acesso à rede.

Grava os bytes exatamente como vieram (sem decodificar: o Planalto usa
encoding antigo, e decidir o encoding é trabalho do `structure`) e, ao lado,
um `.meta.json` com url, data da coleta e sha256. O build lê `coletado_em`
desse arquivo, nunca do relógio, para ser determinístico.

Uso:
    uv run python -m taxlaw.ingest.fetch                     # baixa da URL oficial
    uv run python -m taxlaw.ingest.fetch --from-file pag.htm # página salva no navegador
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SOURCE_NAME = "ec132-2023"
SOURCE_URL = "https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc132.htm"
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


def check_looks_like_source(content: bytes) -> None:
    """Recusa o que claramente não é a EC 132: vazio, página de erro, captcha.

    A busca é em bytes e só com ASCII, que é igual em UTF-8 e windows-1252.
    """
    lowered = content.lower()
    if not content.strip():
        raise FetchError("o conteúdo está vazio")
    if b"emenda constitucional" not in lowered or b"132" not in lowered:
        raise FetchError(
            "o conteúdo não parece ser a EC 132/2023 (faltam 'Emenda Constitucional' "
            "e '132'); confira se a página salva é a certa"
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
    parser.add_argument("--from-file", type=Path, help="página salva no navegador")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)

    try:
        if args.from_file is not None:
            download, method = read_file(args.from_file), "arquivo"
        else:
            download, method = get(SOURCE_URL), "http"
        check_looks_like_source(download.content)
    except FetchError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    meta = build_meta(SOURCE_URL, download, today(), method)
    html_path, meta_path = paths_for(args.raw_dir, SOURCE_NAME)
    if meta_path.is_file():
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        if old.get("sha256") == meta["sha256"] and verify(args.raw_dir, SOURCE_NAME):
            # Mesmo texto: não regrava, para o git não mostrar diff só de data.
            print(f"sem mudança: {html_path.name} (sha256 {meta['sha256'][:12]}…)")
            return 0
        print(f"o texto mudou: sha256 {str(old.get('sha256'))[:12]}… → {meta['sha256'][:12]}…")
    save(args.raw_dir, SOURCE_NAME, download, meta)
    print(f"gravado: {html_path} ({meta['tamanho_bytes']} bytes, via {method})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

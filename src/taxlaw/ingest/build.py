"""Build do corpus: structure + effects + correções → corpus/dispositivos.json.

Uso:
    uv run python -m taxlaw.ingest.build            # gera e imprime o relatório
    uv run python -m taxlaw.ingest.build --check    # só confere se o arquivo está em dia

Regras (spec, seção 5):
- lê `coletado_em` e a URL do `.meta.json`, nunca do relógio;
- aborta, sem gravar nada, se o HTML não bater com o sha256 do meta, se o
  structure tiver erros, se faltar a estrutura mínima ou se alguma correção
  for inválida;
- correções de `efeitos_correcoes.yaml` vencem o automático e exigem
  `fundamento`;
- saída determinística: mesma entrada, mesmos bytes (o teste confere que o
  `dispositivos.json` versionado é exatamente o que o build gera hoje);
- `fonte_url` e `coletado_em` ficam uma vez só, no cabeçalho `fonte` (spec,
  seção 5, decisão de 2026-11-07): repetidos em cada registro, uma recoleta
  que muda uma vírgula mudaria 487 linhas e esconderia a mudança no diff.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

import yaml

from taxlaw.ingest.effects import Effects, effects_for, find_publication_date
from taxlaw.ingest.fetch import DEFAULT_RAW_DIR, SOURCE_NAME, paths_for, verify
from taxlaw.ingest.structure import Record, decode_html, paragraphs, parse

CORPUS_DIR = DEFAULT_RAW_DIR.parent
DEFAULT_CORRECTIONS = CORPUS_DIR / "efeitos_correcoes.yaml"
DEFAULT_OUTPUT = CORPUS_DIR / "dispositivos.json"

# Dispositivos que a EC traz por inteiro (novos) e o art. 23: se faltar
# algum, o corpus está quebrado, mesmo que o parser não reclame. (O caput do
# art. 195 não serve: no texto da EC ele aparece só como linha de pontos.)
MINIMUM_IDS = ("CF.art149-B", "CF.art156-A", "ADCT.art125", "EC132.art23")
EC_ARTICLES = range(1, 24)

_CORRECTION_KEYS = {"id", "versao", "efeitos_desde", "efeitos_ate", "fundamento"}


class BuildError(Exception):
    """Motivos para não gravar nada. Cada item é uma linha do relatório."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Correction:
    id: str
    versao: str
    efeitos_desde: date | None
    efeitos_ate: date | None
    fundamento: str


@dataclass
class BuildResult:
    text: str  # conteúdo de dispositivos.json
    report: list[str] = field(default_factory=list)


def _as_date(value: object, where: str, errors: list[str]) -> date | None:
    """YAML devolve `date` para 2027-01-01 sem aspas e `str` com aspas: aceita os dois."""
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    errors.append(f"{where}: data inválida {value!r} (use AAAA-MM-DD ou null)")
    return None


def load_corrections(text: str) -> list[Correction]:
    """Lê o YAML de correções. Junta todos os problemas antes de falhar."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict) or not isinstance(data.get("correcoes", []), list):
        raise BuildError(["efeitos_correcoes.yaml: esperado 'correcoes:' com uma lista"])
    errors: list[str] = []
    corrections: list[Correction] = []
    seen: set[tuple[str, str]] = set()
    for n, item in enumerate(data.get("correcoes") or [], start=1):
        where = f"correção {n}"
        if not isinstance(item, dict):
            errors.append(f"{where}: esperado um mapa com id, versao, efeitos_desde, efeitos_ate, fundamento")
            continue
        unknown = sorted(set(item) - _CORRECTION_KEYS)
        if unknown:
            errors.append(f"{where}: campo desconhecido {', '.join(unknown)}")
        rid, versao = item.get("id"), item.get("versao")
        if not isinstance(rid, str) or not isinstance(versao, str):
            errors.append(f"{where}: 'id' e 'versao' são obrigatórios")
            continue
        fundamento = item.get("fundamento")
        if not isinstance(fundamento, str) or not fundamento.strip():
            errors.append(f"{where} ({rid}, {versao}): 'fundamento' é obrigatório")
        desde = _as_date(item.get("efeitos_desde"), where, errors)
        ate = _as_date(item.get("efeitos_ate"), where, errors)
        if desde and ate and ate < desde:
            errors.append(f"{where} ({rid}, {versao}): efeitos_ate antes de efeitos_desde")
        if (rid, versao) in seen:
            errors.append(f"{where} ({rid}, {versao}): correção duplicada")
        seen.add((rid, versao))
        corrections.append(Correction(rid, versao, desde, ate, str(fundamento or "").strip()))
    if errors:
        raise BuildError(errors)
    return corrections


def apply_corrections(
    by_version: dict[tuple[str, str], Effects], corrections: list[Correction]
) -> dict[tuple[str, str], Effects]:
    """Correção vence o automático. Correção para versão inexistente é erro."""
    errors = [f"correção para versão inexistente: {c.id} ({c.versao})" for c in corrections if (c.id, c.versao) not in by_version]
    if errors:
        raise BuildError(errors)
    out = dict(by_version)
    for c in corrections:
        out[(c.id, c.versao)] = Effects(
            vigor_desde=c.efeitos_desde,
            efeitos_desde=c.efeitos_desde,
            efeitos_ate=c.efeitos_ate,
            fundamento=c.fundamento,
            metodo="correcao",
            fundamento_ate=c.fundamento if c.efeitos_ate else None,
        )
    return out


def check_minimum(records: list[Record]) -> list[str]:
    """Estrutura mínima esperada: se faltar, o parser perdeu algo grande."""
    ids = {r.id for r in records}
    errors = [f"estrutura mínima ausente: {rid}" for rid in MINIMUM_IDS if rid not in ids]
    errors += [f"artigo da EC ausente: EC132.art{n}" for n in EC_ARTICLES if f"EC132.art{n}" not in ids]
    return errors


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def render(records: list[Record], effects: dict[tuple[str, str], Effects], meta: dict) -> str:
    """JSON determinístico: cabeçalho `fonte` + registros ordenados por (id, artigo da EC)."""
    ordered = sorted(records, key=lambda r: (r.id, int(r.versao.removeprefix("EC132.art"))))
    rows = []
    for r in ordered:
        e = effects[(r.id, r.versao)]
        rows.append({
            "id": r.id,
            "citacao": r.citacao,
            "norma": r.norma,
            "pai": r.pai,
            "versao": r.versao,
            "origem": r.origem,
            "alteracao": r.alteracao,
            "texto": r.texto,
            "vigor_desde": _iso(e.vigor_desde),
            "efeitos_desde": _iso(e.efeitos_desde),
            "efeitos_ate": _iso(e.efeitos_ate),
            "fundamento_efeitos": e.fundamento,
            "fundamento_ate": e.fundamento_ate,
            "metodo": e.metodo,
        })
    document = {
        "fonte": {"url": meta["url"], "coletado_em": meta["coletado_em"], "sha256_html": meta["sha256"]},
        "dispositivos": rows,
    }
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def build(raw_dir: Path, corrections_text: str) -> BuildResult:
    """Pipeline inteiro em memória. Levanta BuildError em vez de gravar algo errado."""
    html_path, meta_path = paths_for(raw_dir, SOURCE_NAME)
    if not verify(raw_dir, SOURCE_NAME):
        raise BuildError([f"{html_path.name} ausente ou diferente do sha256 em {meta_path.name}"])
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    html = decode_html(html_path.read_bytes())

    parsed = parse(html)
    errors = list(parsed.errors) + check_minimum(parsed.records)
    if errors:
        raise BuildError(errors)
    result = effects_for(parsed.records, find_publication_date(t for _, t in paragraphs(html)))
    corrections = load_corrections(corrections_text)
    effects = apply_corrections(result.by_version, corrections)

    methods = Counter(e.metodo for e in effects.values())
    indeterminate = sorted(f"{rid} ({versao})" for (rid, versao), e in effects.items() if e.metodo == "indeterminado")
    report = [
        f"dispositivos: {len(parsed.records)} versões, {len({r.id for r in parsed.records})} ids",
        "por norma: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.norma for r in parsed.records).items())),
        "por método: " + ", ".join(f"{k} {v}" for k, v in sorted(methods.items())),
        f"correções aplicadas: {len(corrections)}",
        f"revogações (art. 22): {len(result.revocations)}",
        f"indeterminados: {len(indeterminate)}",
        *[f"  - {i}" for i in indeterminate],
        f"avisos: {len(parsed.warnings) + len(result.warnings)}",
        *[f"  - {w}" for w in parsed.warnings + result.warnings],
    ]
    return BuildResult(text=render(parsed.records, effects, meta), report=report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m taxlaw.ingest.build")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="não grava; sai com 1 se o arquivo estiver desatualizado")
    args = parser.parse_args(argv)

    try:
        corrections_text = args.corrections.read_text(encoding="utf-8") if args.corrections.is_file() else ""
        result = build(args.raw_dir, corrections_text)
    except BuildError as exc:
        print("build abortado; nada foi gravado:", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("\n".join(result.report))
    current = args.output.read_text(encoding="utf-8") if args.output.is_file() else None
    if args.check:
        if current == result.text:
            print(f"{args.output.name} em dia")
            return 0
        print(f"{args.output.name} desatualizado: rode o build sem --check", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.text, encoding="utf-8")
    print(f"gravado: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

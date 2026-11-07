"""As duas ferramentas do server como funções puras: argumentos → dicionário.

Sem MCP aqui (spec, seção 4: lógica separada do protocolo). O server (passo 10)
só expõe estas funções via stdio e converte `ToolError` em `isError`.

Regras que valem para as duas (spec, seção 6):
- a guarda de CPF/CNPJ roda antes de qualquer validação ou busca, em todo
  argumento de texto, e a mensagem nunca contém o número;
- entrada inválida → `ToolError("entrada_invalida", ...)`; "não encontrei" não
  é erro: volta `encontrado: false` com `motivo`;
- `data_referencia` ausente vira a data de hoje e é sempre ecoada;
- toda resposta traz `corpus{versao, coletado_em}`;
- a resposta só tem dados (texto da norma é dado, nunca instrução).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from taxlaw.corpus import DEFAULT_PATH, Corpus, load_corpus
from taxlaw.guard import describe_findings, find_taxpayer_ids
from taxlaw.search import Index, build_index, search
from taxlaw.versions import Choice, choose_version

MAX_QUERY_CHARS = 500
MAX_ID_CHARS = 200
SNIPPET_CHARS = 300
# Teto de `obter_dispositivo` (texto + textos dos filhos). Decisão de
# 2026-11-07: no corpus atual o maior caso tem 3.013 caracteres (EC, art. 9º),
# então nada real é cortado; o teto protege contra normas maiores (LC 214).
MAX_CHARS = 4000

OBS_PREVIOUS_WORDING = "redação anterior não incluída no corpus"
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ToolError(Exception):
    """Erro que o server devolve com `isError`: só `entrada_invalida` e `dados_de_contribuinte`."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"erro": self.code, "mensagem": self.message}


@dataclass(frozen=True)
class Context:
    """Corpus e índice carregados uma vez; as ferramentas só leem."""

    corpus: Corpus
    index: Index


def load_context(path: Path = DEFAULT_PATH) -> Context:
    corpus = load_corpus(path)
    return Context(corpus, build_index(corpus))


# ------------------------------------------------------------------ entrada


def _guard(**fields: object) -> None:
    """Bloqueia antes de tudo se algum argumento de texto tem CPF/CNPJ válido."""
    for name, value in fields.items():
        if isinstance(value, str):
            findings = find_taxpayer_ids(value)
            if findings:
                raise ToolError("dados_de_contribuinte", f"{describe_findings(findings)} no campo '{name}'")


def _reference_date(value: object, today: date | None) -> date:
    if value is None:
        return today or date.today()
    # fromisoformat aceita "20231221" e outras formas; a spec pede AAAA-MM-DD.
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ToolError("entrada_invalida", "data_referencia deve estar no formato AAAA-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError("entrada_invalida", "data_referencia não é uma data válida") from None


def _corpus_info(ctx: Context) -> dict:
    return {"versao": ctx.corpus.versao, "coletado_em": ctx.corpus.fonte["coletado_em"]}


# ------------------------------------------------------------------ saída


def _effects(choice: Choice) -> dict:
    v = choice.chosen
    return {
        "desde": v["efeitos_desde"],
        "ate": v["efeitos_ate"],
        "fundamento": v["fundamento_efeitos"],
        "fundamento_ate": v["fundamento_ate"],
        "metodo": v["metodo"],
        "produz_efeitos_na_data": choice.in_effect,
    }


def _other_versions(choice: Choice) -> list[dict]:
    return [{"versao": v["versao"], "efeitos": {"desde": v["efeitos_desde"], "ate": v["efeitos_ate"]}} for v in choice.others]


def _snippet(text: str) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    return text[: SNIPPET_CHARS - 1].rstrip() + "…"


def _observation(choice: Choice, when: date) -> str | None:
    """As duas observações da spec; None quando não há o que avisar."""
    v = choice.chosen
    start = date.fromisoformat(v["efeitos_desde"]) if v["efeitos_desde"] else None
    end = date.fromisoformat(v["efeitos_ate"]) if v["efeitos_ate"] else None
    if v["alteracao"] == "alterado" and start is not None and when < start:
        return OBS_PREVIOUS_WORDING
    if v["fundamento_ate"] and end is not None and when > end:
        return f"revogado a partir de {(end + timedelta(days=1)).isoformat()} ({v['fundamento_ate']})"
    return None


_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman(numeral: str) -> int:
    total = 0
    for current, following in zip(numeral, numeral[1:] + " "):
        value = _ROMAN[current]
        total += -value if _ROMAN.get(following, 0) > value else value
    return total


def _legal_order(rid: str) -> tuple:
    """Ordem do texto da lei: incisos e alíneas antes dos parágrafos; I, II, ..., IX, X (não alfabética)."""
    last = rid.rsplit(".", 1)[-1]
    if m := re.fullmatch(r"inc([IVXLC]+)", last):
        return (0, _roman(m.group(1)), "")
    if m := re.fullmatch(r"ali([a-z])", last):
        return (0, ord(m.group(1)), "")
    if last == "parunico":
        return (1, 1, "")
    if m := re.fullmatch(r"par([0-9]+)", last):
        return (1, int(m.group(1)), "")
    if m := re.fullmatch(r"art([0-9]+)(.*)", last):
        return (2, int(m.group(1)), m.group(2))
    return (3, 0, last)


def _children(ctx: Context, parent: dict, when: date) -> list[dict]:
    """Filhos diretos: a lista vem da versão do pai; o texto de cada um, da data (decisão de 2026-11-07)."""
    child_ids = dict.fromkeys(
        r["id"] for r in ctx.corpus.dispositivos if r["pai"] == parent["id"] and r["versao"] == parent["versao"]
    )
    children = []
    for cid in sorted(child_ids, key=_legal_order):
        choice = choose_version(ctx.corpus.versions(cid), when)
        v = choice.chosen
        children.append(
            {"id": cid, "versao": v["versao"], "citacao": v["citacao"], "texto": v["texto"], "produz_efeitos_na_data": choice.in_effect}
        )
    return children


def _fit(text: str, children: list[dict]) -> tuple[str, list[dict], bool]:
    """Aplica MAX_CHARS: o texto primeiro; filhos que não cabem ficam com texto null (o id continua)."""
    truncated = False
    if len(text) > MAX_CHARS:
        text, truncated = text[: MAX_CHARS - 1].rstrip() + "…", True
    budget = MAX_CHARS - len(text)
    fitted = []
    for child in children:
        if not truncated and len(child["texto"]) <= budget:
            budget -= len(child["texto"])
            fitted.append(child)
        else:
            truncated = True
            fitted.append({**child, "texto": None})
    return text, fitted, truncated


# ------------------------------------------------------------------ ferramentas


def buscar_dispositivos(ctx: Context, consulta: object, data_referencia: object = None, limite: object = 5, *, today: date | None = None) -> dict:
    """Busca por palavras; cada resultado mostra a versão que vale na data de referência."""
    _guard(consulta=consulta, data_referencia=data_referencia)
    if not isinstance(consulta, str) or not consulta.strip() or len(consulta) > MAX_QUERY_CHARS:
        raise ToolError("entrada_invalida", f"consulta deve ter de 1 a {MAX_QUERY_CHARS} caracteres")
    if isinstance(limite, bool) or not isinstance(limite, int) or not 1 <= limite <= 10:
        raise ToolError("entrada_invalida", "limite deve ser um inteiro de 1 a 10")
    when = _reference_date(data_referencia, today)

    found = search(ctx.index, consulta, limite)
    results = []
    for hit in found.hits:
        choice = choose_version(ctx.corpus.versions(hit.id), when)
        v = choice.chosen
        results.append(
            {
                "id": hit.id,
                "versao": v["versao"],
                "citacao": v["citacao"],
                "trecho": _snippet(v["texto"]),
                "pontuacao": hit.relevance,
                "efeitos": _effects(choice),
                "outras_versoes": _other_versions(choice),
            }
        )
    return {
        "encontrado": found.found,
        "consulta": consulta,
        "data_referencia": when.isoformat(),
        "resultados": results,
        "motivo": found.reason,
        "corpus": _corpus_info(ctx),
    }


def obter_dispositivo(ctx: Context, id: object, data_referencia: object = None, incluir_filhos: object = True, *, today: date | None = None) -> dict:
    """Um dispositivo pelo id, na versão que vale na data, com os filhos diretos."""
    _guard(id=id, data_referencia=data_referencia)
    if not isinstance(id, str) or not id.strip() or len(id) > MAX_ID_CHARS:
        raise ToolError("entrada_invalida", f"id deve ter de 1 a {MAX_ID_CHARS} caracteres")
    if not isinstance(incluir_filhos, bool):
        raise ToolError("entrada_invalida", "incluir_filhos deve ser true ou false")
    when = _reference_date(data_referencia, today)

    versions = ctx.corpus.versions(id)
    if not versions:
        return {
            "encontrado": False,
            "id": id,
            "data_referencia": when.isoformat(),
            "motivo": "id inexistente no corpus",
            "corpus": _corpus_info(ctx),
        }
    choice = choose_version(versions, when)
    v = choice.chosen
    children = _children(ctx, v, when) if incluir_filhos else []
    text, children, truncated = _fit(v["texto"], children)
    return {
        "encontrado": True,
        "id": id,
        "data_referencia": when.isoformat(),
        "versao": v["versao"],
        "citacao": v["citacao"],
        "norma": v["norma"],
        "origem": v["origem"],
        "alteracao": v["alteracao"],
        "texto": text,
        "filhos": children,
        "vigor_desde": v["vigor_desde"],
        "efeitos": _effects(choice),
        "outras_versoes": _other_versions(choice),
        "observacao": _observation(choice, when),
        "truncado": truncated,
        "fonte_url": ctx.corpus.fonte["url"],
        "corpus": _corpus_info(ctx),
    }

"""Escolha da versão de um dispositivo pela data de referência (spec, seção 6).

Um mesmo `id` pode ter várias versões, uma por artigo da EC que o inclui ou
altera, cada uma com seu intervalo [efeitos_desde, efeitos_ate]. Este módulo
responde: "qual texto vale nessa data?" e "ele produz efeitos nessa data?".

Três respostas possíveis para `in_effect` (`produz_efeitos_na_data`):
- True: a data cai dentro do intervalo de uma única versão;
- False: a data cai fora de todas (antes da primeira ou depois da última);
- None: não dá para saber (versão com `efeitos_desde` nulo, ou mais de uma
  versão possível). Nunca False no lugar de "não sei".

Fora de todas as versões, o dispositivo continua sendo devolvido (decisão de
2026-11-06): antes da primeira → a primeira; depois → a última que já começou.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Choice:
    chosen: dict  # a versão devolvida
    others: list[dict]  # as demais, na ordem do corpus (artigo da EC crescente)
    in_effect: bool | None  # produz_efeitos_na_data


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def status_at(version: dict, when: date) -> bool | None:
    """True se `when` está no intervalo da versão, False se fora, None se o início é desconhecido."""
    start = _day(version["efeitos_desde"])
    if start is None:
        return None
    end = _day(version["efeitos_ate"])  # None = sem término conhecido
    if when < start:
        return False
    if end is not None and when > end:
        return False
    return True


def choose_version(versions: list[dict], when: date) -> Choice:
    """A versão que vale em `when`, pelas regras da spec. `versions` não pode ser vazia."""
    if not versions:
        raise ValueError("um dispositivo sem versões não existe no corpus")
    statuses = [status_at(v, when) for v in versions]
    possible = [i for i, s in enumerate(statuses) if s is not False]

    if len(possible) == 1 and statuses[possible[0]] is True:
        index, in_effect = possible[0], True
    elif possible:
        # Mais de uma versão possível, ou uma só com início desconhecido:
        # devolve a mais antiga das possíveis e admite que não sabe.
        index, in_effect = min(possible, key=lambda i: (versions[i]["efeitos_desde"] is None, versions[i]["efeitos_desde"] or "", i)), None
    else:
        # Fora de todas (aqui todo início é conhecido, senão a versão seria
        # "possível"): a última que já começou; se nenhuma começou, a primeira.
        started = [i for i, v in enumerate(versions) if v["efeitos_desde"] <= when.isoformat()]
        if started:
            index = max(started, key=lambda i: (versions[i]["efeitos_desde"], i))
        else:
            index = min(range(len(versions)), key=lambda i: (versions[i]["efeitos_desde"], i))
        in_effect = False

    others = [v for i, v in enumerate(versions) if i != index]
    return Choice(versions[index], others, in_effect)

"""Leitura de `corpus/dispositivos.json` (gerado pelo build): só leitura, sem rede.

`versao` é o sha256 do arquivo: toda resposta das ferramentas o expõe como
`corpus.versao`, e o P3 sabe se duas execuções usaram o mesmo corpus.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# src/taxlaw/corpus.py → parents[2] é a raiz do repositório.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "corpus" / "dispositivos.json"


@dataclass(frozen=True)
class Corpus:
    fonte: dict
    dispositivos: tuple[dict, ...]
    versao: str
    _by_id: dict[str, list[dict]] = field(default_factory=dict, repr=False, compare=False)

    def ids(self) -> list[str]:
        """Ids distintos, em ordem."""
        return sorted(self._by_id)

    def versions(self, rid: str) -> list[dict]:
        """Versões de um id na ordem do arquivo (artigo da EC crescente); [] se não existe."""
        return list(self._by_id.get(rid, []))


def load_corpus(path: Path = DEFAULT_PATH) -> Corpus:
    raw = path.read_bytes()
    document = json.loads(raw)
    by_id: dict[str, list[dict]] = defaultdict(list)
    for row in document["dispositivos"]:
        by_id[row["id"]].append(row)
    return Corpus(
        fonte=document["fonte"],
        dispositivos=tuple(document["dispositivos"]),
        versao=hashlib.sha256(raw).hexdigest(),
        _by_id=dict(by_id),
    )

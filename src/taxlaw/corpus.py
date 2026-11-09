"""Leitura de `corpus/dispositivos.json` (gerado pelo build): só leitura, sem rede.

`versao` é o sha256 do arquivo: toda resposta das ferramentas o expõe como
`corpus.versao`, e o P3 sabe se duas execuções usaram o mesmo corpus.

Desde o passo 13b o corpus tem várias fontes (EC 132 e LC 214), num
cabeçalho `fontes` chaveado pelo nome da fonte. A fonte de cada registro sai
do prefixo da `versao`: "EC132.art3" → ec132-2023; "LC214" → lc214-2025.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# src/taxlaw/corpus.py → parents[2] é a raiz do repositório.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "corpus" / "dispositivos.json"

# Prefixo da `versao` → nome da fonte em `fontes` (e em corpus/raw).
SOURCE_OF_VERSION = {"EC132": "ec132-2023", "LC214": "lc214-2025"}


def source_name(versao: str) -> str:
    """'EC132.art3' → 'ec132-2023'; 'LC214' → 'lc214-2025'."""
    return SOURCE_OF_VERSION[versao.split(".")[0]]


@dataclass(frozen=True)
class Corpus:
    fontes: dict  # nome da fonte → {url, coletado_em, sha256_html}
    dispositivos: tuple[dict, ...]
    versao: str
    _by_id: dict[str, list[dict]] = field(default_factory=dict, repr=False, compare=False)

    def ids(self) -> list[str]:
        """Ids distintos, em ordem."""
        return sorted(self._by_id)

    def versions(self, rid: str) -> list[dict]:
        """Versões de um id na ordem do arquivo (artigo da EC crescente); [] se não existe."""
        return list(self._by_id.get(rid, []))

    def source_of(self, row: dict) -> dict:
        """A fonte (url, coletado_em, sha256_html) de onde veio um registro."""
        return self.fontes[source_name(row["versao"])]

    @property
    def coletado_em(self) -> str:
        """A coleta mais antiga entre as fontes: o limite de quão desatualizado o corpus pode estar."""
        return min(f["coletado_em"] for f in self.fontes.values())


def load_corpus(path: Path = DEFAULT_PATH) -> Corpus:
    raw = path.read_bytes()
    document = json.loads(raw)
    by_id: dict[str, list[dict]] = defaultdict(list)
    for row in document["dispositivos"]:
        by_id[row["id"]].append(row)
    return Corpus(
        fontes=document["fontes"],
        dispositivos=tuple(document["dispositivos"]),
        versao=hashlib.sha256(raw).hexdigest(),
        _by_id=dict(by_id),
    )

"""Ingestão do corpus: fetch (rede) → structure → effects → build (puros).

Só `fetch` toca a rede. Os demais módulos leem os arquivos de `corpus/raw/`,
então testes e server funcionam offline.
"""

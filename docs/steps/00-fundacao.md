# Passo 00: fundação do repositório

## O que mudou

- `pyproject.toml` com layout `src/`, pacote `taxlaw`, pytest como dependência de desenvolvimento e nenhuma dependência de runtime.
- `.gitignore` protegendo `.env`, `traces/` e `runs/` desde o primeiro commit de código.
- `src/taxlaw/__init__.py` com `__version__` e um teste que confirma que o pacote é importável.
- README esqueleto e `AGENTS.md` com stack, comando de testes e convenções.

## Como rodar

    uv sync
    uv run pytest

## O que observar

- Por que layout `src/`: sem ele, `import taxlaw` funcionaria só por estar na raiz, escondendo um pacote mal configurado. Com ele, o teste só passa se o uv instalou o pacote.
- `traces/` já está no `.gitignore` antes de existir: o passo 01 vai gravar ali o log das mensagens MCP, e o roadmap proíbe commitar traces.
- Nenhuma dependência de runtime: `mcp` e `pyyaml` entram quando forem usados (YAGNI).

## Pergunta de previsão

No passo 01 o Claude Code vai iniciar um server MCP nosso por stdio. Qual será a primeira mensagem que ele envia: `initialize` (protocolo antigo) ou `server/discover` (revisão 2026-07-28)? E o que acontece se o server não souber responder?

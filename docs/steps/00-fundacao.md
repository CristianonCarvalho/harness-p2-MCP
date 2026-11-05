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

## O que deu errado na execução

O gate do MeisterRouter roda os testes num worktree novo, sem `.venv`, e por isso caiu no Python do próprio Meister: `ModuleNotFoundError: No module named 'taxlaw'`. A tentativa de reparo acrescentou `pythonpath = ["src"]` ao `pyproject.toml`. O teste passou, mas o atalho anula o motivo do layout `src/`: o import funciona mesmo com o pacote mal configurado. É a mesma família do `conftest.py` do P1, que fazia o teste passar sem corrigir o problema.

Correção: a linha saiu do `pyproject.toml`, e o `meister.config.yaml` passou a ter `gate.install: "uv sync --quiet"`, que cria o `.venv` com o pacote instalado antes do gate. A causa estava no ambiente do gate, não no projeto.

Lição: um reparo automático otimiza para "o gate passa", não para "o problema foi entendido". Todo reparo precisa de revisão do diff.

# P2, passo 00: fundação do repositório (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-05-p2-passo-00-fundacao.json`. É um passo de estudo: mudanças pequenas, legíveis e comentadas. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deixar o repositório pronto para os passos seguintes: pacote Python `taxlaw` instalável com uv, pytest funcionando, `.gitignore` protegendo segredos e traces, README e `AGENTS.md` com o contexto do projeto.

**Architecture:** Layout `src/` com o pacote `taxlaw` (vazio por enquanto, só `__version__`). Nenhuma dependência de runtime ainda: `mcp` entra no passo 10 e `pyyaml` no passo 07, quando forem usados.

**Tech Stack:** Python 3.13, uv, hatchling, pytest.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md`

## Global Constraints

- Python `>=3.13`; build com `hatchling`; dev só `pytest`. Nenhuma dependência de runtime neste passo.
- Testes 100% offline; nenhum teste depende do diretório atual (caminhos a partir de `Path(__file__)`); nada de `conftest.py`.
- `.env`, `traces/` e execuções locais nunca são commitados. Nunca exibir chaves de API.
- Só dados públicos ou sintéticos.
- Mensagens ao usuário, comentários e notas em português; identificadores de código em inglês.
- Comentários didáticos: explicam o porquê de cada bloco, não repetem o código.
- Não editar `CLAUDE.md`, `CODEX.md`, `meister.config.yaml`, `.meister/` nem `docs/superpowers/`.
- A nota do passo tem as seções `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Review Focus

- `uv run pytest` passa igual na raiz, em `cd tests && uv run pytest` e de fora do repositório (verificação no Step 4).
- `git status` depois de `uv sync` não mostra `.venv/`, `__pycache__/` nem `.pytest_cache/` (verificação no Step 4).
- Um `.env` ou um arquivo em `traces/` criado na raiz não aparece no `git status` (verificação no Step 4).
- `import taxlaw` funciona sem `PYTHONPATH` manual, ou seja, o pacote está instalado pelo uv (teste no Step 1).

---

### Task 1: Fundação do repositório

**Files:**
- Create: `pyproject.toml`
- Create: `uv.lock`
- Create: `.gitignore`
- Create: `src/taxlaw/__init__.py`
- Test: `tests/test_package.py`
- Create: `README.md`
- Modify: `AGENTS.md`
- Create: `docs/steps/00-fundacao.md`

**Interfaces:**
- Produces: pacote `taxlaw` importável, com `taxlaw.__version__ == "0.1.0"`; comando de testes `uv run pytest`; diretório `traces/` ignorado pelo git (usado pelo passo 01).

- [ ] **Step 1: teste que falha.** Crie `tests/test_package.py`:

```python
"""Teste mínimo do passo 00: o pacote existe e é importável.

Parece trivial, mas confirma três coisas de uma vez: o layout src/ está
certo, o uv instalou o pacote em modo editável e o pytest acha os testes.
"""

import taxlaw


def test_package_has_version():
    # A versão vive num lugar só (__init__.py) para não divergir do pyproject.
    assert taxlaw.__version__ == "0.1.0"
```

Rode `uv run pytest tests/test_package.py -v`. Esperado: falha (ainda não há `pyproject.toml` nem pacote).

- [ ] **Step 2: implementação.**

`pyproject.toml`:

```toml
# Configuração do projeto P2: MCP server de legislação da reforma tributária.
# O layout src/ evita que os testes importem o código "por acaso" a partir
# do diretório atual: só funciona se o pacote estiver instalado de verdade.

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "taxlaw"
version = "0.1.0"
description = "MCP server de legislação pública da reforma tributária (EC 132/2023)"
readme = "README.md"
requires-python = ">=3.13"
dependencies = []

[dependency-groups]
dev = ["pytest"]

[tool.hatch.build.targets.wheel]
packages = ["src/taxlaw"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`src/taxlaw/__init__.py`:

```python
"""Pacote taxlaw: busca e citação de dispositivos da reforma tributária.

Por enquanto só guarda a versão. Os módulos (guard, search, tools, server
e ingest) chegam nos próximos passos, um por vez.
"""

__version__ = "0.1.0"
```

`.gitignore`:

```gitignore
# Segredos: nunca vão para o repositório.
.env

# Traces e execuções locais (ex.: log de mensagens MCP do passo 01).
traces/
runs/

# Ambiente e caches do Python.
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

Rode `uv sync` para gerar `uv.lock` e o ambiente.

`README.md` (esqueleto; as seções crescem nos próximos passos):

```markdown
# P2: MCP server da reforma tributária

MCP server que busca dispositivos da reforma tributária (EC 132/2023) e responde
sempre com o dispositivo citado e a data a partir da qual ele produz efeitos.
Projeto de estudo do roadmap "Engenharia de Software com Agentes de IA" (Fase 2).

## Estado

Em construção, um passo por vez. Cada passo tem uma nota em `docs/steps/`.

## Como rodar os testes

    uv sync
    uv run pytest

## Dados

Só normas públicas (texto oficial do Planalto). Nenhum dado de contribuinte,
nem em testes.

## Decisões e limites

Ver `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md`.
```

`AGENTS.md`: substitua os três comentários da seção `## Project context` por:

```markdown
- **Stack:** Python 3.13, uv, hatchling, pytest. Pacote `taxlaw` em `src/`.
- **Test command:** `uv run pytest`
- **Conventions:** identificadores em inglês; comentários, mensagens e notas em português; comentários didáticos explicam o porquê. Testes offline, sem `conftest.py`, independentes do diretório atual. Só dados públicos ou sintéticos: nunca CPF/CNPJ válido escrito no repositório.
```

Mantenha o restante do `AGENTS.md` como está.

- [ ] **Step 3: teste passa.** `uv run pytest tests/test_package.py -v`. Esperado: `1 passed`.

- [ ] **Step 4: verificações.**
  - `uv run pytest -q`, `cd tests && uv run pytest -q` e, da raiz, `cd /tmp && uv run --project "$OLDPWD" pytest "$OLDPWD/tests" -q`: todos `1 passed`.
  - `touch .env && mkdir -p traces && touch traces/x.jsonl && git status --short`: não lista `.env`, `traces/`, `.venv/`, `__pycache__/` nem `.pytest_cache/`. Depois `rm .env traces/x.jsonl`.

- [ ] **Step 5: nota do passo.** Crie `docs/steps/00-fundacao.md`:

```markdown
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
```

- [ ] **Step 6: commit.** `git add pyproject.toml uv.lock .gitignore src/taxlaw/__init__.py tests/test_package.py README.md AGENTS.md docs/steps/00-fundacao.md` e `git commit -m "feat(step-00): fundação do repositório"`.

---

## Depois da execução (arquiteto, fora do Meister)

1. Revisar o diff e rodar `uv run pytest` na raiz.
2. Commitar também `CLAUDE.md`, `CODEX.md` (gerados antes) e os planos: `docs: regras de agentes e plano do passo 00`.
3. Merge em `main` (se a execução usou branch), tag `step-00`.
4. Criar o repositório público no GitHub e dar push, **só depois de confirmar com o usuário** nome e visibilidade.
5. Parar e esperar o usuário estudar o passo.

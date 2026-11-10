# Imagem do taxlaw em modo HTTP (spec 2026-11-10-deploy-vps-design).
# Só o necessário para servir: código, dependências travadas e o corpus gerado.
# Fora da imagem: o HTML bruto (5 MB), os testes, o .git e qualquer .env.

# uv em versão fixa, copiado da imagem oficial (sem instalar nada pela rede no build do app).
FROM ghcr.io/astral-sh/uv:0.11.18 AS uv

FROM python:3.13-slim

COPY --from=uv /uv /usr/local/bin/uv

# Bytecode compilado no build (o sistema de arquivos roda só de leitura) e
# nenhum .pyc escrito em tempo de execução.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências exatamente as do uv.lock, sem as de desenvolvimento (pytest).
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# O pacote fica instalado em modo editável apontando para /app/src: assim
# corpus.py acha /app/corpus/dispositivos.json pelo caminho relativo ao código.
COPY corpus/dispositivos.json ./corpus/dispositivos.json
RUN uv sync --frozen --no-dev

# Usuário sem privilégio: o processo não roda como root.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin taxlaw
USER taxlaw

# Domínio público aceito no cabeçalho Host (o compose pode sobrescrever, ex.: localhost:8020).
ENV TAXLAW_ALLOWED_HOST=mcpreforma.cristianocarvalho.cloud
EXPOSE 8000

# Saúde = a porta abriu. Não faz requisição MCP: /mcp exige token.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"]

# 0.0.0.0 dentro do container: quem restringe o acesso é o compose (127.0.0.1:8020 no host).
CMD ["sh", "-c", "exec /app/.venv/bin/python -m taxlaw.http --host 0.0.0.0 --port 8000 --allowed-host \"$TAXLAW_ALLOWED_HOST\""]

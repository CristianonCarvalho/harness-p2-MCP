# P2, passo extra: deploy do taxlaw na VPS (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-10-p2-deploy-vps.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** os arquivos que publicam o taxlaw (modo HTTP com token) na VPS: imagem Docker endurecida, compose só em 127.0.0.1:8020, site e limite de taxa do nginx, roteiro de deploy e testes que prendem as decisões de segurança.

**Architecture:** só arquivos novos de infraestrutura e documentação, mais um teste offline. Nenhum código Python de produção muda. O deploy em si (clone, `.env`, `docker compose up`, nginx e certbot) acontece depois do merge, seguindo `docs/deploy.md`.

**Tech Stack:** Docker (`python:3.13-slim`, `ghcr.io/astral-sh/uv:0.11.18`), Docker Compose, nginx, pytest, pyyaml (já é dependência).

**Spec:** `docs/superpowers/specs/2026-11-10-deploy-vps-design.md`

## Global Constraints

- Nenhum segredo em arquivo versionado: o token só existe no `.env` da VPS (e no do Mac, para teste local), que está no `.gitignore` e no `.dockerignore`.
- Porta publicada só em `127.0.0.1:8020` (a 8000 da VPS é de outro app); domínio `mcpreforma.cristianocarvalho.cloud`.
- Container: usuário sem privilégio, `read_only`, `cap_drop: ALL`, `no-new-privileges`, teto de memória e CPU.
- Nenhum código Python de produção muda; `pyproject.toml`, `uv.lock` e `.gitignore` não mudam.
- Testes 100% offline e independentes do diretório atual (sem daemon Docker, sem rede); nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes.
- Mensagens, comentários e documentação em português.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `src/`, `client/`, `corpus/`, `.claude/`, `.kiro/`, `hooks/`, `.mcp.json`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-10)

- VPS (`ssh tradeomqs-vps-agente`, só leitura): Ubuntu 24.04.4; `agente` no grupo `docker`, `sudo` com senha; nginx do sistema em 80/443 com sites por subdomínio de `cristianocarvalho.cloud` e certbot; portas ocupadas em 127.0.0.1: 8000, 6080, 65529; sem `uv`; `mcpreforma.cristianocarvalho.cloud` já resolve para 179.198.110.134.
- No Mac (Docker 29.6), com estes arquivos: `TAXLAW_ALLOWED_HOST=localhost:8020 docker compose up -d --build` → imagem de 386 MB, container `healthy`; sem token → 401; o cliente com `--url http://localhost:8020/mcp` traz `LC214.art125`; `Host: 127.0.0.1:8020` (fora da lista) recusado e registrado como "Invalid Host header: 127.0.0.1:8020"; processo `uid=10001(taxlaw)`; `touch /app/x` → "Read-only file system"; o token não aparece em `docker compose logs`.
- `nginx -t` num container `nginx:1.27-alpine` com os dois arquivos em `conf.d`: ok; só com o site: `[emerg] zero size shared memory zone "mcpreforma"`.
- Mutações no protótipo (todas quebram um teste): porta sem `127.0.0.1`, `read_only: false`, `USER root`, `COPY . .`, `.env` fora do `.dockerignore`, nginx sem repassar `Host`, nginx ecoando `$http_authorization`, roteiro com `cat .env`, `proxy_pass` para a porta 8000.

## Review Focus

- Porta publicada para a internet sem passar pelo nginx (teste `test_compose_publishes_only_on_localhost`).
- O token entrando na imagem ou no git (testes `test_dockerignore_keeps_secrets_and_bulk_out_of_the_image`, `test_env_is_gitignored_and_example_has_no_value` e `test_no_token_written_in_deploy_files`).
- O nginx sem repassar o `Host` (o server recusaria tudo com 421) ou apontando para a porta errada (teste `test_nginx_site_proxies_to_the_container_with_host_and_limits`).
- A zona de limite de taxa dentro do site, o que quebra o `nginx -t` (teste `test_rate_limit_zone_is_defined_separately_for_the_http_block`).
- O roteiro imprimindo o token na tela (teste `test_deploy_guide_installs_zone_before_site_and_never_prints_the_token`).

---

### Task 1: Arquivos de deploy, roteiro e testes

**Files:**
- Create: `Dockerfile`
- Create: `compose.yaml`
- Create: `.dockerignore`
- Create: `.env.example`
- Create: `deploy/nginx-mcpreforma.conf`
- Create: `deploy/nginx-mcpreforma-ratelimit.conf`
- Create: `docs/deploy.md`
- Create: `tests/test_deploy.py`
- Create: `docs/steps/deploy.md`

**Interfaces:**
- Consumes: `python -m taxlaw.http --host --port --allowed-host` e a variável `TAXLAW_HTTP_TOKEN` (passo HTTP); `pyproject.toml`, `uv.lock`, `README.md`, `src/`, `corpus/dispositivos.json`; `.gitignore` (já contém `.env`).
- Produces: a imagem `mcpreforma-taxlaw:latest` (via `docker compose up -d --build`), o serviço `taxlaw` em `127.0.0.1:8020`, os arquivos do nginx e o roteiro `docs/deploy.md`.

- [ ] **Step 1: testes que falham.** Crie `tests/test_deploy.py`:

```python
"""Os arquivos de deploy da VPS (spec 2026-11-10-deploy-vps-design).

Offline e só de leitura: nada de daemon Docker nem de rede. Estes testes
prendem as decisões de segurança do deploy, para que ninguém as afrouxe sem
perceber: porta só em 127.0.0.1, container endurecido, segredos fora do git e
da imagem, nginx sem logar o token, e a mesma porta e o mesmo domínio nos
três arquivos. O build de verdade foi verificado à mão (Mac e VPS).
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "mcpreforma.cristianocarvalho.cloud"
HOST_PORT = 8020


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def compose_service() -> dict:
    return yaml.safe_load(read("compose.yaml"))["services"]["taxlaw"]


def dockerfile_instructions() -> list[str]:
    """Instruções do Dockerfile, com as continuações (\\) juntadas e sem comentários."""
    text = re.sub(r"\\\n\s*", " ", read("Dockerfile"))
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


# ------------------------------------------------------------------ compose


def test_compose_publishes_only_on_localhost():
    assert compose_service()["ports"] == [f"127.0.0.1:{HOST_PORT}:8000"]


def test_compose_reads_the_token_from_env_file_and_restarts():
    service = compose_service()
    assert service["env_file"] == ".env"
    assert service["restart"] == "unless-stopped"
    assert "TAXLAW_HTTP_TOKEN" not in str(service.get("environment", {}))  # o token não fica no compose


def test_compose_is_hardened():
    service = compose_service()
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["mem_limit"] and service["cpus"]


def test_compose_default_allowed_host_is_the_domain():
    assert compose_service()["environment"]["TAXLAW_ALLOWED_HOST"] == f"${{TAXLAW_ALLOWED_HOST:-{DOMAIN}}}"


# ------------------------------------------------------------------ Dockerfile


def test_dockerfile_runs_as_non_root():
    users = [line.split()[1] for line in dockerfile_instructions() if line.startswith("USER ")]
    assert users and users[-1] not in {"root", "0"}


def test_dockerfile_installs_the_locked_runtime_only():
    assert any(line == "RUN uv sync --frozen --no-dev" for line in dockerfile_instructions())


def test_dockerfile_copies_only_what_it_serves():
    copies = [line for line in dockerfile_instructions() if line.startswith("COPY ")]
    assert not any(re.fullmatch(r"COPY \. \S+", line) for line in copies), "COPY . copiaria tudo, até segredos"
    assert not any("corpus/raw" in line for line in copies)
    assert "COPY corpus/dispositivos.json ./corpus/dispositivos.json" in copies


def test_dockerfile_starts_the_http_server_with_allowed_host():
    instructions = dockerfile_instructions()
    cmd = next(line for line in reversed(instructions) if line.startswith("CMD "))
    assert "-m taxlaw.http" in cmd and "--allowed-host" in cmd and "--port 8000" in cmd
    assert f"ENV TAXLAW_ALLOWED_HOST={DOMAIN}" in instructions


def test_dockerfile_pins_the_uv_image():
    assert re.search(r"^FROM ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+ AS uv$", "\n".join(dockerfile_instructions()), re.MULTILINE)


# ------------------------------------------------------------------ segredos


def test_dockerignore_keeps_secrets_and_bulk_out_of_the_image():
    entries = {line.strip() for line in read(".dockerignore").splitlines() if line.strip() and not line.startswith("#")}
    assert {".env", ".git", "tests/", "corpus/raw/"} <= entries


def test_env_is_gitignored_and_example_has_no_value():
    assert ".env" in [line.strip() for line in read(".gitignore").splitlines()]
    values = [line for line in read(".env.example").splitlines() if line.startswith("TAXLAW_HTTP_TOKEN=")]
    assert values == ["TAXLAW_HTTP_TOKEN="]


def test_no_token_written_in_deploy_files():
    # Um token gerado por token_urlsafe(32) tem 43 caracteres de [A-Za-z0-9_-].
    for path in [ROOT / "compose.yaml", ROOT / "Dockerfile", ROOT / ".env.example", *sorted((ROOT / "deploy").iterdir())]:
        assert not re.search(r"Bearer\s+[A-Za-z0-9_-]{20,}|TAXLAW_HTTP_TOKEN=[A-Za-z0-9_-]{20,}", path.read_text(encoding="utf-8")), path


# ------------------------------------------------------------------ nginx


def test_nginx_site_proxies_to_the_container_with_host_and_limits():
    site = read("deploy/nginx-mcpreforma.conf")
    assert f"server_name {DOMAIN};" in site
    assert f"proxy_pass http://127.0.0.1:{HOST_PORT};" in site
    assert "proxy_set_header Host $host;" in site  # o server confere o Host
    assert "limit_req zone=mcpreforma" in site and "limit_req_status 429;" in site
    assert "client_max_body_size 64k;" in site


def test_rate_limit_zone_is_defined_separately_for_the_http_block():
    # limit_req_zone só vale no bloco http: fica num arquivo próprio de conf.d.
    zone = read("deploy/nginx-mcpreforma-ratelimit.conf")
    assert re.search(r"^limit_req_zone \$binary_remote_addr zone=mcpreforma:\d+m rate=\d+r/s;$", zone, re.MULTILINE)
    assert "limit_req_zone" not in read("deploy/nginx-mcpreforma.conf")


def test_nginx_never_logs_the_authorization_header():
    for name in ("deploy/nginx-mcpreforma.conf", "deploy/nginx-mcpreforma-ratelimit.conf"):
        assert "$http_authorization" not in read(name), name


# ------------------------------------------------------------------ documentação


def test_deploy_guide_installs_zone_before_site_and_never_prints_the_token():
    guide = read("docs/deploy.md")
    assert guide.index("mcpreforma-ratelimit.conf") < guide.index("sites-enabled")
    assert "certbot --nginx -d " + DOMAIN in guide
    assert "umask 077" in guide
    assert not re.search(r"cat\s+\S*\.env\b", guide), "o roteiro não deve imprimir o .env na tela"
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_deploy.py -q` → falhas com `FileNotFoundError` (os arquivos de deploy ainda não existem).

- [ ] **Step 3: imagem.** Crie `Dockerfile`:

```dockerfile
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
```

e `.dockerignore`:

```
# Nada disto vai para a imagem (segredos, histórico, testes e o HTML bruto de 5 MB).
.git
.venv
.env
tests/
corpus/raw/
docs/
traces/
runs/
__pycache__/
**/__pycache__/
.pytest_cache/
.meister/
.claude/
.kiro/
client/
echo/
hooks/
meister.config.yaml*
```

- [ ] **Step 4: compose e exemplo de ambiente.** Crie `compose.yaml`:

```yaml
# taxlaw via HTTP na VPS (spec 2026-11-10-deploy-vps-design).
# Uso: docker compose up -d --build   (na pasta ~/mcpreforma, com o .env ao lado)
services:
  taxlaw:
    build: .
    image: mcpreforma-taxlaw:latest
    # Só a própria máquina alcança o container; de fora, só pelo nginx (HTTPS).
    ports:
      - "127.0.0.1:8020:8000"
    # TAXLAW_HTTP_TOKEN (nunca no git: veja .env.example).
    env_file: .env
    environment:
      TAXLAW_ALLOWED_HOST: ${TAXLAW_ALLOWED_HOST:-mcpreforma.cristianocarvalho.cloud}
    restart: unless-stopped
    # Endurecimento: sistema de arquivos só de leitura, nenhuma capacidade de
    # kernel, sem ganho de privilégio e com teto de memória e CPU.
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    security_opt:
      - "no-new-privileges:true"
    mem_limit: 512m
    cpus: 1.0
```

e `.env.example`:

```
# Copie para .env (que nunca vai para o git) e preencha. Gere o token NA VPS:
#   umask 077 && echo "TAXLAW_HTTP_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > .env
TAXLAW_HTTP_TOKEN=
```

- [ ] **Step 5: nginx.** Crie `deploy/nginx-mcpreforma-ratelimit.conf`:

```nginx
# Instalar em /etc/nginx/conf.d/mcpreforma-ratelimit.conf
# (conf.d é incluído dentro do bloco http, o único lugar onde limit_req_zone vale).
# 10 requisições por segundo por IP; o site usa esta zona com rajada de 20.
limit_req_zone $binary_remote_addr zone=mcpreforma:10m rate=10r/s;
```

e `deploy/nginx-mcpreforma.conf`:

```nginx
# Instalar em /etc/nginx/sites-available/mcpreforma (+ link em sites-enabled).
# O HTTPS entra depois, pelo certbot --nginx, que edita este arquivo.
server {
    listen 80;
    listen [::]:80;
    server_name mcpreforma.cristianocarvalho.cloud;

    location / {
        # Limite de taxa por IP (zona em conf.d/mcpreforma-ratelimit.conf).
        limit_req zone=mcpreforma burst=20 nodelay;
        limit_req_status 429;

        # Igual ao limite do server (64 KB): recusa cedo, no nginx.
        client_max_body_size 64k;

        proxy_pass http://127.0.0.1:8020;
        proxy_http_version 1.1;
        # O server confere o Host (proteção contra DNS rebinding): repasse o original.
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_buffering off;
    }
}
```

- [ ] **Step 6: roteiro.** Crie `docs/deploy.md`:

````markdown
# Deploy do taxlaw na VPS

Publica o server em **`https://mcpreforma.cristianocarvalho.cloud/mcp`** (modo HTTP com token), a partir de `~/mcpreforma` na VPS. Design: [`docs/superpowers/specs/2026-11-10-deploy-vps-design.md`](superpowers/specs/2026-11-10-deploy-vps-design.md).

```
cliente MCP ──HTTPS──▶ nginx da VPS (certbot, limite de taxa) ──▶ 127.0.0.1:8020 ──▶ container taxlaw (porta 8000)
```

Regras que valem em todos os passos:
- **o token nunca aparece na tela, no git nem num log.** Ele é gerado na VPS, direto no `.env` com permissão 600, e só sai de lá para a área de transferência do seu Mac;
- os comandos do usuário `agente` não usam sudo. **Os do nginx e do certbot exigem sudo** e estão marcados.

## 1. Primeira instalação (como `agente`)

```
ssh tradeomqs-vps-agente
git clone https://github.com/CristianonCarvalho/harness-p2-MCP.git ~/mcpreforma
cd ~/mcpreforma
umask 077 && echo "TAXLAW_HTTP_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > .env
docker compose up -d --build
docker compose ps                      # espere "healthy"
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8020/mcp -d '{}'   # 401: está de pé e exige token
```

## 2. nginx e HTTPS (com sudo)

A zona do limite de taxa só vale no bloco `http` do nginx, então ela vai **antes**, em `conf.d`. Sem ela, o `nginx -t` falha com `zero size shared memory zone "mcpreforma"`.

```
cd ~/mcpreforma
sudo cp deploy/nginx-mcpreforma-ratelimit.conf /etc/nginx/conf.d/mcpreforma-ratelimit.conf
sudo cp deploy/nginx-mcpreforma.conf /etc/nginx/sites-available/mcpreforma
sudo ln -s /etc/nginx/sites-available/mcpreforma /etc/nginx/sites-enabled/mcpreforma
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d mcpreforma.cristianocarvalho.cloud
```

O certbot edita o site para escutar na porta 443, com o certificado, e redirecionar o `http://`, como nos outros sites da VPS.

## 3. Verificação (do seu Mac)

```
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://mcpreforma.cristianocarvalho.cloud/mcp -d '{}'   # 401
curl -s -o /dev/null -w "%{http_code}\n" http://mcpreforma.cristianocarvalho.cloud/mcp                    # 301 para https
ssh tradeomqs-vps-agente 'sed -n "s/^TAXLAW_HTTP_TOKEN=//p" ~/mcpreforma/.env' | pbcopy                # token → área de transferência
export TAXLAW_HTTP_TOKEN="$(pbpaste)"
uv run python client/taxlaw_client.py --url https://mcpreforma.cristianocarvalho.cloud/mcp buscar "cesta básica"
for i in $(seq 1 40); do curl -s -o /dev/null -w "%{http_code} " -X POST https://mcpreforma.cristianocarvalho.cloud/mcp -d '{}'; done; echo   # aparecem 429
```

## 4. Claude Code apontando para o server remoto

No **seu** `~/.claude.json` ou com `claude mcp add`, nunca no `.mcp.json` do repositório, porque o token não pode ir para o git:

```json
{"mcpServers": {"taxlaw-remoto": {"type": "http", "url": "https://mcpreforma.cristianocarvalho.cloud/mcp", "headers": {"Authorization": "Bearer ${TAXLAW_HTTP_TOKEN}"}}}}
```

## 5. Operação (como `agente`, em `~/mcpreforma`)

- **Atualizar** (código ou corpus novo): `git pull && docker compose up -d --build`
- **Trocar o token:** `umask 077 && echo "TAXLAW_HTTP_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" > .env && docker compose up -d`. O token antigo para de valer na hora.
- **Logs:** `docker compose logs --tail 100`. Eles não contêm o token nem os argumentos das consultas.
- **Desfazer:**
  1. `docker compose down`
  2. com sudo: `sudo rm /etc/nginx/sites-enabled/mcpreforma /etc/nginx/conf.d/mcpreforma-ratelimit.conf && sudo nginx -t && sudo systemctl reload nginx` (o certificado pode ficar).

## Erros comuns

| Sintoma | Causa provável |
|---|---|
| 401 com o token "certo" | o `TAXLAW_HTTP_TOKEN` do Mac não é o do `.env` da VPS (copie de novo); ou o token foi trocado e o container não foi recriado |
| 421 "Invalid Host header" | o domínio usado não é o `TAXLAW_ALLOWED_HOST` (padrão: `mcpreforma.cristianocarvalho.cloud`) |
| 502 do nginx | o container não está de pé: `docker compose ps` e `docker compose logs` |
| 429 | limite de taxa: 10 requisições por segundo por IP, com rajada de 20 |
| `nginx -t` com "zero size shared memory zone" | o site foi instalado sem a zona em `conf.d` |
````

- [ ] **Step 7: rode e veja passar.** `uv run pytest tests/test_deploy.py -q` → 16 passed; `uv run pytest -q` → 478 passed. Não rode `docker compose up` nem crie `.env` no repositório: o build é verificado à mão depois do merge.

- [ ] **Step 8: nota do passo.** Crie `docs/steps/deploy.md`:

````markdown
# Passo extra: deploy do taxlaw na VPS

## O que mudou

- **`Dockerfile`**:
  - `python:3.13-slim` com o `uv` 0.11.18 copiado da imagem oficial;
  - `uv sync --frozen --no-dev` instala só o que o `uv.lock` trava, sem as dependências de desenvolvimento;
  - leva só o necessário: `src/` e o `corpus/dispositivos.json`;
  - usuário sem privilégio (uid 10001);
  - verificação de saúde pela porta, sem requisição MCP.
- **`compose.yaml`**:
  - porta **só em `127.0.0.1:8020`**: a 8000 já é de outro app da VPS;
  - token pelo `.env`;
  - `restart: unless-stopped`;
  - sistema de arquivos só de leitura, nenhuma capacidade de kernel, `no-new-privileges` e teto de memória e CPU.
- **`.dockerignore` e `.env.example`:** o token e o HTML bruto ficam fora da imagem, e o exemplo não tem valor.
- **`deploy/`**: o site do nginx (proxy para `127.0.0.1:8020`, repassando o `Host`, com limite de taxa e corpo de 64 KB) e a zona de limite de taxa, num arquivo separado para `conf.d`.
- **`docs/deploy.md`**: o roteiro (instalar, nginx e certbot com sudo, verificar, operar e desfazer). O token nunca vai para a tela: sai da VPS direto para a área de transferência.
- **`tests/test_deploy.py`**: 16 testes, offline, que prendem as decisões de segurança e a coerência de porta e domínio entre os três arquivos.

## Como rodar

```
uv run pytest tests/test_deploy.py -v
# No Mac, o mesmo container (token de teste num .env local, que não vai para o git):
TAXLAW_ALLOWED_HOST=localhost:8020 docker compose up -d --build
```

Na VPS, siga o `docs/deploy.md`.

## O que observar

- **Verificado no Mac antes da VPS:**
  - o container fica saudável e responde 401 sem token;
  - com token, traz a LC 214, art. 125;
  - recusa `Host` fora da lista;
  - roda como `uid=10001` e não consegue escrever em `/app`;
  - o log não contém o token.
- **O `nginx -t` foi rodado num container `nginx`.** Com os dois arquivos, passa; com o site sozinho, falha com "zero size shared memory zone". Por isso o roteiro instala a zona primeiro.
- **Defesa em camadas.** HTTPS e limite de taxa ficam no nginx. O token, o `Host` e o tamanho ficam no server, e a guarda de CPF/CNPJ nas ferramentas. Cada camada continua valendo se a anterior falhar.
- **O que segue manual:** o nginx e o certbot exigem sudo, que o usuário `agente` não tem sem senha.

## Pergunta de previsão

O container escuta em `0.0.0.0:8000` **dentro** dele, mas o compose publica só em `127.0.0.1:8020`. Se alguém trocar a porta para `"8020:8000"` (sem o `127.0.0.1`), o que muda para quem está na internet? Que camadas ainda protegem, e qual deixa de valer?
````

- [ ] **Step 9: commit.** `git add Dockerfile compose.yaml .dockerignore .env.example deploy/nginx-mcpreforma.conf deploy/nginx-mcpreforma-ratelimit.conf docs/deploy.md tests/test_deploy.py docs/steps/deploy.md && git commit -m "feat(deploy): imagem, compose, nginx e roteiro para a VPS"`. Confira com `git status --short` que nenhum `.env` entrou.

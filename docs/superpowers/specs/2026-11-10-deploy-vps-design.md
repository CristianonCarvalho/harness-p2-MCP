# P2, extra: deploy do taxlaw na VPS (design)

- **Data:** 2026-11-10
- **Status:** design aprovado em conversa (partes 1 e 2); aguardando revisão desta spec escrita.
- **Depende de:** [2026-11-09-transporte-http-design.md](2026-11-09-transporte-http-design.md). O server HTTP com token já existe (`python -m taxlaw.http`). Este passo o publica.

## 1. Objetivo

Publicar o taxlaw em **`https://mcpreforma.cristianocarvalho.cloud/mcp`**, na VPS acessada pelo alias SSH `tradeomqs-vps-agente`, a partir da pasta `~/mcpreforma`. O acesso exige o token. HTTPS, limite de taxa e reinício automático ficam garantidos.

**Sucesso:**
- por HTTPS, com certificado válido, sem token responde 401;
- o cliente com `--url` e o token consulta normalmente;
- uma rajada de requisições recebe 429;
- o container reinicia sozinho;
- nenhum log mostra o token ou argumentos.

## 2. Fatos da VPS (levantados em 2026-11-10, só com leitura)

- Ubuntu 24.04.4 LTS. O usuário `agente` está no grupo `docker`, e **`sudo` exige senha**.
- **nginx do sistema** nas portas 80 e 443. Cada app é um site em `/etc/nginx/sites-available/` (chronoastro, licitai, omniroute, tradeomqs), um subdomínio de `cristianocarvalho.cloud` com `proxy_pass` para `127.0.0.1:<porta>` e certificado do **certbot** ("managed by Certbot"). Nenhum site usa `limit_req`.
- **Portas ocupadas** em 127.0.0.1: 8000 (omqs-binance-trading-app), 6080, 65529. Também 4000 e 5432 (chronoastro).
- Na VPS há `git`, `python3` e `docker`, mas **não** há `uv`. `~/mcpreforma` ainda não existe.
- `mcpreforma.cristianocarvalho.cloud` **já resolve** para 179.198.110.134 (DNS curinga), então não é preciso criar registro.
- O Mac tem Docker 29.6, o que permite testar o container localmente antes.

## 3. Decisões

| Tema | Decisão | Descartado e por quê |
|---|---|---|
| Endereço | `mcpreforma.cristianocarvalho.cloud` (escolha do usuário) | `taxlaw.…`: fugia do nome da pasta |
| Como rodar | Docker Compose em `~/mcpreforma`, com clone do repositório público | uv + systemd do usuário: precisa de `enable-linger` (sudo) e o processo veria o home inteiro do `agente`. Imagem em registry por CI: peças demais para um server |
| Porta | `127.0.0.1:8020` no host, `8000` no container | 8000 no host já está ocupada |
| HTTPS e limite de taxa | No nginx existente, com o certbot, seguindo o padrão da VPS | Um proxy próprio no compose: duplicaria o que a VPS já tem nas portas 80 e 443 |
| Quem configura o nginx | O usuário, com sudo, a partir de um arquivo pronto no repositório | Automatizar com sudo: exigiria guardar a senha ou liberar sudo |
| Token | Gerado **na VPS**, direto no `.env` com permissão 600 | Gerar no Mac e copiar: o valor passaria pela conversa ou pelo terminal |

## 4. Arquivos no repositório

### `Dockerfile`
- Base `python:3.13-slim`, com o `uv` copiado de `ghcr.io/astral-sh/uv` em versão fixa.
- `uv sync --frozen --no-dev` instala exatamente o `uv.lock`, sem as dependências de desenvolvimento.
- Copia `pyproject.toml`, `uv.lock`, `README.md`, `src/` e `corpus/dispositivos.json`. O HTML bruto, os testes e o `.git` ficam fora.
- Usuário sem privilégio (`taxlaw`, uid 10001).
- `CMD`: `python -m taxlaw.http --host 0.0.0.0 --port 8000 --allowed-host ${TAXLAW_ALLOWED_HOST}`. O valor padrão do `ENV` é `mcpreforma.cristianocarvalho.cloud`.
- `HEALTHCHECK` que só testa se a porta 8000 abriu, sem requisição MCP, porque o `/mcp` exige token.

### `compose.yaml`
- Serviço `taxlaw`, com `build: .`.
- `ports: ["127.0.0.1:8020:8000"]`.
- `env_file: .env` (`TAXLAW_HTTP_TOKEN`). O `TAXLAW_ALLOWED_HOST` pode ser sobrescrito; no Mac, usa `localhost:8020`.
- `restart: unless-stopped`.
- **Endurecimento:** `read_only: true`, `tmpfs: /tmp`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `mem_limit: 512m`, `cpus: "1.0"`.

### `.dockerignore`
`.git`, `.venv`, `.env`, `tests/`, `corpus/raw/`, `docs/`, `traces/`, `runs/`, `__pycache__/`, `.meister/`, `.claude/`, `.kiro/`.

### `.env.example`
`TAXLAW_HTTP_TOKEN=` sem valor, com um comentário de como gerar o token.

### `deploy/nginx-mcpreforma.conf`
- Uma zona de limite de taxa (`limit_req_zone $binary_remote_addr zone=mcpreforma:10m rate=10r/s`). Vai para `conf.d`, num arquivo separado, `deploy/nginx-mcpreforma-ratelimit.conf`, porque `limit_req_zone` só vale no bloco `http`.
- `server`:
  - `listen 80` e `[::]:80`, `server_name mcpreforma.cristianocarvalho.cloud`;
  - `location /`:
    - `limit_req zone=mcpreforma burst=20 nodelay`, `limit_req_status 429`;
    - `client_max_body_size 64k`;
    - `proxy_pass http://127.0.0.1:8020`;
    - `proxy_set_header Host $host`, mais `X-Forwarded-For` e `X-Forwarded-Proto`;
    - `proxy_read_timeout 60s`.
- Nenhum `log_format` com `$http_authorization`.
- O HTTPS entra pelo `certbot --nginx`, que edita o arquivo, como nos outros sites.

### `docs/deploy.md`
O roteiro, separando os comandos do `agente` dos que exigem sudo: primeira instalação, verificação, atualização, troca do token, logs e como desfazer. Inclui a entrada pessoal do Claude Code para o server remoto.

## 5. Sequência

| # | Quem | O quê |
|---|---|---|
| 1 | Meister | os arquivos da seção 4 e `tests/test_deploy.py` |
| 2 | Claude, no Mac | `TAXLAW_ALLOWED_HOST=localhost:8020 docker compose up -d --build` com um token de teste; o cliente com `--url http://localhost:8020/mcp` funciona; sem token, 401; depois, `docker compose down` |
| 3 | Claude, por SSH como `agente`, com o ok do usuário antes | `git clone https://github.com/CristianonCarvalho/harness-p2-MCP.git ~/mcpreforma`; `umask 077` e o token gerado na VPS direto no `.env`; `docker compose up -d --build`; o container fica saudável; `curl` local em `127.0.0.1:8020` sem token responde 401 |
| 4 | o usuário, com sudo | instalar os dois arquivos do nginx; `sudo nginx -t && sudo systemctl reload nginx`; `sudo certbot --nginx -d mcpreforma.cristianocarvalho.cloud` |
| 5 | Claude, do Mac | a verificação de fora (seção 6) |
| 6 | o usuário | ler o token na VPS e configurar o próprio Claude Code (entrada `"type": "http"`) |

## 6. Verificação de ponta a ponta

- `https://mcpreforma.cristianocarvalho.cloud/mcp` sem token responde 401, com certificado válido; `http://` redireciona para HTTPS.
- O cliente com `--url https://mcpreforma.cristianocarvalho.cloud/mcp` faz `buscar` e `obter`. O token fica numa variável exportada pelo usuário no próprio terminal.
- Uma rajada de 40 requisições sem token recebe 429 em parte delas.
- Na VPS, `docker compose logs` não contém o token nem argumentos de consulta.
- `docker compose restart` volta a responder sem intervenção.

## 7. Testes (`tests/test_deploy.py`)

Offline e só de leitura dos arquivos (sem daemon Docker, sem rede, sem pyyaml para o Dockerfile). Prendem as decisões de segurança:

- **`compose.yaml`** (lido com pyyaml):
  - porta `127.0.0.1:8020:8000`;
  - `env_file` com `.env`;
  - `read_only` verdadeiro, `cap_drop` com `ALL`, `no-new-privileges:true`;
  - `restart: unless-stopped`.
- **`Dockerfile`:**
  - `USER` diferente de root;
  - `uv sync --frozen --no-dev`;
  - `python -m taxlaw.http` com `--allowed-host`;
  - nenhum `COPY . .` e nenhuma cópia de `corpus/raw`.
- **`.dockerignore`:** inclui `.env`, `.git`, `tests/` e `corpus/raw/`.
- **Segredos:**
  - `.env` está no `.gitignore`;
  - `.env.example` tem `TAXLAW_HTTP_TOKEN=` sem valor;
  - nenhum arquivo de `deploy/` contém um token.
- **nginx:**
  - `server_name mcpreforma.cristianocarvalho.cloud`, `proxy_pass http://127.0.0.1:8020`, `proxy_set_header Host $host`;
  - `limit_req zone=mcpreforma`, com a zona definida no arquivo de `conf.d`;
  - `client_max_body_size 64k`;
  - nenhum `$http_authorization`.
- **Coerência:** a porta do nginx é a mesma do compose, e o domínio do nginx é o padrão do `Dockerfile`.

## 8. Operação

- **Atualizar:** `cd ~/mcpreforma && git pull && docker compose up -d --build`. Um corpus novo exige rebuild.
- **Trocar o token:** editar o `.env` e rodar `docker compose up -d`.
- **Logs:** `docker compose logs --tail 100`.
- **Desfazer:** `docker compose down`; remover o site e a zona do nginx; `sudo nginx -t && sudo systemctl reload nginx`. O certificado pode ficar.

## 9. Fora do escopo

CI que publica imagem, monitoramento e alertas, backup (o corpus está no git), OAuth, vários tokens e clientes de navegador.

## 10. Passo

Um passo extra, com tag `step-deploy` e nota em `docs/steps/deploy.md`. Os passos 3 a 6 da seção 5 acontecem depois do merge e ficam registrados na nota.

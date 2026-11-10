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

## Verificação na VPS (2026-11-10)

Publicado em **`https://mcpreforma.cristianocarvalho.cloud/mcp`**.

- **Container (como `agente`, sem sudo):**
  - clone em `~/mcpreforma` no commit `394d181`;
  - `.env` gerado na VPS com permissão 600, sem que o valor fosse exibido;
  - `docker compose up -d --build` deixou o container `healthy`, publicado só em `127.0.0.1:8020`, sem nada em `0.0.0.0:8020`;
  - `curl` local sem token respondeu 401;
  - o token aparece 0 vezes nos logs;
  - os outros containers (omqs, chronoastro, mt4) continuaram de pé.
- **nginx e certbot (feitos por Claude como root, pelo alias SSH `tradeomqs-vps`, a pedido do usuário):**
  - a zona foi para `conf.d` e o site para `sites-available`, com o link em `sites-enabled`;
  - `nginx -t` passou, e só então veio o reload;
  - `certbot --nginx --non-interactive --redirect` usou a conta já existente na VPS. O certificado vale até 2027-02-08, com renovação automática.
- **De fora, do Mac:**
  - HTTPS sem token responde 401, com certificado válido;
  - `http://` responde 301 para `https://`;
  - o cliente com `--url` e o token (lido da VPS sem aparecer na tela) trouxe a busca "cesta básica";
  - 60 requisições em paralelo deram 24 respostas 401 e **36 respostas 429** (limite de taxa).
- **Achados fora do taxlaw, que já existiam antes do deploy:**
  - `licitai` e `omniroute` respondem 502, porque os serviços deles não escutam nas portas 3000 e 20128. O log do nginx tem os mesmos erros desde antes da mudança;
  - `chronoastro.cristianocarvalho.cloud` não resolve no DNS.

  Não foram mexidos.

## Pergunta de previsão

O container escuta em `0.0.0.0:8000` **dentro** dele, mas o compose publica só em `127.0.0.1:8020`. Se alguém trocar a porta para `"8020:8000"` (sem o `127.0.0.1`), o que muda para quem está na internet? Que camadas ainda protegem, e qual deixa de valer?

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

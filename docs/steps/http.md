# Passo extra: o taxlaw via Streamable HTTP, com token

## O que mudou

- **`src/taxlaw/http.py`** (novo) deixa o **mesmo** server (`build_server()`: mesma guarda, mesmas ferramentas, mesmo corpus) atrás de uma porta HTTP.
  - **Stateless**, com resposta JSON simples.
  - **Sempre com token:** sem `Authorization: Bearer <token>` exato, a resposta é **401** antes de chegar ao MCP, em qualquer caminho.
  - **O token vem só de `TAXLAW_HTTP_TOKEN`** e precisa ter pelo menos 32 caracteres. Sem ele, o server não sobe.
  - **Escuta em `127.0.0.1` por padrão.**
  - **`Host` só da lista** (`--allowed-host`); um `Host` estranho recebe **421**. Navegadores, que mandam `Origin`, são recusados.
  - **Corpo de no máximo 64 KB**; acima disso, 413.
  - **Log de acesso desligado.**
- **O 401 vem como erro JSON-RPC** (`nao_autorizado`, código -32001). Com isso, o cliente do SDK repassa o motivo, em vez de um "Server returned an error response" genérico.
- **`client/taxlaw_client.py`** ganha `--url`, com o token de `TAXLAW_HTTP_TOKEN`. Ele reconhece o 401 pelo código HTTP e responde "token recusado pelo server", com código de saída 2. `--url` e `--server` juntos são erro de uso.
- O `server.py` (stdio) não muda. O Claude Code e o Kiro continuam por stdio.

## Como rodar

```
export TAXLAW_HTTP_TOKEN=$(uv run python -c "import secrets; print(secrets.token_urlsafe(32))")
uv run python -m taxlaw.http --port 8000 &
uv run python client/taxlaw_client.py --url http://127.0.0.1:8000/mcp buscar "cesta básica"
curl -s -X POST http://127.0.0.1:8000/mcp -d '{}'     # 401, sem token
uv run pytest tests/test_http.py -v
```

No Claude Code, a configuração **pessoal** para um server remoto (nunca no `.mcp.json` do repositório, por causa do token) seria assim:

```json
{"mcpServers": {"taxlaw-remoto": {"type": "http", "url": "https://SEU-DOMINIO/mcp", "headers": {"Authorization": "Bearer ${TAXLAW_HTTP_TOKEN}"}}}}
```

## O que observar

- **O protocolo é o mesmo; só o transporte muda.** O mesmo `tools/list` e o mesmo `tools/call`, agora num `POST /mcp`, sem processo filho. O `--json` pela rede é idêntico ao `tools.py`.
- **A guarda do server vira a principal.** Um cliente remoto não tem o hook do Claude Code. Um CPF numa consulta HTTP é barrado pelo `TaxLawServer.call_tool`, e o número não aparece em nenhuma saída.
- **Três camadas de recusa, cada uma com o seu código:**
  - 401: quem é você? (o token);
  - 421: para quem é esta requisição? (o `Host`);
  - 413: tamanho.

  Só depois de passar por elas a requisição chega ao MCP.
- **O que falta para publicar** (o passo do deploy): HTTPS, limite de taxa, proxy reverso, o server rodando como serviço na VPS e o `--allowed-host` com o domínio.

## Pergunta de previsão

Na VPS, o server vai escutar em `127.0.0.1:8000`, atrás de um proxy com HTTPS. O proxy repassa a requisição com o `Host` do domínio. O que acontece se você esquecer o `--allowed-host SEU-DOMINIO`: o token ainda protege, mas qual resposta o cliente recebe, e por quê?

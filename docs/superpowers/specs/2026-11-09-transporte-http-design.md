# P2, extra: transporte Streamable HTTP para o taxlaw (design)

- **Data:** 2026-11-09
- **Status:** design aprovado em conversa (partes 1 e 2); aguardando revisão desta spec escrita.
- **Spec principal:** [2026-11-05-mcp-reforma-tributaria-design.md](2026-11-05-mcp-reforma-tributaria-design.md). O stdio continua sendo o transporte do Claude Code e do Kiro. Este passo **acrescenta** o HTTP, sem substituí-lo.

## 1. Objetivo

Permitir que um cliente MCP em **outra máquina** use o taxlaw, como primeira etapa de uma publicação futura numa VPS. Esta etapa deixa o server pronto para HTTP e testado localmente. O deploy (proxy, HTTPS, limite de taxa, serviço) é um passo seguinte.

**Sucesso:**
- o mesmo server (`build_server()`, a mesma guarda, as mesmas ferramentas, o mesmo corpus) responde via Streamable HTTP **stateless**;
- **só com o token:** toda requisição sem `Authorization: Bearer <token>` válido recebe 401 antes de chegar ao MCP;
- o server não sobe sem um token configurado;
- o cliente de terminal consulta por URL;
- nenhum log ou mensagem contém o token, CPF ou CNPJ.

## 2. Decisões

| Tema | Decisão | Descartado e por quê |
|---|---|---|
| Quem acessa | Só quem tiver o token (decisão do usuário) | Aberto com limite de taxa: não bloqueia um abusador específico. Configurável: abre um caminho para publicar aberto por engano |
| Onde fica a checagem do token | Um middleware próprio em volta do app HTTP do SDK | O caminho OAuth do SDK só com o verificador: exige `issuer_url` e expõe metadados OAuth para um token que não é OAuth. Só no proxy: o server ficaria aberto se exposto sem o proxy, e os testes não provariam a proteção |
| Estado | `stateless_http=True` e `json_response=True` | Com sessão: guarda estado sem necessidade. A revisão 2026-07-28 já é stateless |
| Origem do token | Só a variável de ambiente `TAXLAW_HTTP_TOKEN`, no server e no cliente | Argumento de linha de comando: aparece no `ps` e no histórico do shell |
| OAuth | Fora, por agora | Só se justifica para cadastro aberto ou conector público. Entra depois, substituindo o middleware, sem mudar o resto |

## 3. Componentes

### Server: `src/taxlaw/http.py` (novo; `server.py` não muda)

- **`BearerTokenMiddleware(app, token: str)`:** um middleware ASGI.
  - Para requisições HTTP, lê o cabeçalho `authorization` e só aceita `Bearer <token>`, comparado com `hmac.compare_digest`.
  - Se falhar, responde **401** com `WWW-Authenticate: Bearer` e, como corpo, um erro JSON-RPC: `{"jsonrpc": "2.0", "id": null, "error": {"code": -32001, "message": "nao_autorizado"}}`, sem repetir o que veio. *(Ajuste do protótipo: o cliente do SDK repassa um erro JSON-RPC recebido com status de erro, em vez de um genérico "Server returned an error response", então qualquer cliente MCP entende a recusa.)*
  - Escopos que não são HTTP (`lifespan`) passam direto.
- **`build_http_app(server, *, token: str, allowed_hosts: list[str]) -> ASGI app`:**
  - `server.streamable_http_app(stateless_http=True, json_response=True, max_request_body_size=65536, transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=allowed_hosts, allowed_origins=[]))`;
  - tudo embrulhado no `BearerTokenMiddleware`.
- **`main(argv=None) -> int`**, executado como `python -m taxlaw.http`:
  - `--host`: padrão `127.0.0.1`;
  - `--port`: padrão `8000`;
  - `--allowed-host`: repetível, com padrão `127.0.0.1:<porta>` e `localhost:<porta>`;
  - lê `TAXLAW_HTTP_TOKEN`. Se ela estiver ausente ou tiver menos de 32 caracteres, imprime um erro **sem o valor** e sai com 2;
  - roda o `uvicorn` com `access_log=False`, montando o app com `build_http_app(build_server(), …)`.
- **Constantes:** `TOKEN_ENV = "TAXLAW_HTTP_TOKEN"`, `MIN_TOKEN_LENGTH = 32`, `MAX_BODY_BYTES = 65536`, `MCP_PATH = "/mcp"`.

### Cliente: `client/taxlaw_client.py`

- **`--url URL`:** alternativa ao `--server` e ao `.mcp.json`. Os dois juntos são erro de uso.
- **Com `--url`:**
  - o token vem de `TAXLAW_HTTP_TOKEN`; sem ele, o cliente sai com 2 antes de conectar;
  - a conexão é `Client(streamable_http_client(url, http_client=httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"})))`.
- **Mensagens de erro (código 2), sem o token:**
  - 401 vira "token recusado pelo server". O cliente reconhece o 401 pelo código HTTP de cada resposta (um "event hook" do httpx), não pelo corpo, então funciona mesmo quando quem responde é o proxy;
  - uma conexão recusada vira "não consegui falar com o server".
- Continua sem importar `taxlaw`.

### Configuração de exemplo (só na nota do passo, nunca no `.mcp.json` do repositório)

```json
{"mcpServers": {"taxlaw-remoto": {"type": "http", "url": "https://SEU-DOMINIO/mcp", "headers": {"Authorization": "Bearer ${TAXLAW_HTTP_TOKEN}"}}}}
```

## 4. Segurança

| Ponto | Regra |
|---|---|
| Token | Esquema `Bearer`, comparação em tempo constante. Mínimo de 32 caracteres; a nota ensina `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| Escuta | Padrão `127.0.0.1`. Na VPS, continua assim, atrás do proxy (passo seguinte) |
| Logs | Log de acesso desligado. Nenhum log de cabeçalhos nem de argumentos. As mensagens de erro do taxlaw já vêm sem CPF/CNPJ |
| Tamanho | Corpo de no máximo 64 KB; acima disso, 413 |
| Host e origem | Proteção contra DNS rebinding ligada, com `allowed_hosts` explícitos e nenhuma origem permitida (navegadores são recusados) |
| CPF/CNPJ | A guarda do `TaxLawServer.call_tool` vale igual. Para um cliente remoto sem hook, é a camada que protege |

## 5. Erros

| Situação | Resultado |
|---|---|
| Server sem token, ou com token curto | Não sobe; código 2; mensagem sem o valor |
| Requisição sem token, com token errado ou com outro esquema | 401, com o erro JSON-RPC `nao_autorizado` (código -32001) |
| `Host` fora da lista | 421 "Invalid Host header", da proteção do SDK (medido no protótipo) |
| Corpo acima de 64 KB | 413 |
| Erro de ferramenta | Igual ao stdio: `isError` com `{"erro", "mensagem"}` |
| Cliente: 401, server fora do ar ou token ausente | Código 2, sem o token na mensagem |

## 6. Testes (`tests/test_http.py`)

Os testes sobem o server HTTP real num subprocesso (`python -m taxlaw.http`), numa porta livre, com um token de teste gerado na hora (`secrets.token_urlsafe(32)`), e esperam a porta abrir. Todos são offline, locais e independentes do diretório.

- **Funcionamento:**
  - o cliente com `--url` faz `ferramentas`, `buscar` e `obter`;
  - o `--json` de `obter` é igual ao `tools.obter_dispositivo`;
  - a revisão negociada é a 2026-07-28;
  - duas chamadas seguidas funcionam.
- **Token:**
  - um `POST` cru sem `Authorization`, com token errado e com `Basic …` dá 401;
  - o corpo da resposta não contém o token;
  - o cliente sem a variável, ou com token errado, sai com 2 e uma mensagem sem o token.
- **Proteções:**
  - um `Host` fora da lista é recusado;
  - um corpo acima de 64 KB dá 413.
- **CPF pela rede:** um CPF sintético na consulta dá `dados_de_contribuinte`, sem o número na saída.
- **Partida:** num subprocesso com tempo máximo, para que uma regressão falhe em vez de pendurar a suíte:
  - sem `TAXLAW_HTTP_TOKEN`, sai com 2;
  - com token curto, sai com 2, e a mensagem não contém o valor.
- **Unidade:** o `BearerTokenMiddleware` com um app ASGI falso aceita o token certo, recusa os demais e deixa o `lifespan` passar.
- **O cliente sem dataclass:** `HttpTarget` é uma classe simples, porque o teste carrega o cliente pelo caminho do arquivo, sem registrá-lo em `sys.modules`, e `@dataclass` precisa do módulo registrado.

## 7. Fora do escopo (passo seguinte: deploy)

HTTPS, limite de taxa, proxy reverso (Caddy ou nginx), systemd ou Docker na VPS, vários tokens ou rotação sem reiniciar, OAuth e clientes de navegador (CORS).

## 8. Passo

Um passo extra, com tag `step-http` e nota em `docs/steps/http.md`. Ele não depende de nada pendente: o server, as ferramentas e o cliente já existem.

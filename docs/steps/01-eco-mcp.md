# Passo 01: eco MCP feito à mão

## O que mudou

- `echo/echo_server.py`: server MCP sem SDK, só biblioteca padrão, com a ferramenta `eco`. Atende a era moderna do protocolo (2026-07-28: `server/discover`, versão em `params._meta`) e a legada (`initialize`).
- Cada mensagem que entra e sai é gravada em `traces/echo.jsonl` (ignorado pelo git).
- `.mcp.json` registra o server `eco` para o Claude Code neste projeto.
- Testes de `handle_message` (sem processo) e um teste que roda o script via stdio.

## Como rodar

    uv run pytest tests/test_echo_server.py -v

Para ver o protocolo de verdade:

1. Saia e abra de novo o Claude Code na raiz do projeto. Ele pergunta se aprova o server `eco` do `.mcp.json`: aprove.
2. Rode `/mcp` e confira que `eco` aparece conectado.
3. Peça: "use a ferramenta eco com o texto olá".
4. Em outro terminal: `jq -c '[.direcao, .mensagem.method // .mensagem.id]' traces/echo.jsonl` para ver a sequência, e `jq . traces/echo.jsonl | less` para ver tudo.

Também dá para conversar com o server à mão, sem Claude Code:

    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | uv run python echo/echo_server.py

## O que observar

- **Qual era o Claude Code usou:** a primeira mensagem do log é `server/discover` ou `initialize`? Se for `server/discover`, veja se as requisições seguintes trazem `_meta` com a versão.
- **stdout é sagrado:** um `print()` de depuração no server quebraria o protocolo. É por isso que o log vai para arquivo.
- **Notificações não têm resposta:** mensagens sem `id` aparecem como "entrada" sem "saida" correspondente.
- **Dois tipos de erro:** ferramenta desconhecida é erro JSON-RPC (o cliente errou o pedido); argumento ruim é `isError: true` no resultado (a ferramenta falhou e o modelo pode ler e corrigir). O server do passo 10 usa essa mesma distinção.
- **A descrição da ferramenta é contexto:** o texto de `description` e `inputSchema` é o que o modelo recebe sobre o `eco`. Repare no `tools/list` do log.

## Pergunta de previsão

Antes de abrir o log: quantas mensagens você espera entre o Claude Code iniciar o server e o `tools/call` do eco? E o modelo vai mandar `texto` exatamente "olá", ou pode mudar algo?

## O que observamos (2026-11-05, Claude Code 2.1.318)

**Resposta à pendência da spec (linha 48):** o Claude Code fala a revisão stateless **2026-07-28**. Não houve `initialize` nem `notifications/initialized`.

Sequência no `traces/echo.jsonl`:

    ["entrada","server/discover"]   ← id "server-discover-probe-1" (string)
    ["saida","server-discover-probe-1"]
    ["entrada","tools/list"]        ← id 0, logo ao conectar, antes de qualquer pedido
    ["saida",0]
    ["entrada","tools/call"]        ← eco "Olá!"
    ["saida",1]
    ["entrada","tools/call"]        ← eco "Tudo bem?\ncom voce?"
    ["saida",2]

- **Versão em toda requisição:** cada `params._meta` traz `io.modelcontextprotocol/protocolVersion: "2026-07-28"`, `clientInfo` e `clientCapabilities` (roots, elicitation, extensão `tasks`). Não existe sessão: cada mensagem se explica sozinha.
- **`tools/call` traz extras do cliente em `_meta`:** `progressToken` e `claudecode/toolUseId`, que liga a chamada MCP ao `tool_use` do modelo. Útil para cruzar traces no P3.
- **A resposta ao `server/discover`** tem `supportedVersions`, `capabilities`, `resultType` e `_meta`.
- **O cliente guarda a lista em cache:** a segunda chamada não repetiu `server/discover` nem `tools/list`. Só entraram `tools/call` e a resposta com id `2`.
- **Quebra de linha no texto não quebra o stdio:** o `\n` vai escapado dentro da string JSON, e a mensagem continua ocupando uma linha.
- **Nome da ferramenta no cliente:** o server expõe `eco`, e o Claude Code a mostra ao modelo como `mcp__eco__eco` (`mcp__<server>__<ferramenta>`).

**Quem inicia o server:** o Claude Code, como processo filho (`claude` → `uv run ...` → `python echo/echo_server.py`), com stdin, stdout e stderr ligados por sockets unix anônimos. Nenhuma porta TCP é aberta.

**Experimento: matar o server.** Previsão: "o Claude Code inicia o server de novo sozinho". Resultado: **não inicia.** Com `kill` no Python, o `uv` saiu junto, o server ficou desconectado e a ferramenta sumiu da lista do modelo (nem chega a falhar, deixa de existir). Só voltou com `/mcp` → reconnect.

- Depois do reconnect, o log recebeu as linhas novas no final do arquivo, sem sobrescrever: `server/discover` de novo e `tools/list` com os ids **recomeçando do 0**. O contador é por conexão.
- **Lição para o P3:** uma suíte que use o server via stdio precisa detectar a queda e reiniciar o processo. Senão, um crash vira uma cascata de falhas que parecem erro de conteúdo.

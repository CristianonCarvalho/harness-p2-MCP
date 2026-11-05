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

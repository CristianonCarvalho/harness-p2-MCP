# Passo extra: cliente MCP de terminal para o taxlaw

## O que mudou

- **`client/taxlaw_client.py`:** uma ferramenta de terminal que é cliente MCP de verdade. Ela sobe o server como processo filho (stdio) com o `Client` do SDK oficial, faz **uma** chamada e sai.
  - `ferramentas`: lista as ferramentas e os parâmetros.
  - `buscar CONSULTA [--data] [--limite]`
  - `obter ID [--data] [--sem-filhos]`
  - `--json`: imprime o `structuredContent` cru.
  - `--server "cmd args"`: troca o comando do server.
- **Acha o server pelo `.mcp.json`:** a mesma entrada `taxlaw` que o Claude Code usa (e o Kiro, pelo `.kiro/settings/mcp.json`). O `cwd` é a pasta do `.mcp.json`, então o cliente funciona de qualquer diretório.
- **Desacoplado, como o `echo/`:** não importa o pacote `taxlaw`, só a biblioteca padrão e o `mcp`, e um teste confere os imports. Os nomes de ferramentas e campos são os do contrato público do server.
- **Códigos de saída:** 0 para sucesso, **inclusive "não encontrado"**; 1 para erro devolvido pelo server (`isError`); 2 para erro do cliente (uso, configuração, server que não sobe).
- **Os logs do server** (stderr do processo filho) vão para `/dev/null`, para o stderr do cliente ter só as mensagens dele.

## Como rodar

```
uv run python client/taxlaw_client.py ferramentas
uv run python client/taxlaw_client.py buscar "zona franca de manaus" --limite 2
uv run python client/taxlaw_client.py obter CF.art156-A.par1.incIX --data 2030-06-01
uv run python client/taxlaw_client.py --json obter CF.art155.par3 --data 2033-01-01 --sem-filhos
uv run pytest tests/test_taxlaw_client.py -v
```

## O que observar

- **Três clientes, um server.** O Claude Code (revisão 2026-07-28, sem sessão), o Kiro (`initialize`, 2025-11-25) e este cliente sobem o mesmo comando do `.mcp.json`. O SDK do cliente negocia a versão sozinho.
- **A guarda sem hook.** Fora do Claude Code não existe hook. Um CPF numa consulta deste cliente é bloqueado pelo **server** (camada 2): o cliente sai com código 1, a mensagem é `dados_de_contribuinte`, e o número não aparece em nenhuma saída.
- **"Não encontrado" sai com código 0.** Num script, o código de saída separa "a consulta funcionou e a resposta é 'nada'" de "algo deu errado". É a mesma regra do server (`isError: false`).
- **Os padrões são do server.** O cliente só envia as opções que você deu. Se o server mudar o `limite` padrão, o cliente segue a mudança sem alteração.
- **O tempo de cada chamada** inclui subir o server e montar o índice: cerca de 1 s com `--server` e um pouco mais com o `uv run` do `.mcp.json`. É o custo de não manter o server vivo entre as consultas, uma decisão da spec.

## Pergunta de previsão

Um script do P3 vai rodar 100 perguntas com este cliente, uma por processo. Onde está o custo maior: na busca, no `obter`, ou em subir o server 100 vezes? Que mudança, e em qual camada, resolveria isso sem perder o desacoplamento?

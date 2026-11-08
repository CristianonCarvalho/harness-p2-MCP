# Passo 10: o server MCP via stdio

## O que mudou

- **Dependência nova:** `mcp>=2,<3`, o SDK oficial em Python. A versão travada no `uv.lock` é a 2.3.0.
- **`src/taxlaw/server.py`:** uma camada fina sobre `tools.py`.
  - `build_server(ctx, today)` monta um `TaxLawServer`, uma subclasse de `MCPServer`, com as duas ferramentas.
  - Ambas são marcadas como só leitura.
  - `main()` roda o server via stdio.
- **`.mcp.json`:** registra o server `taxlaw` ao lado do `eco`. O Claude Code expõe as ferramentas como `mcp__taxlaw__buscar_dispositivos` e `mcp__taxlaw__obter_dispositivo`.
- **Três coisas do SDK 2.3 que o código contorna** (medidas no protótipo em 2026-11-08):
  1. **O erro de validação repete o valor recebido.** O SDK valida os argumentos com o pydantic antes de chamar a ferramenta, e o erro traz `input_value=...`. Um CPF mandado no campo `limite` voltaria inteiro. Por isso `TaxLawServer.call_tool` varre todos os argumentos crus antes do SDK, incluindo chaves, valores aninhados e campos desconhecidos. Depois reescreve o erro de validação só com o nome do campo.
  2. **O que não está no tipo de retorno some em silêncio.** O SDK descarta do `structuredContent` toda chave que não está no `TypedDict`, mas o texto continua com ela. Por isso cada campo de `tools.py` está declarado, e um teste compara os dois.
  3. **O pydantic aceita `True` e `"5"` como inteiros.** `limite` e `incluir_filhos` são `strict`, para o server rejeitar o mesmo que `tools.py` rejeita.
- **Erros:** todo `isError` tem como texto só um JSON `{"erro", "mensagem"}`. O prefixo "Error executing tool" do SDK é removido.

## Como rodar

```
uv run pytest tests/test_server.py tests/test_server_stdio.py -v
```

No Claude Code, a primeira consulta real:

1. Rode `/mcp` e reconecte. O `taxlaw` deve aparecer com 2 ferramentas.
2. Pergunte: "Pela EC 132, o IBS integra a própria base de cálculo em 2030? Cite o dispositivo."
3. Confira se o modelo chamou `mcp__taxlaw__buscar_dispositivos` e depois `mcp__taxlaw__obter_dispositivo` com `data_referencia` 2030, e se a resposta cita `CF, art. 156-A, § 1º, IX` na redação do art. 3º da EC.

## O que observar

- **O mesmo resultado nos dois caminhos.** Chamar `tools.py` direto e chamar via MCP dá o mesmo resultado, no `structuredContent` e no texto. O teste de stdio sobe o processo de verdade, a partir de outro diretório, e fala a revisão `2026-07-28`.
- **O ponto único por onde todas as ações passam** (lição do P1). A guarda agora existe em duas camadas do server: em `call_tool`, antes do SDK, e em `tools.py`, para chamadas diretas. O hook do passo 11 será a terceira, no cliente.
- **"Não encontrei" volta com `isError: false`.** O modelo recebe a ausência como dado, e não como falha.

## Pergunta de previsão

Sem `/mcp` reconectado, o Claude Code ainda vê o server? E depois de reconectar: se você mudar o `dispositivos.json` e não reiniciar o server, a resposta muda? Pense em quando o `load_context()` roda.

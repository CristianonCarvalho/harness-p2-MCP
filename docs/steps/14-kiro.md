# Passo 14: o mesmo server no Kiro (critério 1)

## O que mudou

Nenhuma linha de código Python mudou. Só entraram arquivos de configuração do Kiro, que apontam para o que já existia:

- **`.kiro/settings/mcp.json`:** registra o server `taxlaw` com o mesmo comando do `.mcp.json` (`uv run --quiet python -m taxlaw.server`). Um teste garante que os dois não divergem.
- **`.kiro/hooks/block-taxpayer-ids.json`:** dois hooks `PreToolUse` (matchers `@taxlaw` e `web`) que chamam o **mesmo** `hooks/block_taxpayer_ids.py` do passo 11. O stdin do Kiro tem os mesmos campos `tool_name` e `tool_input`, e no Kiro qualquer código diferente de 0 bloqueia. O nosso script sai com 2, então serve como está.
- **`.kiro/skills/consultar-reforma-tributaria`:** um link simbólico relativo para `.claude/skills/consultar-reforma-tributaria`. O Kiro CLI lê `SKILL.md` no mesmo padrão, então a skill é um arquivo só para os dois clientes.
- **`tests/test_kiro.py`:**
  - o server responde ao handshake `initialize`;
  - as configurações do Kiro batem com as do Claude Code;
  - o hook bloqueia com o `tool_name` no formato do Kiro (`mcp_taxlaw_*`);
  - o link da skill é relativo.

## Como rodar

```
uv run pytest tests/test_kiro.py -v
kiro-cli mcp list
```

No Kiro CLI, dentro do projeto:

1. `kiro-cli chat`. Na primeira vez, confie no workspace: sem isso, o Kiro não carrega hooks, MCP e skills do projeto.
2. Rode `/mcp` e confira se `taxlaw` aparece com 2 ferramentas.
3. Pergunte "qual o percentual do IBS?". Confira se a skill entra, e se a busca usa "imposto sobre bens e serviços" com a data.
4. Gere um CPF sintético (`uv run python -c "from taxlaw.synthetic_ids import make_cpf; print(make_cpf('987654321', formatted=True))"`) e peça uma consulta ao `taxlaw` com ele. O hook deve bloquear antes de a chamada chegar ao server.

## O que observar

**Medido em 2026-11-09** com Kiro CLI 3.1.0, numa consulta não interativa e com um registrador stdio que gravava só método, id e versão:

| | Claude Code (passo 01) | Kiro CLI 3.1.0 |
|---|---|---|
| Abertura | `server/discover`, sem sessão, revisão 2026-07-28 | `initialize` + `notifications/initialized`, revisão 2025-11-25 |
| Descoberta | `tools/list` | `tools/list` e `prompts/list` |
| Chamada | `tools/call` | `tools/call`; a resposta tem `content`, `isError` e `structuredContent` |
| Nome mostrado | `mcp__taxlaw__obter_dispositivo` | `@taxlaw/obter_dispositivo` (id interno `mcp_taxlaw_obter_dispositivo`) |

- **O mesmo server atendeu às duas gerações do protocolo sem nenhuma mudança.** O SDK negocia a versão: com o Claude Code, sem sessão; com o Kiro, com o handshake. É o que a spec previu na seção 1: nada específico de um cliente.
- **Por que funcionou sem esforço:**
  - o transporte é stdio;
  - as ferramentas são padrão do MCP;
  - o retorno é só dado, sem depender de recurso de nenhum cliente;
  - a guarda tem um ponto único, `guard.py`.

  A portabilidade foi uma decisão de projeto tomada no passo 00, e não um trabalho do passo 14.
- **O que muda entre os clientes:** o formato da configuração de hooks (`.claude/settings.json` com regex × `.kiro/hooks/*.json` com seletores) e a regra de código de saída (só 2 bloqueia × qualquer código diferente de 0 bloqueia). Como o script sai com 2, ele satisfaz as duas regras.

## Pergunta de previsão

O Kiro abriu com `initialize`, que cria uma sessão. O nosso server guarda algum estado por sessão? Se o Kiro reconectar no meio de uma conversa, a resposta de `obter_dispositivo` para o mesmo id e a mesma data pode mudar?

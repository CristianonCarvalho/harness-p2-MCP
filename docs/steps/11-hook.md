# Passo 11: o hook que bloqueia CPF/CNPJ (critério 2)

## O que mudou

- **`.claude/settings.json`** (novo, versionado) registra um hook `PreToolUse`.
  - O matcher `^(mcp__taxlaw__.*|WebSearch|WebFetch)$` usa âncoras porque o Claude Code testa o matcher como regex sem âncora. Sem elas, `WebSearch` casaria dentro de outros nomes.
  - O comando é `uv run --quiet --project "$CLAUDE_PROJECT_DIR" python "$CLAUDE_PROJECT_DIR/hooks/block_taxpayer_ids.py"`, com timeout de 30 s.
- **`hooks/block_taxpayer_ids.py`** é o ponto de entrada. A lógica está em `src/taxlaw/hook.py`, testável como função.
  - Ele lê a chamada do stdin e varre todos os textos de `tool_input`, inclusive chaves e valores aninhados.
  - Se achar CPF ou CNPJ, escreve o motivo no stderr (tipo e campo, sem o número) e sai com **2**.
- **Bloqueia na dúvida (fail closed).** Pela documentação, só o código 2 bloqueia: qualquer outro deixa a chamada passar. Por isso JSON ilegível, `tool_input` ausente, erro interno ou pacote não instalado também saem com 2.
- **`guard.find_in_arguments`.** A varredura de argumentos saiu do `server.py` e foi para a `guard.py`. O hook e o server usam a mesma função (spec, seção 4: "as duas guardas não divergem").
- **Correção na guarda.** Um CPF ou CNPJ logo depois de uma `/` de URL (`https://exemplo.invalid/<cnpj>`) ou de um hífen com letra (`cpf-<número>`) não era achado. As fronteiras da regex tratavam `/`, `.` e `-` como continuação do número mesmo com letra do outro lado. Agora a `/` separa campos, e só um **dígito** do outro lado de `.` ou `-` barra o candidato. Foi achado no protótipo deste passo, ao testar um `WebFetch` sintético.

## Como rodar

```
uv run pytest tests/test_hook.py tests/test_guard.py -v
echo '{"tool_name":"WebSearch","tool_input":{"query":"reforma tributária"}}' | uv run python hooks/block_taxpayer_ids.py; echo "código $?"
```

No Claude Code (o hook entra sozinho quando o `settings.json` muda; se não entrar, reinicie a sessão):

1. Em `/hooks`, confira que `PreToolUse` tem o matcher acima.
2. Gere um CPF **sintético** sem gravá-lo em arquivo: `uv run python -c "from taxlaw.synthetic_ids import make_cpf; print(make_cpf('987654321', formatted=True))"`.
3. Peça uma busca na web pela situação cadastral desse CPF, e depois uma consulta ao `taxlaw` que o contenha. Nos dois casos, a chamada deve ser bloqueada antes de sair, e o motivo deve dizer "1 CPF (números omitidos)" e o campo.

## O que observar

- **O hook roda no cliente, antes da chamada sair.** O server do `taxlaw` nem fica sabendo da tentativa. `WebSearch` e `WebFetch`, que nenhum server nosso vê, agora também têm guarda.
- **O que o hook não cobre.**
  - O texto que você digita: isso é outro evento, o `UserPromptSubmit`.
  - O `Bash` (um `curl` com o CPF passa). Essa ficou como decisão da spec, por ruído.
  - Falhas do próprio `uv`: se o comando nem chegar ao Python, o código não é 2 e a chamada segue. O server continua bloqueando o que for para o `taxlaw`.
- **Três camadas, uma função.** O hook, o `server.py` e o `tools.py` usam a mesma `guard.py`. Uma correção nela vale para os três.

## Pergunta de previsão

Depois do bloqueio, o que o modelo faz? Ele tenta de novo com o número disfarçado (com espaços, por extenso), desiste, ou explica ao usuário? Qual dessas reações o hook consegue impedir, e qual depende da skill do passo 12?

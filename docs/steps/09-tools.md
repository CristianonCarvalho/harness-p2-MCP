# Passo 09: as ferramentas como funções puras

## O que mudou

- `src/taxlaw/versions.py`: `choose_version(versions, when)` escolhe a versão de um dispositivo pela data de referência e diz se ela produz efeitos nessa data: `True`, `False` ou `None` (não sei). Fora de todas as versões, o dispositivo continua sendo devolvido: antes da primeira, a primeira; depois da última, a última.
- `src/taxlaw/tools.py`: `buscar_dispositivos` e `obter_dispositivo`, que recebem argumentos e devolvem dicionários, ainda sem MCP. Ordem de cada chamada:
  1. a guarda de CPF/CNPJ (`dados_de_contribuinte`);
  2. a validação (`entrada_invalida`);
  3. a busca, ou a leitura do corpus, com a versão escolhida pela data.
- Decisões de 2026-11-07:
  - os **filhos** vêm da versão do pai, mas o texto de cada filho é escolhido pela data. Em 2030, o § 1º do art. 156-A mostra o inciso IX na redação do art. 3º;
  - o **teto** de `obter_dispositivo` é de 4.000 caracteres;
  - os filhos aparecem na ordem da lei (I, II, …, V, …, IX, X), e não na ordem alfabética dos ids.

## Como rodar

```
uv run pytest tests/test_versions.py tests/test_tools.py tests/test_tools_real.py -v
uv run python -c "from taxlaw.tools import load_context, obter_dispositivo as o; c = load_context(); [print(d, o(c, 'CF.art156-A.par1.incIX', d)['versao']) for d in ('2025-01-01', '2030-06-01', '2040-01-01')]"
uv run python -c "import json; from taxlaw.tools import load_context, obter_dispositivo as o; print(json.dumps(o(load_context(), 'CF.art155.par3', '2033-01-01'), ensure_ascii=False, indent=2))"
```

## O que observar

- O mesmo id muda de texto com a data, e as outras versões aparecem sempre em `outras_versoes`.
- Um dispositivo revogado continua sendo encontrado. Ele vem com `produz_efeitos_na_data: false` e a `observacao` "revogado a partir de 2033-01-01 (EC 132/2023, art. 22, II, a)".
- **"Não encontrei" não é erro.** Volta `encontrado: false` com `motivo`. Só entrada inválida e CPF/CNPJ geram `ToolError`, e a mensagem nunca repete o número.
- A guarda roda antes da validação. Uma consulta longa demais que contém um CPF é bloqueada como `dados_de_contribuinte`, e não como entrada inválida.
- Nenhum dispositivo real chega ao teto: o maior, a EC, art. 9º, tem 3.013 caracteres. O truncamento é testado só com dados sintéticos.

## Pergunta de previsão

Por que `produz_efeitos_na_data` tem três valores, e não dois? Pense num dispositivo com `metodo: indeterminado`: o que o modelo diria ao usuário se recebesse `false` no lugar de `null`?

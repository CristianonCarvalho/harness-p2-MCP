# Passo 13b: efeitos do art. 544 e o corpus com duas fontes

## O que mudou

- **`ingest/lc_effects.py`** (novo) lê o art. 544 da LC 214 e calcula vigor e efeitos de cada registro da LC:
  - **vigor** = data de publicação (1ª nota "DOU de 16.1.2025");
  - **efeitos** = a data do inciso que alcança o artigo, ou o inciso VI ("demais dispositivos": 2026-01-01);
  - o inciso I ("primeiro dia do quarto mês subsequente") é calculado: 2025-05-01;
  - **travas, as mesmas da EC:**
    - um inciso não reconhecido bloqueia a regra dos demais;
    - um artigo citado com ressalva ("58, caput", "450, exceto os §§ 1º e 5º") ou em dois incisos fica `indeterminado`;
    - um dispositivo com redação dada ou incluído pela LC 227/2026 fica com vigor e efeitos nulos.
- **Build com duas fontes.** `ec132-2023` e `lc214-2025` conferem o próprio sha256, e o erro de qualquer uma aborta o build. O cabeçalho `fonte` virou **`fontes`**, chaveado pelo nome da fonte.
- **`corpus.py`:** `source_of(row)` deduz a fonte pelo prefixo da `versao`, e `coletado_em` é a coleta **mais antiga** entre as fontes.
- **`tools.py`:** o `fonte_url` vem da norma do dispositivo. O schema das ferramentas não mudou.
- **`corpus/dispositivos.json`:** 649 versões e 636 ids. As 487 linhas da EC são idênticas às de antes, e as 162 da LC vêm depois.
- **7 casos da LC conferidos à mão pelo usuário em 2026-11-09:** arts. 125, 127, II, 128, I, 126, § 6º, 142, II, 422, § 2º, e 419.

## Como rodar

```
uv run python -m taxlaw.ingest.build
uv run pytest tests/test_lc_effects.py tests/test_build.py tests/test_build_real.py -v
uv run python client/taxlaw_client.py obter LC214.art128.incI --data 2025-06-01
uv run python client/taxlaw_client.py buscar "cesta básica"
```

## O que observar

- **Vigor e efeitos se separam pela primeira vez.** O art. 128, I (serviços de educação, redução de 60%), está em vigor desde 2025-01-16, mas só produz efeitos a partir de 2026-01-01. Em 2025-06-01, a ferramenta responde "produz efeitos na data: não". É por isso que a spec manteve os dois campos desde o passo 05.
- **"Não sei" continua sendo resposta.** Os 4 dispositivos tocados pela LC 227 respondem `produz_efeitos_na_data: null`. A data deles está em outra lei, e o corpus não a inventa.
- **A LC usa as siglas que a EC não usa.** "IBS" e "CBS" sozinhos agora acham dispositivos, mas **só da LC**. A Constituição continua precisando da tabela "usuário diz → busque" da skill, e o teste da skill foi ajustado para dizer exatamente isso.
- **A busca já acha a LC sem recalibrar.** "cesta básica" traz a EC, art. 8º, e a LC, art. 125, entre os 3 primeiros; "redução de 30% advogados" traz o art. 127, II, em 1º. O limiar de 0,15 continuou separando as consultas do tema das de fora. A recalibração formal e a skill ficam para o 13c.

## Pergunta de previsão

O art. 544 escalona os efeitos por **artigo**. O art. 450 aparece com ressalva em dois incisos ("exceto os §§ 1º e 5º" no III; "§§ 1º e 5º" no IV): os parágrafos 1º e 5º seguem uma data, o resto do artigo segue outra. O parser marca o artigo inteiro como `indeterminado`. O que seria preciso para acertar a data parágrafo por parágrafo, e por que vale (ou não) a pena fazer isso agora?

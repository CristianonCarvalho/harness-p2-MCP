# Passo 13a: coleta e estrutura da LC 214

## O que mudou

- **`fetch.py` com várias fontes.** O dicionário `SOURCES` guarda, para cada norma, o nome, a URL oficial, os marcadores do corpo e o número que precisa estar no `<title>`. A opção `--source` escolhe a norma; sem ela, continua sendo a EC 132.
- **Bug achado no protótipo.** Os marcadores do passo 03 ("emenda constitucional" e "132") também aparecem na LC 214, que cita a EC. Com isso, a página da LC era aceita como se fosse a EC e sobrescrevia `ec132-2023.html`. Agora, se a página tem `<title>`, ele precisa conter o número da norma.
- **`corpus/raw/lc214-2025.html` e `.meta.json`:** coletados pelo navegador (`fetch(location.href)`) e gravados com `--source lc214-2025 --from-file`. Sha256 `0301816c…`, 5,4 MB.
- **`ingest/lc_structure.py`** (novo): HTML de lei compilada → registros. Reaproveita `Record`, `_Context` e `_label` do `structure.py`, que só ganhou o prefixo `LC214 → "LC 214/2025"`. Regras:
  - descarta a redação antiga, que vem num elemento com `line-through`;
  - um parágrafo parcialmente tachado é erro;
  - um id repetido é erro: seria redação antiga que escapou do tachado;
  - "(Redação dada / Incluído pela LC 227/2026)" vira `alteracao` e `origem` e sai do `texto`;
  - "(VETADO)" não vira registro;
  - títulos e seus nomes são ignorados;
  - um artigo do escopo ausente é erro.
- **`LC214_SCOPE`:** 23 artigos, os arts. 125 a 142 e 419 a 423 (spec do passo 13, seção 3).

## Como rodar

```
uv run pytest tests/test_lc_structure.py tests/test_lc_structure_real.py tests/test_fetch.py -v
uv run python -c "from pathlib import Path; from taxlaw.ingest.structure import decode_html; from taxlaw.ingest.lc_structure import parse_lc, LC214_SCOPE; r = parse_lc(decode_html(Path('corpus/raw/lc214-2025.html').read_bytes()), norma='LC214', scope=LC214_SCOPE); print(len(r.records), r.struck, r.vetoed, r.errors)"
```

## O que observar

- **Os números do HTML real.**
  - Os 23 artigos dão **162 registros**, sem erro nem aviso.
  - **3 tachados** foram descartados: as redações antigas do art. 142, II, e do art. 422, §§ 2º e 5º.
  - **2 vetados** ficaram sem registro: o art. 138, § 4º, e o art. 138, § 9º, II.
  - **4 dispositivos** foram tocados pela LC 227, contando o art. 126, § 6º, que foi incluído.
- **A página é a versão compilada:** quase 1.900 parágrafos tachados no total. Na lei inteira há 66 parágrafos **parcialmente** tachados, nenhum no escopo. Se o escopo crescer, eles viram erro, e não um texto errado em silêncio.
- **Ainda não muda nada no `dispositivos.json` nem nas ferramentas.** O build com duas fontes e os efeitos do art. 544 são o passo 13b.
- **Uma conferência que servia para uma norma não serve para duas.** "Tem 'emenda constitucional' e '132'" distinguia a EC de uma página de erro, mas não de outra norma que a cita.

## Pergunta de previsão

O parser descarta tudo o que está tachado. Se o Planalto mudar o jeito de marcar a redação antiga (por exemplo, para uma classe CSS em vez do `style`), o que acontece: o build falha, ou a redação antiga entra no corpus em silêncio? Qual regra do parser responde a isso?

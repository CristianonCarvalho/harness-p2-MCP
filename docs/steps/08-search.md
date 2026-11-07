# Passo 08: cabeçalho `fonte` e busca com limiar

## O que mudou

- **Formato do `corpus/dispositivos.json`:** agora é `{"fonte": {url, coletado_em, sha256_html}, "dispositivos": [...]}`. `fonte_url` e `coletado_em` saíram de cada registro, e o arquivo caiu de 8.768 para 7.801 linhas. Mudaram o `build` e os testes do passo 07.
- `src/taxlaw/corpus.py`: `load_corpus()` lê o arquivo; `Corpus.versao` é o sha256 dele. `ids()` e `versions(id)`.
- `src/taxlaw/search.py`: BM25 com um documento por `id` (citação + textos distintos de todas as versões), tokenizador de português (sem acento, plural no singular, sem palavras vazias, `156-A` junto) e **limiar de relevância 0,15**. Abaixo dele: `found=False` com o motivo.

## Como rodar

    uv run pytest tests/test_search.py tests/test_search_real.py -v

Para brincar:

    uv run python -c "from taxlaw.corpus import load_corpus; from taxlaw.search import build_index, search; ix = build_index(load_corpus()); print(search(ix, 'zona franca de manaus')); print(search(ix, 'receita de bolo de chocolate'))"

## O que observar

- **Pontuação absoluta não serve de limiar:** "art. 156-A" dá 2,2 e "horário de funcionamento do banco" dá 5,8. A **relevância** divide pela pontuação máxima que a consulta poderia ter, contando as palavras que nem existem no corpus como as mais raras possíveis. Medido: fora do tema até 0,130; dentro do tema a partir de 0,180. Limiar 0,15.
- **"Não encontrei" honesto:** "transição ICMS ISS" e "split payment" ficam abaixo do limiar porque a EC não usa essas palavras. Ela diz "o imposto previsto no art. 155, II". Reformular a consulta é trabalho da skill (passo 12), e é um bom caso para o P3.
- **"receita" tem dois sentidos:** "receita de bolo" acha "receita" no sentido tributário. O limiar segura porque "bolo" e "chocolate" puxam a relevância para baixo.
- **A busca não escolhe versão:** devolve o `id`; qual redação vale na data é o passo 09.
- **Cabeçalho `fonte`:** uma recoleta que muda uma vírgula agora muda uma linha de texto e uma de `coletado_em`, não 487.

## Pergunta de previsão

A relevância de "zona franca de manaus" é 0,404, e a de "Comitê Gestor do IBS" é 0,213. Sem rodar: o que acontece com a relevância de "Comitê Gestor do IBS" se você trocar "IBS" por "imposto sobre bens e serviços"? Sobe ou desce, e por quê?

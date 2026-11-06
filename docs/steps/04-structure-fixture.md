# Passo 04: structure com fixture sintética

## O que mudou

- `src/taxlaw/ingest/structure.py`: transforma o HTML da EC em registros `Record(id, citacao, norma, pai, versao, origem, alteracao, texto)`.
  - `decode_html` lê o charset declarado; sem declaração, usa windows-1252.
  - `paragraphs` extrai o texto limpo de cada `<p>` e a âncora `artN`, se houver.
  - `parse` monta os registros e uma lista de `warnings`.
- Testado só contra uma **fixture sintética** que imita o formato real (`dou-paragraph`, `<font>`, `&quot;`, `(NR)`, linhas de pontos, título de seção, link "Vigência", o mesmo inciso em dois artigos da EC). O arquivo real fica para o passo 05.

## Como rodar

    uv run pytest tests/test_structure.py -v

Para espiar o arquivo real (sem teste ainda, é o passo 05):

    uv run python -c "from taxlaw.ingest.structure import decode_html, parse; r = parse(decode_html(open('corpus/raw/ec132-2023.html','rb').read())); print(len(r.records), 'registros;', len(r.warnings), 'avisos'); print(*r.warnings[:5], sep='\n')"

## O que observar

- **A marca está no fechamento, não na abertura:** só ao chegar em `" (NR)` ou `"` o parser sabe se o bloco inteiro é `alterado` ou `incluido`. Por isso ele acumula os parágrafos do bloco e só cria os registros no fim (`flush_block`).
- **Linha de pontos posiciona, mas não registra:** em `"Art. 156-A. ....."`, `§ 1º .....`, `IX - texto novo`, o inciso IX ganha o `pai` certo (`CF.art156-A.par1`) mesmo sem registros para o artigo e o parágrafo nessa versão. Consequência: um `pai` pode não ter registro próprio (spec seção 9: "ancestral omitido").
- **Versões:** o mesmo `id` aparece com `versao` `EC132.art1` e `EC132.art3`, cada um com seu texto. No arquivo real são 9 dispositivos assim.
- **Avisos em vez de silêncio:** um parágrafo sem rótulo dentro de um bloco não é colado no anterior. Vira aviso, e o build (passo 07) decide o que fazer.
- **Ordinal legislativo:** art. 1º a 9º, art. 10 em diante sem "º".

## Pergunta de previsão

Rodando o parser no arquivo real, o protótipo deste passo gerou 485 registros e 21 avisos. Antes de rodar: que tipos de parágrafo você acha que viraram aviso? Dica: pense no que vem depois do art. 23 e em como o FrontPage às vezes cola o número do artigo no texto.

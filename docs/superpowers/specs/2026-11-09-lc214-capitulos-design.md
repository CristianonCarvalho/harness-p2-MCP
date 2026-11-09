# P2, passo 13: capítulos da LC 214/2025 no corpus (design)

- **Data:** 2026-11-09
- **Status:** design aprovado em conversa (partes 1 a 3); aguardando revisão desta spec escrita.
- **Spec principal:** [2026-11-05-mcp-reforma-tributaria-design.md](2026-11-05-mcp-reforma-tributaria-design.md). Esta spec detalha a linha "13: capítulos da LC 214" da seção 10 da principal. O que não está escrito aqui segue a principal.

## 1. Objetivo

Responder perguntas que hoje dão "não está no corpus", porque a EC 132 delega o assunto à lei complementar: cesta básica, reduções de 30% e de 60% das alíquotas do IBS e da CBS, e as alíquotas do Imposto Seletivo. É também a primeira vez que o corpus tem duas normas.

**Sucesso:**
- as consultas novas da seção 7 acham o artigo certo da LC no topo;
- os casos conferidos à mão pelo usuário passam;
- nenhuma redação tachada entra no corpus;
- os testes da EC continuam valendo, com as contagens separadas por norma.

## 2. Fatos medidos no HTML (2026-11-09)

Arquivo coletado pelo navegador com `fetch(location.href)` em `https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm`: 5,2 MB, windows-1252, CRLF, gerado pelo FrontPage, sha256 `0301816c65aef305df1824ef625b29acbc8fe964ece88cbb4f54efaeabd36685`.

- **É o texto compilado.** Há 766 marcas "(Incluído / Redação dada pela Lei Complementar nº 227, de 2026)", 2 da LC 235/2026 e 59 "Revogado".
- **A redação antiga continua na página.** O parágrafo inteiro vem dentro de um `<span … style="…text-decoration:line-through">`, logo antes da redação atual. São 1.953 ocorrências de `line-through` na página. Só 35 trechos usam `<strike>`.
- **Os parágrafos** são `<p class=MsoNormal>`, com âncoras por dispositivo (`<a name="art142-2">`, `<a name="art126§6">`). Títulos de LIVRO, TÍTULO, CAPÍTULO e Seção vêm em parágrafos próprios, seguidos do nome em outro parágrafo.
- **Rótulos nos capítulos escolhidos:** `Art.`, `§ Nº`, `Parágrafo único`, incisos romanos (`I -`) e alíneas (`a)`). Não há itens numerados.
- **Vigência (art. 544, redação atual):**
  - caput: "entra em vigor na data de sua publicação, produzindo efeitos:";
  - I: "a partir do primeiro dia do quarto mês subsequente ao da sua publicação", arts. 537 a 540;
  - II: 2025-01-01, arts. 35, 58, caput, 60, § 3º, 62, 266, 317, 403, 480 a 484, 516 e 541;
  - III: 2027-01-01, arts. 168 a 171, 309 a 315, 444, 450, exceto os §§ 1º e 5º, 461, 462, 467, 499, 500, 502, 504 a 507, 509 a 515, 517, 519 a 534 e 542. Este inciso tem redação dada pela LC 227, e a anterior está tachada;
  - IV: 2029-01-01;
  - V: 2033-01-01;
  - VI: 2026-01-01, "em relação aos demais dispositivos".
- **Publicação.** A 1ª nota é "Este texto não substitui o publicado no DOU de 16.1.2025 - Edição extra e republicado no DOU de 23.1.2025". A nota de 2.7.2025 é da promulgação de partes vetadas.
- **Vetos.** No escopo, só o art. 138, § 4º, e o art. 138, II, ambos "(VETADO)". Nenhuma "(Promulgação partes vetadas)" no escopo; fora dele há, por exemplo no art. 26.
- **Alterações da LC 227 no escopo:** art. 126, § 6º (incluído), art. 142, II (redação dada), e art. 422, §§ 2º e 5º (redação dada).
- **Anexos.** As listas concretas (produtos da cesta básica, serviços e produtos com redução) estão em tabelas nos Anexos, que **não** fazem parte do escopo.

## 3. Escopo

| Parte da LC 214 | Artigos | Assunto |
|---|---|---|
| Livro I, Título III, Capítulo II | 125 | cesta básica nacional (alíquota zero) |
| Livro I, Título IV, Capítulos I a III | 126 a 142 | regimes diferenciados: disposições gerais, redução de 30% e redução de 60% |
| Livro II, Título II, Capítulo IV | 419 a 423 | alíquotas do Imposto Seletivo |
| Livro III, art. 544 | 544 | só para calcular os efeitos; não vira registro |

**Fora:** os Anexos, os demais capítulos e as alterações como versões separadas. Os capítulos mais procurados que ficaram de fora, como fato gerador e base de cálculo (arts. 4 a 57, com 141 marcas da LC 227) e as alíquotas de transição (arts. 342 a 370, com 89), precisam de versões e da LC 227 no corpus. Ficam como limite registrado.

## 4. Modelo dos registros

Os mesmos 14 campos da spec principal; o schema das ferramentas não muda.

| Campo | LC 214 |
|---|---|
| `id` | `LC214.art128.par1.incII.alia` (mesmo esquema da CF; `parunico` para parágrafo único) |
| `citacao` | `LC 214/2025, art. 128, § 1º, II, a` |
| `norma` | `LC214` |
| `pai` | o id do nível acima; o artigo não tem pai |
| `versao` | `LC214`, uma versão só, a redação atual |
| `origem` | `LC 214/2025`; `LC 214/2025, com redação dada pela LC 227/2026`; ou `LC 214/2025, incluído pela LC 227/2026` |
| `alteracao` | `original`; `alterado` ("Redação dada pela"); `incluido` ("Incluído/Incluída pela") |
| `texto` | o texto do parágrafo, sem a marca de alteração no fim |

Regras do parser `ingest/lc_structure.py` (novo; o `structure.py` da EC não muda):

1. Decodifica windows-1252 e lê os `<p>` em ordem.
2. **Descarta todo parágrafo cujo texto está inteiro dentro de `line-through`.** É a redação antiga. Um parágrafo com só uma parte tachada é **erro**, que aborta o build, porque não dá para saber qual é o texto vigente.
3. Títulos (LIVRO, TÍTULO, CAPÍTULO, Seção, Subseção) e o nome que vem em seguida não viram registro.
4. Um rótulo reconhecido abre um registro: `Art. N[-X].`, `§ Nº`, `Parágrafo único.`, `<romano> -`, `<letra>)`. O pai vem da pilha de níveis.
5. Uma marca de alteração no fim define `alteracao` e `origem` e é tirada do `texto`.
6. **Dispositivo "(VETADO)" não vira registro**, porque não tem texto normativo. Ele é contado no relatório.
7. Dispositivo com "(Promulgação partes vetadas)" vira registro com efeitos `indeterminado`. A data de vigor dele é a da promulgação, que o parser não deduz. Não há nenhum no escopo, mas a regra existe para não errar se o escopo crescer.
8. Só os artigos do escopo (seção 3) geram registros. Um artigo do escopo que não for encontrado é **erro**.
9. Parágrafo com texto e sem rótulo, dentro do escopo, gera **aviso** no relatório.

## 5. Efeitos (art. 544)

Função nova `lc_effects_for(records, paragraphs)` em `ingest/lc_effects.py`, no estilo de `effects.py`.

- **Vigor:** `vigor_desde` = data da 1ª nota "DOU de …" (2025-01-16), porque o caput diz "entra em vigor na data de sua publicação".
- **Efeitos por artigo:** cada inciso do art. 544, só na redação atual (sem tachado), vira uma regra com a data e a lista de artigos.
  - Datas reconhecidas: "1º de janeiro de AAAA", e "primeiro dia do <ordinal> mês subsequente ao da sua publicação", que dá o 1º dia do mês resultante.
  - Listas reconhecidas: números, "N a M", "N-A", separados por vírgula e "e".
  - "demais dispositivos" é a regra padrão.
- **Travas iguais às da EC:**
  - um inciso não reconhecido **bloqueia a regra padrão**: tudo o que dependeria dela fica `indeterminado`, com aviso;
  - um artigo citado com ressalva ("58, caput", "60, § 3º", "450, exceto os §§ 1º e 5º") fica `indeterminado` no artigo inteiro, porque a regra não é do artigo todo.
- **Alterações da LC 227:** todo registro `alterado` ou `incluido` fica com `vigor_desde`, `efeitos_desde` e `efeitos_ate` nulos e `metodo: indeterminado`. A data da nova redação está na LC 227, fora do corpus.
- **Fundamento:** `LC 214/2025, art. 544, VI` (ou o inciso aplicado). `fundamento_ate` é sempre nulo: não há revogação no escopo.
- **Resultado esperado no escopo:** `vigor_desde` 2025-01-16 e `efeitos_desde` 2026-01-01 (art. 544, VI) para todos, menos os 4 da LC 227, que ficam `indeterminado`.
- **Correções:** o `efeitos_correcoes.yaml` continua valendo por (`id`, `versao`). Para preencher a data de um dispositivo da LC 227, basta uma correção com fundamento.

## 6. Coleta e build com duas fontes

- **Coleta.** `fetch.py` deixa de ter a fonte fixa e passa a receber nome e URL (`--source-name`, `--source-url`). Os padrões continuam os da EC, para não mudar o comportamento atual. O arquivo vai para `corpus/raw/lc214-2025.html` com `lc214-2025.meta.json` (`metodo_coleta: arquivo`).
- **Fontes.** `build` passa a ler uma lista fixa: `ec132-2023` (structure + effects da EC) e `lc214-2025` (lc_structure + lc_effects). Cada fonte confere o próprio sha256.
- **Cabeçalho.** `fonte` vira `fontes: {"ec132-2023": {url, coletado_em, sha256_html}, "lc214-2025": {…}}`. Os registros mantêm 14 campos.
- **Fonte de cada registro.** É deduzida da `versao`: `EC132.*` vem de `ec132-2023`, e `LC214` de `lc214-2025`. Isso fica numa função só, em `corpus.py`.
- **Ordem.** Por (`id`, chave da versão), em que a chave da versão é (norma da versão, número do artigo da EC ou 0). As linhas da LC (`LC214…`) vêm depois de `EC132…`, e as linhas da EC não se movem.
- **Mínimo:** além do atual, `LC214.art125`, `LC214.art128`, `LC214.art422` e o art. 544 com o inciso VI reconhecido.
- **Relatório:** por norma, mais os descartes (tachados e vetados) e os avisos.

## 7. Ferramentas, busca e skill

- **Ferramentas:**
  - `fonte_url` de `obter_dispositivo` passa a ser o da fonte do dispositivo;
  - `corpus.coletado_em` passa a ser a coleta **mais antiga** entre as fontes. Assim o schema e a skill não mudam;
  - nenhum outro campo muda.
- **Teto:** medir se algum artigo da LC passa de 4.000 caracteres (o art. 127 tem 18 incisos). Se passar, o truncamento existente vale, e o teste do corpus real deixa de dizer "nada é truncado".
- **Busca.** O corpus cresce, e o idf de cada termo muda.
  - Remedir `ON_TOPIC`, `OFF_TOPIC` e `VOCABULARY_GAPS`. Se 0,15 não separar mais os grupos, o novo limiar sai da medição e fica documentado.
  - Consultas novas, com o resultado esperado entre os primeiros:
    - "serviços de educação redução de 60%" → `LC214.art128` ou filho;
    - "alíquota zero cesta básica alimentação humana" → `LC214.art125`;
    - "imposto seletivo bens minerais alíquota máxima" → `LC214.art422.par2`;
    - "redução de 30% advogados" → `LC214.art127` ou filho.
- **Skill:**
  - a `description` ganha "LC 214", "cesta básica" e "redução de alíquota";
  - o corpo diz que o corpus inclui esses capítulos da LC 214 e que os Anexos não estão nele;
  - a tabela "usuário diz → busque" ganha cesta básica e reduções de 30% e 60%, conferidas pelo `test_skill`.

## 8. Testes

- **Sintéticos (HTML escrito à mão no formato da LC):**
  - `MsoNormal`, âncoras e títulos de Seção;
  - parágrafo `line-through` descartado; tachado parcial → erro;
  - "(Redação dada / Incluído pela …)" → `alteracao` e `origem`, com a marca tirada do texto;
  - "(VETADO)" não vira registro;
  - artigo do escopo ausente → erro;
  - um art. 544 sintético com "quarto mês subsequente", artigo com ressalva e inciso não reconhecido.
- **Reais:**
  - nenhum `texto` do corpus é igual a um parágrafo tachado do HTML;
  - os 4 dispositivos da LC 227 com `indeterminado`;
  - os demais com vigor 2025-01-16 e efeitos 2026-01-01 (art. 544, VI);
  - o art. 138, § 4º, e o art. 138, II, ausentes (vetados);
  - pares (`id`, `versao`) únicos e `pai` existente;
  - `dispositivos.json` versionado igual ao build de hoje.
- **Conferidos pelo usuário:** de 5 a 8 dispositivos da LC conferidos à mão contra o Planalto (texto, citação, efeitos), que viram um teste, como no passo 07.
- **Testes atuais que mudam de propósito:** as contagens passam a ser separadas por norma (EC: 487 versões, 474 ids, inalteradas), a estrutura mínima cresce, e o tamanho máximo das respostas e a calibração da busca são remedidos.

## 9. Passos

| Passo | Conteúdo | Tag |
|---|---|---|
| 13a | `fetch` parametrizado; `corpus/raw/lc214-2025.*`; `ingest/lc_structure.py` com testes sintéticos e reais | `step-13a` |
| 13b | `ingest/lc_effects.py`; build com duas fontes; `dispositivos.json` novo; `fonte_url` e `coletado_em` por fonte; casos conferidos pelo usuário | `step-13b` |
| 13c | recalibração da busca; consultas novas; skill; README (limites); diagrama do corpus | `step-13c` |

Cada passo tem protótipo, plano, `meister orchestrate`, conferência contra o protótipo e uma nota em `docs/steps/13a-…`, `13b-…` e `13c-…`.

## 10. Limites que continuam

- Os Anexos ficam fora, e com eles as listas de produtos e serviços: a ferramenta diz o que a lei diz ("relacionados no Anexo I"), mas não o que está no anexo.
- A redação anterior às alterações da LC 227 é descartada. Os dispositivos alterados ficam com efeitos `indeterminado` até uma correção com fundamento.
- Os capítulos com muitas alterações (fato gerador, base de cálculo, transição) dependem de versões e da LC 227 no corpus.
- A coleta continua manual, pelo navegador.

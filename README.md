# P2: MCP server da reforma tributária

MCP server que busca dispositivos da reforma tributária (EC 132/2023) e responde **sempre** com o dispositivo citado e a data a partir da qual ele produz efeitos, em formato estruturado e verificável. Junto vêm uma skill que ensina o modelo a usá-lo e um hook que bloqueia CPF/CNPJ antes de qualquer chamada de ferramenta.

É o projeto P2 do roadmap "Engenharia de Software com Agentes de IA" (Fase 2: engenharia de contexto e harness). Foi feito em passos pequenos, cada um com uma nota em [`docs/steps/`](docs/steps/) e uma tag `step-NN`.

## Critério de concluído

| Critério | Como foi provado | Passo |
|---|---|---|
| O **mesmo** server funciona no Claude Code e no Kiro | Consulta real nos dois clientes. O Claude Code abre sem sessão (revisão 2026-07-28); o Kiro CLI 3.1.0 abre com `initialize` (2025-11-25). Nenhuma linha mudou entre um e outro | 10, 14 |
| Um hook bloqueia uma ação proibida | No Claude Code, uma chamada com CPF sintético foi bloqueada antes de chegar ao server, e o motivo não repete o número | 11 |
| Há uma skill que usa o server | `/consultar-reforma-tributaria` fez o modelo buscar com as palavras da lei e responder "a EC não fixa um percentual" em vez de inventar um número | 12 |

## Como usar

```
uv sync
uv run pytest                      # 442 testes, todos offline
uv run python -m taxlaw.server     # o server via stdio (normalmente é o cliente que o sobe)
```

- **Claude Code:** `.mcp.json` registra o server, `.claude/settings.json` registra o hook e `.claude/skills/` guarda a skill. Depois de clonar, abra o Claude Code na pasta do projeto e aprove o server `taxlaw`.
- **Kiro CLI:** `.kiro/settings/mcp.json`, `.kiro/hooks/` e `.kiro/skills/` apontam para os **mesmos** server, script e skill (a skill é um link simbólico). Rode `kiro-cli chat` na pasta e confie no workspace.

As ferramentas:
- `buscar_dispositivos(consulta, data_referencia?, limite?)` devolve candidatos com trecho e efeitos;
- `obter_dispositivo(id, data_referencia?, incluir_filhos?)` devolve o texto completo, os filhos, os efeitos, as outras versões e as observações.

O contrato completo está na [spec, seção 6](docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md).

## Arquitetura

```
Planalto (EC 132 e LC 214, HTML) ──navegador──▶ corpus/raw/ ──build (puro, determinístico)──▶ corpus/dispositivos.json
                                                                              │
cliente MCP ──hook PreToolUse──▶ server.py (guarda antes do SDK) ──▶ tools.py ──▶ search.py (BM25) + versions.py (data)
```

- **Lógica separada do protocolo.** `tools.py` são funções puras (argumentos → dicionário), testadas sem MCP. `server.py` é uma camada fina sobre elas.
- **Corpus versionado.** O HTML bruto e o JSON gerado ficam no git. O server e os testes nunca acessam a rede, e o diff mostra quando o texto da lei mudou.
- **Uma guarda só.** `guard.py` (CPF/CNPJ pelo dígito verificador) é usada pelo hook, pelo server e pelas ferramentas.

Diagramas: [corpus](docs/diagramas/bloco-2-corpus.md), [sequência de uma consulta](docs/diagramas/bloco-3-server.md) e [guardas](docs/diagramas/bloco-4-harness.md).

## Decisões

| Tema | Decisão | Por quê |
|---|---|---|
| Corpus | A EC 132/2023 e os dispositivos da CF e do ADCT que ela inclui ou altera (487 versões), mais, da LC 214/2025, cesta básica, reduções de 30% e 60% e alíquotas do Imposto Seletivo (162 registros) | A LC 214 inteira (mais de 500 artigos, compilada com 766 marcas de alteração da LC 227/2026) não cabe em passos pequenos; os capítulos escolhidos respondem o que a EC deixa para a lei complementar |
| Data que importa | Produção de efeitos (`efeitos_desde`/`efeitos_ate`), separada de entrada em vigor | Um campo só, "vigência", confunde as duas coisas |
| Versões | Um registro por (`id`, artigo da EC). A ferramenta escolhe a versão pela `data_referencia` | O mesmo inciso tem três redações na própria EC (2023, 2027 e 2033) |
| Datas de efeito | Automáticas a partir do art. 23 da EC; um arquivo de correções exige fundamento para cada exceção; o que o parser não resolve fica `indeterminado` | Nunca inventar uma data |
| Busca | Lexical (BM25 escrito no projeto) com limiar de relevância | Determinística e offline, o que permite regressão no P3. Embeddings exigiriam um modelo em tempo de execução |
| "Não sei" | `encontrado: false`, `produz_efeitos_na_data: null` e "redação anterior não incluída" são respostas, com `isError: false` | "Não encontrei" é uma resposta válida, nunca uma invenção |
| Retorno | Só dados, sem frases imperativas nem `instructions` no server | O texto da norma é dado, e é por aí que entra a injeção do P4 |
| Ferramentas | Duas: buscar (barata e larga) e obter (cara e focada) | O modelo paga pelo detalhe só do que escolheu |
| Guarda | Em camadas: hook (cliente), `server.py` (antes do SDK) e `tools.py`, todas com a mesma `guard.py`. O hook bloqueia na dúvida | Prompt melhora a taxa de acerto; o harness decide o que acontece quando o modelo erra |
| Execução | Cada passo foi protótipo no scratchpad → plano → `meister orchestrate` → conferência arquivo a arquivo contra o protótipo | O código entregue é exatamente o que foi testado |

## Limites conhecidos

- **Corpus parcial.** Da LC 214 há só alguns capítulos (cesta básica, reduções de 30% e 60%, alíquotas do Imposto Seletivo). Não há os demais capítulos da LC (fato gerador, base de cálculo, transição), os Anexos (as listas de produtos e serviços), resoluções do Senado nem leis dos entes. Alíquotas concretas, por exemplo, ficam fora.
- **Alterações da LC 227/2026.** Na LC 214, entra só a redação atual. Os 4 dispositivos alterados ou incluídos pela LC 227 ficam com efeitos `indeterminado` (a data está na LC 227, fora do corpus), e a redação anterior é descartada.
- **Vigor e efeitos separados.** Na LC 214, a lei vigora desde a publicação (2025-01-16), mas os capítulos do corpus só produzem efeitos a partir de 2026-01-01 (art. 544, VI). Um artigo citado com ressalva no art. 544 fica `indeterminado` no artigo inteiro.
- **Redação anterior ausente.** Para dispositivos `alterado`, o texto que valia antes da EC não está no corpus, e a ferramenta diz isso.
- **Efeito não é cobrança.** Um dispositivo pode produzir efeitos antes de o tributo ser cobrado; a cobrança segue a transição do ADCT (arts. 124 a 137). Juntar as peças é tarefa do modelo, e a skill pede isso.
- **Ancestrais omitidos.** A EC cita alguns caputs só como linha de pontos (ex.: o caput do art. 195 da CF). Eles não estão no corpus.
- **Busca lexical:**
  - siglas (IBS, CBS) acham só a LC 214, que as usa; a EC e a CF não, então a sigla nunca leva à Constituição. Palavras que nenhuma das normas usa (ICMS, split payment) não acham nada;
  - dispositivos de tributos diferentes com a mesma frase empatam: o do Imposto Seletivo veio à frente do do IBS.

  A skill compensa em parte, com a tabela "usuário diz → busque".
- **Hook:**
  - não vê o texto digitado pelo usuário, nem o `Bash` (um `curl` com o número passa);
  - não vê falhas do próprio `uv` antes do Python;
  - não vê números disfarçados (com espaços entre os dígitos, por extenso). Esse é o alvo do P4.
- **Skill.** O carregamento automático pela `description` é decisão do modelo. Nos testes deste projeto, ela só entrou com certeza quando foi invocada por `/consultar-reforma-tributaria`.
- **Kiro.** O server foi verificado numa consulta real. O hook e a skill no Kiro estão cobertos por testes, mas não foram vistos funcionando lá.
- **Coleta manual.** O Planalto derruba clientes automatizados. Os HTML foram baixados pelo navegador, e atualizar o corpus é um passo manual.

## O que deu errado

O resumo está em [docs/o-que-deu-errado.md](docs/o-que-deu-errado.md). Em uma frase: **os erros que importavam foram achados em protótipos e testes de mutação antes da entrega, e quase todos estavam em fronteiras.** O SDK repetia o valor rejeitado num erro, a regex da guarda não via um número depois de uma barra de URL, e um hook que sai com código 1 não bloqueia.

## Dados

Só normas públicas (texto oficial do Planalto) e números **sintéticos**, gerados em tempo de execução a partir de bases inventadas. Nenhum CPF ou CNPJ válido está escrito no repositório, nem em testes, exemplos ou traces.

## Próximos projetos

- **P3:** uma suíte de avaliação deste server, com perguntas anotadas, juiz calibrado e comparação com e sem a skill.
- **P4:** red team de prompt injection. O texto da norma volta só em `texto`/`trecho`, e a guarda de CPF/CNPJ é um alvo explícito de contorno.

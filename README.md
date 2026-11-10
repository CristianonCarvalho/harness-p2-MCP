# P2: MCP server da reforma tributária

MCP server que busca dispositivos da reforma tributária (EC 132/2023 e capítulos da LC 214/2025) e responde **sempre** com o dispositivo citado e a data a partir da qual ele produz efeitos, em formato estruturado e verificável. Junto vêm uma skill que ensina o modelo a usá-lo, um hook que bloqueia CPF/CNPJ antes de qualquer chamada de ferramenta, um cliente de terminal e um modo HTTP com token, publicado numa VPS.

É o projeto P2 do roadmap "Engenharia de Software com Agentes de IA" (Fase 2: engenharia de contexto e harness). Foi feito em passos pequenos, cada um com uma nota em [`docs/steps/`](docs/steps/) e uma tag (`step-NN` e, nos passos extras, `step-cliente`, `step-http`, `step-deploy` e outras).

## Critério de concluído

| Critério | Como foi provado | Passo |
|---|---|---|
| O **mesmo** server funciona no Claude Code e no Kiro | Consulta real nos dois clientes. O Claude Code abre sem sessão (revisão 2026-07-28); o Kiro CLI 3.1.0 abre com `initialize` (2025-11-25). Nenhuma linha mudou entre um e outro | 10, 14 |
| Um hook bloqueia uma ação proibida | No Claude Code, uma chamada com CPF sintético foi bloqueada antes de chegar ao server, e o motivo não repete o número | 11 |
| Há uma skill que usa o server | `/consultar-reforma-tributaria` fez o modelo buscar com as palavras da lei e responder "a EC não fixa um percentual" em vez de inventar um número | 12 |

Depois dos três critérios, o server ganhou o transporte HTTP, foi publicado numa VPS (`https://mcpreforma.cristianocarvalho.cloud/mcp`) e passou a responder, de lá, às mesmas perguntas (passos extras `http` e `deploy`).

## Como usar

```
uv sync
uv run pytest                      # 479 testes, todos offline
uv run python -m taxlaw.server     # o server via stdio (normalmente é o cliente que o sobe)
```

- **Claude Code:** `.mcp.json` registra o server, `.claude/settings.json` registra o hook e `.claude/skills/` guarda a skill. Depois de clonar, abra o Claude Code na pasta do projeto e aprove o server `taxlaw`.
- **Kiro CLI:** `.kiro/settings/mcp.json`, `.kiro/hooks/` e `.kiro/skills/` apontam para os **mesmos** server, script e skill (a skill é um link simbólico). Rode `kiro-cli chat` na pasta e confie no workspace.
- **Cliente de terminal** (`client/taxlaw_client.py`, sem modelo nenhum):
  ```
  uv run python client/taxlaw_client.py buscar "cesta básica" --limite 3
  uv run python client/taxlaw_client.py obter LC214.art125 --data 2026-06-01
  uv run python client/taxlaw_client.py --json obter CF.art156-A.par1.incIX --data 2030-06-01
  ```
  Com `--url`, ele fala com um server HTTP (o token vem de `TAXLAW_HTTP_TOKEN`, nunca de argumento).
- **Server HTTP** (`src/taxlaw/http.py`): `TAXLAW_HTTP_TOKEN=<32 caracteres ou mais> uv run python -m taxlaw.http --port 8000`. Sem token, ele não sobe. Para publicar, veja o roteiro em [`docs/deploy.md`](docs/deploy.md).
- **Server remoto no seu Claude Code**, sem pôr o token no git:
  ```
  claude mcp add --transport http --scope user taxlaw-remoto https://mcpreforma.cristianocarvalho.cloud/mcp \
    --header "Authorization: Bearer $TAXLAW_HTTP_TOKEN"
  ```
  O token é de quem opera o server (fica no `.env` da VPS). O modo `--scope user` grava em `~/.claude.json`, fora do repositório.

As ferramentas:
- `buscar_dispositivos(consulta, data_referencia?, limite?)` devolve candidatos com trecho e efeitos;
- `obter_dispositivo(id, data_referencia?, incluir_filhos?)` devolve o texto completo, os filhos, os efeitos, as outras versões e as observações.

O contrato completo está na [spec, seção 6](docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md).

## Arquitetura

```
Planalto (EC 132 e LC 214, HTML) ──navegador──▶ corpus/raw/ ──build (puro, determinístico)──▶ corpus/dispositivos.json

stdio:  cliente MCP ──hook PreToolUse──▶ server.py ──┐
                                                      ├──▶ guarda (guard.py) ──▶ tools.py ──▶ search.py (BM25) + versions.py (data)
HTTP:   cliente MCP ──HTTPS──▶ nginx (taxa) ──▶ container: token ▶ Host e tamanho ▶ server.py ──┘
```

- **Lógica separada do protocolo.** `tools.py` são funções puras (argumentos → dicionário), testadas sem MCP. `server.py` é uma camada fina sobre elas, e `http.py` só a coloca atrás de uma porta, com token.
- **Corpus versionado.** O HTML bruto e o JSON gerado ficam no git. O server e os testes nunca acessam a rede, e o diff mostra quando o texto da lei mudou.
- **Uma guarda só.** `guard.py` (CPF/CNPJ pelo dígito verificador) é usada pelo hook, pelo server e pelas ferramentas.
- **No caminho HTTP não há o hook do Claude Code.** A proteção fica toda do lado da VPS, em camadas: limite de taxa no nginx, token, `Host` e tamanho no server, e a guarda de CPF/CNPJ.

Diagramas: [corpus](docs/diagramas/bloco-2-corpus.md), [sequência de uma consulta](docs/diagramas/bloco-3-server.md), [guardas](docs/diagramas/bloco-4-harness.md) e [HTTP e deploy](docs/diagramas/bloco-5-http-deploy.md).

## Decisões

| Tema | Decisão | Por quê |
|---|---|---|
| Corpus | A EC 132/2023 e os dispositivos da CF e do ADCT que ela inclui ou altera (487 versões), mais, da LC 214/2025, cesta básica, reduções de 30% e 60% e alíquotas do Imposto Seletivo (162 registros) | A LC 214 inteira (mais de 500 artigos, compilada com 766 marcas de alteração da LC 227/2026) não cabe em passos pequenos; os capítulos escolhidos respondem o que a EC deixa para a lei complementar |
| Data que importa | Produção de efeitos (`efeitos_desde`/`efeitos_ate`), separada de entrada em vigor | Um campo só, "vigência", confunde as duas coisas |
| Versões | Um registro por (`id`, artigo da EC). A ferramenta escolhe a versão pela `data_referencia` | O mesmo inciso tem três redações na própria EC (2023, 2027 e 2033) |
| Datas de efeito | Automáticas a partir do art. 23 da EC e do art. 544 da LC; um arquivo de correções exige fundamento para cada exceção; o que o parser não resolve fica `indeterminado` | Nunca inventar uma data |
| Busca | Lexical (BM25 escrito no projeto) com limiar de relevância | Determinística e offline, o que permite regressão no P3. Embeddings exigiriam um modelo em tempo de execução |
| "Não sei" | `encontrado: false`, `produz_efeitos_na_data: null` e "redação anterior não incluída" são respostas, com `isError: false` | "Não encontrei" é uma resposta válida, nunca uma invenção |
| Retorno | Só dados, sem frases imperativas nem `instructions` no server | O texto da norma é dado, e é por aí que entra a injeção do P4 |
| Ferramentas | Duas: buscar (barata e larga) e obter (cara e focada) | O modelo paga pelo detalhe só do que escolheu |
| Guarda | Em camadas: hook (cliente), `server.py` (antes do SDK) e `tools.py`, todas com a mesma `guard.py`. O hook bloqueia na dúvida | Prompt melhora a taxa de acerto; o harness decide o que acontece quando o modelo erra |
| Transporte | stdio para Claude Code e Kiro; Streamable HTTP **stateless** acrescentado, sem substituir o stdio | O stdio não precisa de porta nem de rede; o HTTP é o que permite um cliente em outra máquina. A revisão 2026-07-28 já é sem sessão |
| Autenticação do HTTP | Um token fixo (mínimo de 32 caracteres) numa variável de ambiente, conferido por um middleware, em tempo constante | OAuth só se justifica para cadastro aberto ou para conectores públicos. O token também deixa o server fechado mesmo se esquecerem o proxy |
| Deploy | Docker Compose numa VPS que já tem nginx e certbot, com a porta só em `127.0.0.1:8020`, container sem privilégios e sistema de arquivos só de leitura | Segue o padrão dos outros apps da VPS e não expõe nada fora do nginx |
| Cliente de terminal | Um script fora do pacote, com o SDK oficial, que acha o server pelo `.mcp.json` ou por `--url` | Consultar sem modelo, em scripts e no P3, e testar a guarda onde não há hook |
| Execução | Cada passo foi protótipo no scratchpad → plano → `meister orchestrate` → conferência arquivo a arquivo contra o protótipo | O código entregue é exatamente o que foi testado |

## Limites conhecidos

- **Corpus parcial.** Da LC 214 há só alguns capítulos (cesta básica, reduções de 30% e 60%, alíquotas do Imposto Seletivo). Não há os demais capítulos da LC (fato gerador, base de cálculo, transição), os Anexos (as listas de produtos e serviços), resoluções do Senado nem leis dos entes. Alíquotas concretas, por exemplo, ficam fora.
- **Alterações da LC 227/2026.** Na LC 214, entra só a redação atual. Os 4 dispositivos alterados ou incluídos pela LC 227 ficam com efeitos `indeterminado` (a data está na LC 227, fora do corpus), e a redação anterior é descartada.
- **Vigor e efeitos separados.** Na LC 214, a lei vigora desde a publicação (2025-01-16), mas os capítulos do corpus só produzem efeitos a partir de 2026-01-01 (art. 544, VI). Um artigo citado com ressalva no art. 544 fica `indeterminado` no artigo inteiro.
- **Redação anterior ausente.** Para dispositivos `alterado`, o texto que valia antes da EC não está no corpus, e a ferramenta diz isso.
- **Efeito não é cobrança.** Um dispositivo pode produzir efeitos antes de o tributo ser cobrado; a cobrança segue a transição do ADCT (arts. 124 a 137). Juntar as peças é tarefa do modelo, e a skill pede isso.
- **Listas cortadas.** Alguns dispositivos do corpus são só o começo de uma lista (por exemplo, o parágrafo único do art. 129 da LC 214 chega como "A redução de alíquotas prevista no caput deste artigo:", sem os incisos). A ferramenta não avisa, e uma resposta que dependa dos itens precisa dizer que não os viu.
- **Ancestrais omitidos.** A EC cita alguns caputs só como linha de pontos (ex.: o caput do art. 195 da CF). Eles não estão no corpus.
- **Busca lexical:**
  - siglas (IBS, CBS) acham só a LC 214, que as usa; a EC e a CF não, então a sigla nunca leva à Constituição. Palavras que nenhuma das normas usa (ICMS, split payment) não acham nada;
  - dispositivos de tributos diferentes com a mesma frase empatam: o do Imposto Seletivo veio à frente do do IBS.

  A skill compensa em parte, com a tabela "usuário diz → busque".
- **Hook:**
  - não vê o texto digitado pelo usuário, nem o `Bash` (um `curl` com o número passa);
  - não vê falhas do próprio `uv` antes do Python;
  - não vê números disfarçados (com espaços entre os dígitos, por extenso). Esse é o alvo do P4;
  - **não cobre o server remoto:** o matcher casa `mcp__taxlaw__.*`, e o server remoto, cadastrado como `taxlaw-remoto`, tem outro prefixo. Nele vale só a guarda do próprio server.
- **Skill.** O carregamento automático pela `description` é decisão do modelo. Nos testes deste projeto, ela só entrou com certeza quando foi invocada por `/consultar-reforma-tributaria`. As descrições das ferramentas e a skill dizem o que o corpus contém, e um teste as prende às **fontes** do corpus, mas não aos **capítulos** da LC: um capítulo novo exige atualizar o texto à mão.
- **Kiro.** O server foi verificado numa consulta real. O hook e a skill no Kiro estão cobertos por testes, mas não foram vistos funcionando lá.
- **HTTP e deploy:**
  - um token só, sem rotação além de editar o `.env` e recriar o container, e sem OAuth, o que impede o uso em conectores do claude.ai e do Claude Desktop, que esperam OAuth;
  - o nginx e o certbot precisam de sudo, então essa parte é manual (o roteiro está em `docs/deploy.md`);
  - o cliente só reconhece 401, 421 e conexão recusada com mensagem própria; os demais erros de rede aparecem como "não consegui falar com o server";
  - os diagramas mermaid foram revisados à mão, mas nenhum renderizador rodou antes do commit: confira no GitHub.
- **Coleta manual.** O Planalto derruba clientes automatizados. Os HTML foram baixados pelo navegador, e atualizar o corpus é um passo manual.

## O que deu errado

O resumo está em [docs/o-que-deu-errado.md](docs/o-que-deu-errado.md), com 24 falhas. Em uma frase: **os erros que importavam foram achados em protótipos e testes de mutação antes da entrega, e quase todos estavam em fronteiras.** O SDK repetia o valor rejeitado num erro, a regex da guarda não via um número depois de uma barra de URL, um hook que sai com código 1 não bloqueia, uma página de lei era aceita como se fosse outra, e um teste de segurança mal escrito podia pendurar a suíte inteira.

## Dados

Só normas públicas (texto oficial do Planalto) e números **sintéticos**, gerados em tempo de execução a partir de bases inventadas. Nenhum CPF ou CNPJ válido está escrito no repositório, nem em testes, exemplos ou traces. O token do server HTTP vive só no `.env` da VPS (permissão 600), que está no `.gitignore` e no `.dockerignore`.

## Próximos projetos

- **P3:** uma suíte de avaliação deste server, com perguntas anotadas, juiz calibrado e comparação com e sem a skill. Já há material: perguntas como "qual o prazo do IBS e da CBS na transição?" não têm um dispositivo só e exigem juntar vários artigos, e o P3 pode rodá-las também contra a URL pública.
- **P4:** red team de prompt injection. O texto da norma volta só em `texto`/`trecho`, e a guarda de CPF/CNPJ é um alvo explícito de contorno.

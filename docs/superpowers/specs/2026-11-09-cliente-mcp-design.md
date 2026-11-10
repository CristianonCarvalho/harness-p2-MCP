# P2, extra: cliente MCP para o taxlaw (design)

- **Data:** 2026-11-09
- **Status:** implementado (tag `step-cliente`). O `--url` veio depois, com o transporte HTTP, e a mensagem do 421, em `step-421`.
- **Spec principal:** [2026-11-05-mcp-reforma-tributaria-design.md](2026-11-05-mcp-reforma-tributaria-design.md). Este cliente não muda o server nem as ferramentas.

## 1. Objetivo

Uma **ferramenta prática de terminal** para consultar o server `taxlaw` como cliente MCP de verdade, sem o Claude Code e sem modelo nenhum. É a contraparte do `echo/` (passo 01): lá, um server feito à mão; aqui, um cliente que usa o SDK oficial.

**Para que serve:**
- consultar o corpus rapidamente pelo terminal;
- usar em scripts (e no P3) com `--json`;
- testar a guarda do server **fora** do Claude Code, onde não existe o hook.

**Sucesso:**
- `ferramentas`, `buscar` e `obter` funcionam contra o server real, via stdio;
- `--json` devolve exatamente o `structuredContent`;
- os códigos de saída seguem a seção 4;
- o cliente não importa `taxlaw`;
- o cliente roda a partir de qualquer diretório.

## 2. Decisões

| Tema | Decisão | Descartado e por quê |
|---|---|---|
| Implementação | SDK oficial (`mcp.client.Client` + `StdioServerParameters`) | Feito à mão: didático, mas o objetivo aqui é uma ferramenta prática |
| Interface | Comandos de uma vez: sobe o server, faz uma chamada e sai | REPL: mais código e mais difícil de testar |
| Saída | Legível por padrão; `--json` imprime o `structuredContent` cru | Só JSON: ruim de ler. Só legível: ruim para scripts |
| Lugar | Um script em `client/taxlaw_client.py`, como o `echo/` | Pacote com comando instalado: divide o `pyproject` com o server. Projeto separado: dois ambientes, gate mais complexo |
| Como achar o server | A entrada `taxlaw` do `.mcp.json`, a mesma do Claude Code e do Kiro; `--server "cmd args"` sobrescreve | Comando fixo no código: duplicaria a configuração |

## 3. Componentes

Um arquivo, `client/taxlaw_client.py`, com quatro partes de fronteiras claras:

1. **`server_params(mcp_json: Path, name="taxlaw", override: str | None = None) -> StdioServerParameters`**
   - lê `mcpServers[name]` (`command` e `args`) do `.mcp.json`;
   - com `override`, divide o texto com `shlex.split` e usa isso no lugar;
   - `cwd` é a pasta do `.mcp.json`, para o `uv run` achar o projeto;
   - arquivo ausente, JSON inválido ou entrada inexistente levantam `ClientError`.
2. **`list_tools(params)` e `call(params, tool, arguments) -> CallToolResult`:** a **única** parte que fala MCP. Abre o `Client` via stdio, faz uma operação e fecha, com teto de 30 s (`anyio.fail_after`). Falha ao subir ou ao responder levanta `ClientError`.
3. **`render_busca(data: dict) -> str`, `render_dispositivo(data: dict) -> str` e `render_ferramentas(tools) -> str`:** funções puras de dicionário para texto, sem server. Um campo ausente vira "—", nunca uma exceção.
4. **`main(argv: list[str] | None = None) -> int`:**
   - argparse com os subcomandos:
     - `ferramentas`;
     - `buscar CONSULTA [--data AAAA-MM-DD] [--limite N]`;
     - `obter ID [--data AAAA-MM-DD] [--sem-filhos]`;
   - opções globais: `--json`, `--server "cmd args"` e `--mcp-json CAMINHO` (padrão: o `.mcp.json` da raiz do repositório, achado a partir do próprio arquivo);
   - só envia as opções que foram dadas (`data_referencia`, `limite`, `incluir_filhos`). Os padrões são os do server.

**Desacoplamento:** o cliente só importa a biblioteca padrão e o `mcp`. Os nomes das ferramentas e dos campos são os do contrato público do server (spec principal, seção 6), e não vêm de código compartilhado.

## 4. Códigos de saída e erros

| Código | Quando | Saída |
|---|---|---|
| 0 | a chamada funcionou, **inclusive com `encontrado: false`** | stdout |
| 1 | o server devolveu `isError` (`entrada_invalida`, `dados_de_contribuinte`) | stderr: o JSON de erro do server (`erro` e `mensagem`) |
| 2 | erro do cliente: uso errado (argparse), `.mcp.json` ausente ou sem `taxlaw`, server que não sobe, tempo esgotado | stderr: mensagem curta, sem traceback |

- **Nenhuma mensagem do cliente repete os argumentos.** Num erro, só aparece o que o server devolveu, e o server já não repete CPF/CNPJ.
- **O cliente não tem guarda própria de CPF/CNPJ.** Fora do Claude Code não há hook, e quem bloqueia é o server (camada 2). O cliente serve justamente para mostrar essa camada funcionando sozinha.

## 5. Formato legível

**`buscar`:**
- uma linha de cabeçalho: a consulta, a data de referência e o corpus (`coletado_em` e os 8 primeiros caracteres de `versao`);
- para cada resultado:
  - posição, `citacao`, `[id]` e "relevância" com vírgula decimal;
  - o `trecho`;
  - "efeitos desde … (fundamento)", mais "até …" quando houver, e "produz efeitos na data: sim | não | não se sabe".

Com `encontrado: false`, a saída é "Nada encontrado: <motivo>".

**`obter`:**
- `citacao` e `[id]`;
- a versão, com a origem e a alteração, e a data de referência;
- o `texto`;
- os filhos como "citação: texto". Um filho com `texto: null` aparece como "(não coube no teto; peça este id)";
- os efeitos, como na busca;
- as outras versões, como "versão (desde a até)";
- a observação e "truncado", quando houver;
- a fonte e o corpus.

Com `encontrado: false`, a saída é "Não encontrado: <id> (<motivo>)".

**Os três estados de `produz_efeitos_na_data`:** `true` vira "sim", `false` vira "não" e `null` vira "**não se sabe**". Nunca "não" no lugar de "não sei".

**`ferramentas`:** o nome, a primeira linha da descrição e os parâmetros do `inputSchema` (obrigatórios marcados).

## 6. Testes (`tests/test_taxlaw_client.py`)

Todos offline, independentes do diretório atual, sem `conftest.py` nem `sys.path`. O cliente é carregado pelo caminho do arquivo, com `importlib.util.spec_from_file_location`, como o teste do `echo/` faz.

- **Formatação, com dicionários sintéticos:**
  - os três estados de efeito;
  - observação, truncado e filho sem texto;
  - "Nada encontrado";
  - um campo ausente vira "—".
- **`server_params`:**
  - lê a entrada `taxlaw` do `.mcp.json` real;
  - o `cwd` é a raiz do repositório;
  - `--server` passa por `shlex`;
  - um `.mcp.json` ausente ou sem `taxlaw` é erro.
- **De ponta a ponta,** com o server real via stdio, subido com o próprio Python da suíte (`--server "<python> -m taxlaw.server"`):
  - `ferramentas` lista as 2;
  - `buscar "zona franca de manaus"` mostra `ADCT.art126.incIII.alia`;
  - `obter CF.art156-A.par1.incIX --data 2030-06-01` mostra a versão `EC132.art3`;
  - `--json` é igual ao `structuredContent`;
  - `--limite 11` sai com 1 e `entrada_invalida`;
  - um CPF sintético sai com 1 e `dados_de_contribuinte`, e o número não aparece no stdout nem no stderr;
  - "receita de bolo" sai com 0 e "Nada encontrado";
  - um server que não sobe sai com 2.
- **Com o comando do `.mcp.json` (`uv run …`):** uma chamada `ferramentas`, para provar que a configuração compartilhada funciona.
- **Desacoplamento:**
  - os imports de `client/taxlaw_client.py` (via `ast`) não incluem `taxlaw`;
  - o cliente rodado como subprocesso a partir de `tmp_path` funciona.

## 7. Fora do escopo

REPL, cache, várias chamadas por processo, servers HTTP ou SSE, configurar mais de um server pelo nome, e cores no terminal.

## 8. Passo

Um passo extra, fora da sequência da spec principal, com tag `step-cliente`. Ele pode rodar antes do 13b, porque não depende dele: o cliente só fala o contrato público, que o 13b não muda. Nota em `docs/steps/cliente-mcp.md`.

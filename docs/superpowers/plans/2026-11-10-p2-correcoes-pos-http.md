# P2: correções depois do passo HTTP (plano de implementação)

> **For agentic workers:** execute com `meister orchestrate --plan-file docs/superpowers/plans/2026-11-10-p2-correcoes-pos-http.json`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** três correções pequenas: as descrições das ferramentas passam a citar a LC 214 (com um teste que as prende ao corpus), o cliente diz "não há server escutando em <url>" numa conexão recusada, e o teste do 413 deixa de ser intermitente.

**Architecture:** substituições exatas em `server.py` (textos das descrições), `client/taxlaw_client.py` (função `_contains` e uma mensagem nova em `_run`), `tests/test_http.py` (dois testes) e `tests/test_server.py` (um teste novo). Nenhuma mudança de comportamento das ferramentas.

**Tech Stack:** Python 3.13, pytest, SDK `mcp` 2.3.0, `httpx2`.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-reforma-tributaria-design.md` (seção 6) e `docs/superpowers/specs/2026-11-09-transporte-http-design.md` (seções 3 e 6).

## Global Constraints

- Só as mudanças descritas; nenhuma ferramenta muda de comportamento nem de schema (além dos textos de descrição).
- Nenhuma mensagem do cliente contém o token.
- Testes 100% offline (só 127.0.0.1) e independentes do diretório atual; nada de `conftest.py`; nada de `sys.path`/`sys.modules` em testes; nenhum teste pode pendurar.
- Só dados públicos ou sintéticos; nunca CPF/CNPJ válido escrito no repositório.
- Mensagens, comentários e notas em português; identificadores em inglês.
- Não editar `CLAUDE.md`, `AGENTS.md`, `meister.config.yaml`, `.meister/`, `docs/superpowers/`, `echo/`, `corpus/`, `.claude/`, `.kiro/`, `hooks/`, `tools.py`, `http.py`.
- Nota do passo com `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.

## Fatos usados aqui (medidos em 2026-11-10 no protótipo)

- A descrição de `buscar_dispositivos` dizia "Busca dispositivos da reforma tributária (EC 132/2023) por palavras.", e a do parâmetro `consulta` não citava a LC 214, mesmo com o corpus incluindo a LC desde o passo 13b.
- Conexão recusada no cliente com `--url`: o `anyio` levanta `ExceptionGroup` → `httpx2.ConnectError` ("All connection attempts failed") → `httpcore2.ConnectError`. Antes, a mensagem era "não consegui falar com o server (ExceptionGroup)".
- `test_body_over_the_limit_is_413` falhou 1 vez em 3 rodadas da suíte com `ConnectionResetError`: o `RequestBodyLimitMiddleware` do SDK (`mcp/server/transport_security.py`) responde 413 pelo cabeçalho `Content-Length` sem ler o corpo e fecha; os bytes ainda não enviados viram reset. Com só os cabeçalhos por socket cru, passou em 6 de 6 rodadas.
- Mutações no protótipo: tirar a mensagem de porta fechada, tirar "LC 214/2025" da descrição e voltar o limite de corpo ao padrão quebram testes (o último por tempo do socket, 10 s, sem pendurar).

## Review Focus

- Corpus com uma fonte nova sem descrição atualizada (teste `test_descriptions_name_every_norm_in_the_corpus`).
- Server fora do ar ou ainda subindo aparecendo como "ExceptionGroup" (teste `test_client_cannot_reach_a_closed_port`).
- Teste do 413 intermitente por corrida de envio (teste `test_body_over_the_limit_is_413`, por socket cru).
- O token aparecendo na mensagem de conexão recusada (mesmo teste: `TOKEN not in err`).
- Stdio com comando inexistente continuando com "não consegui falar com o server" (teste existente `test_server_that_does_not_start_is_exit_2`, em `tests/test_taxlaw_client.py`, inalterado).

---

### Task 1: Descrições com a LC 214, conexão recusada e 413 sem corrida

**Files:**
- Modify: `src/taxlaw/server.py`
- Modify: `client/taxlaw_client.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_http.py`
- Create: `docs/steps/correcoes-pos-http.md`

**Interfaces:**
- Consumes: `build_server`, `CTX.corpus.fontes` (chaves `ec132-2023`, `lc214-2025`); `HttpTarget`, `_run` do cliente; o fixture `server` e `MAX_BODY_BYTES` de `tests/test_http.py`.
- Produces: `client/taxlaw_client._contains(exc, kind) -> bool`; a mensagem "não há server escutando em <url>" (código 2).

- [ ] **Step 1: testes que falham.** Em `tests/test_server.py`, antes de `def test_input_schemas_match_the_spec():`, acrescente:

```python
def test_descriptions_name_every_norm_in_the_corpus():
    # Se o corpus ganhar uma fonte, as descrições vistas pelo modelo precisam dizer.
    labels = {"ec132-2023": "EC 132/2023", "lc214-2025": "LC 214/2025"}
    assert set(CTX.corpus.fontes) == set(labels), "fonte nova no corpus: atualize as descrições e este teste"
    search = next(t for t in run(lambda c: c.list_tools()).tools if t.name == "buscar_dispositivos")
    for label in labels.values():
        assert label in search.description, label
        assert label in search.input_schema["properties"]["consulta"]["description"], label
    assert "Anexos" in search.description
```

Em `tests/test_http.py`, troque o teste `test_client_cannot_reach_a_closed_port` inteiro por:

```python
def test_client_cannot_reach_a_closed_port(capsys, monkeypatch):
    # Conexão recusada (server fora do ar ou ainda subindo) diz isso, com a URL.
    url = f"http://127.0.0.1:{free_port()}/mcp"
    code, _, err = run_cli(capsys, monkeypatch, url, "ferramentas")
    assert code == 2 and f"não há server escutando em {url}" in err and TOKEN not in err
```

e troque o teste `test_body_over_the_limit_is_413` inteiro por:

```python
def test_body_over_the_limit_is_413(server):
    # Só os cabeçalhos, por socket cru: o SDK decide pelo Content-Length antes de
    # ler o corpo. Mandar 64 KB de verdade dava corrida: o server responde 413 e
    # fecha antes de o cliente terminar de enviar, e às vezes vinha um "connection
    # reset" no lugar do 413 (falha intermitente achada no passo seguinte).
    host, port = server.removeprefix("http://").split("/")[0].split(":")
    request = (
        f"POST /mcp HTTP/1.1\r\nHost: {host}:{port}\r\nAuthorization: Bearer {TOKEN}\r\n"
        f"Content-Type: application/json\r\nAccept: application/json, text/event-stream\r\n"
        f"Content-Length: {MAX_BODY_BYTES + 1}\r\nConnection: close\r\n\r\n"
    )
    with socket.create_connection((host, int(port)), timeout=10) as conn:
        conn.sendall(request.encode())
        status_line = conn.recv(1024).split(b"\r\n", 1)[0]
    assert status_line.split()[1] == b"413", status_line
```

- [ ] **Step 2: rode e veja falhar.** `uv run pytest tests/test_server.py tests/test_http.py -q` → falham `test_descriptions_name_every_norm_in_the_corpus` e `test_client_cannot_reach_a_closed_port` (o do 413 já passa).

- [ ] **Step 3: descrições.** Em `src/taxlaw/server.py`, troque

```python
        consulta: Annotated[str, Field(description="Palavras a buscar no texto da EC 132/2023 e dos dispositivos da CF e do ADCT que ela inclui ou altera (1 a 500 caracteres).")],
```

por

```python
        consulta: Annotated[str, Field(description="Palavras a buscar no texto da EC 132/2023 (e dos dispositivos da CF e do ADCT que ela inclui ou altera) e dos capítulos do corpus da LC 214/2025 (1 a 500 caracteres).")],
```

troque

```python
        """Busca dispositivos da reforma tributária (EC 132/2023) por palavras.
```

por

```python
        """Busca dispositivos da reforma tributária por palavras.

        Corpus: EC 132/2023, com os dispositivos da CF e do ADCT que ela inclui
        ou altera, e da LC 214/2025 a cesta básica (art. 125), as reduções de
        30% e 60% (arts. 126 a 142) e as alíquotas do Imposto Seletivo (arts.
        419 a 423). Os Anexos da LC não estão no corpus.
```

e troque

```python
        Traz citação, origem na EC, filhos diretos, datas de efeito com
```

por

```python
        Traz citação, origem (artigo da EC 132/2023 ou LC 214/2025), filhos diretos, datas de efeito com
```

- [ ] **Step 4: cliente.** Em `client/taxlaw_client.py`, logo antes de `def _run(target: StdioServerParameters | HttpTarget, operation):`, acrescente:

```python
def _contains(exc: BaseException, kind: type[BaseException]) -> bool:
    """`exc`, ou algo dentro dele (grupos de exceções do anyio, causas), é do tipo `kind`?"""
    stack, seen = [exc], set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, kind):
            return True
        stack += list(getattr(current, "exceptions", ()))
        stack += [e for e in (current.__cause__, current.__context__) if e is not None]
    return False
```

e, em `_run`, troque

```python
        if 401 in statuses:
            raise ClientError("token recusado pelo server") from None
```

por

```python
        if 401 in statuses:
            raise ClientError("token recusado pelo server") from None
        if isinstance(target, HttpTarget) and _contains(exc, httpx2.ConnectError):
            # Conexão recusada: ninguém escutando na porta (server fora do ar,
            # ainda subindo ou URL errada). A URL não tem segredo; o token não aparece.
            raise ClientError(f"não há server escutando em {target.url}") from None
```

- [ ] **Step 5: rode e veja passar.** `uv run pytest tests/test_server.py tests/test_http.py tests/test_taxlaw_client.py -q` → 74 passed; `uv run pytest -q` → 462 passed. Rode a suíte inteira mais 2 vezes: as três rodadas passam.

- [ ] **Step 6: nota do passo.** Crie `docs/steps/correcoes-pos-http.md`:

````markdown
# Correções depois do passo HTTP

## O que mudou

- **As descrições das ferramentas agora citam a LC 214.** O modelo decide se e como usar uma ferramenta pela descrição dela, e a de `buscar_dispositivos` ainda dizia só "(EC 132/2023)". O 13c tinha atualizado a skill, mas não as descrições do server.
  - A descrição de `buscar_dispositivos` lista o corpus (EC 132, CF/ADCT, os capítulos da LC 214) e diz que os Anexos não estão nele.
  - A descrição do parâmetro `consulta` cita as duas normas.
  - A de `obter_dispositivo` fala em "artigo da EC 132/2023 ou LC 214/2025".
- **Um teste amarra as descrições ao corpus.** `test_descriptions_name_every_norm_in_the_corpus` falha se o corpus ganhar uma fonte nova sem que as descrições a mencionem.
- **O cliente diz quando não há server.** Com `--url`, uma conexão recusada virava "não consegui falar com o server (ExceptionGroup)". Agora é "não há server escutando em <url>". Foi o que aconteceu no teste manual: o cliente rodou antes de o server terminar de subir.
- **Um teste intermitente foi corrigido.** O `test_body_over_the_limit_is_413` mandava 64 KB de verdade, e às vezes o server respondia 413 e fechava antes de o cliente terminar de enviar, o que virava um "connection reset". Agora o teste manda só os cabeçalhos, com `Content-Length` acima do limite: o SDK decide pelo cabeçalho, sem corrida.

## Como rodar

```
uv run pytest tests/test_server.py tests/test_http.py -v
uv run python client/taxlaw_client.py ferramentas
uv run python client/taxlaw_client.py --url http://127.0.0.1:8999/mcp ferramentas   # sem server: "não há server escutando em ..."
```

## O que observar

- **Três lugares contam ao modelo o que existe no corpus:** a skill, as descrições das ferramentas e o próprio retorno. Atualizar um e esquecer outro deixa o modelo com informação contraditória. O teste novo prende as descrições ao corpus, como o `test_skill` já prendia a skill.
- **Mensagem de erro é interface.** "ExceptionGroup" diz o que quebrou no código; "não há server escutando em ..." diz o que fazer.
- **Um teste intermitente é um defeito.** Ele só aparecia de vez em quando, numa máquina com carga, e foi pego porque a suíte rodou várias vezes seguidas.

## Pergunta de previsão

Se você mudar o corpus para incluir outro capítulo da LC 214 (o de combustíveis, por exemplo) sem mexer nas descrições, o teste novo pega? Por quê? E o que pegaria esse esquecimento?
````

- [ ] **Step 7: commit.** `git add src/taxlaw/server.py client/taxlaw_client.py tests/test_server.py tests/test_http.py docs/steps/correcoes-pos-http.md && git commit -m "fix: descrições com a LC 214, conexão recusada no cliente e teste do 413 sem corrida"`

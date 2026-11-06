# Passo 03: coleta da EC 132 (fetch)

## O que mudou

- `src/taxlaw/ingest/fetch.py`: o **único** módulo do pacote com acesso à rede. Baixa a página oficial da EC 132/2023 do Planalto, ou lê uma página salva à mão (`--from-file`), e grava em `corpus/raw/`:
  - `ec132-2023.html`: os bytes exatamente como vieram, sem decodificar;
  - `ec132-2023.meta.json`: `url`, `coletado_em`, `metodo_coleta` (`http` ou `arquivo`), `sha256`, `tamanho_bytes`, `content_type`.
- Recusa conteúdo que não parece ser a EC 132 (vazio, página de erro, captcha). Não regrava nada se o texto não mudou.
- Um teste garante que nenhum outro módulo de `taxlaw` importa biblioteca de rede.

## Como rodar

    uv run pytest tests/test_fetch.py -v

Coleta de verdade. O Planalto derruba conexões de clientes automatizados (timeout sem resposta), então o caminho normal é:

1. Abra https://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc132.htm no navegador.
2. Cmd+S, formato **"Página da Web, somente HTML"**.
3. `uv run python -m taxlaw.ingest.fetch --from-file ~/Downloads/<arquivo>.htm`
4. Confira `corpus/raw/ec132-2023.meta.json` e faça commit dos dois arquivos.

Sem `--from-file`, o comando tenta baixar direto e, se falhar, diz para usar `--from-file`.

## O que observar

- **Bytes, não texto:** o Planalto usa encoding antigo (windows-1252). Decodificar aqui e regravar em UTF-8 mudaria o sha256 e esconderia o encoding do `structure`, que é quem decide.
- **`coletado_em` vem do meta, não do relógio:** o build (passo 07) lê essa data. Rodar o build amanhã gera o mesmo `dispositivos.json`.
- **PDF não serve como fonte:** "Imprimir → PDF" acrescenta cabeçalho e rodapé (data, URL, `1/29`) e transforma o tachado do Planalto (texto revogado) em desenho. Na extração, o texto revogado sairia igual ao vigente.
- **Cliente honesto:** o `User-Agent` diz o que é (`taxlaw-p2/0.1 ...`). Fingir ser navegador para furar o bloqueio desrespeita a escolha do site. E, como o bloqueio acontece antes do HTTP, nem funcionaria.
- **Rede isolada:** `test_fetch_is_the_only_module_that_imports_network_libraries` é uma regra de arquitetura virando teste. Se alguém fizer o server buscar algo online, a suíte quebra.

## Pergunta de previsão

Se você salvar a mesma página duas vezes, em dias diferentes, e rodar o `--from-file` nas duas, o sha256 vai ser igual? Pense no que o Planalto pode colocar na página que muda sem a lei mudar.

# Passo 07: build do corpus

## O que mudou

- `src/taxlaw/ingest/build.py`: junta `structure` + `effects` + correções manuais e grava `corpus/dispositivos.json`.
  - Confere o sha256 do HTML com o meta antes de tudo.
  - Lê `coletado_em` e a URL do meta, nunca do relógio.
  - **Aborta sem gravar nada** se houver erro no parser, se faltar a estrutura mínima (`CF.art149-B`, `CF.art156-A`, `ADCT.art125`, os 23 artigos da EC) ou se alguma correção for inválida.
  - `--check` só confere se o arquivo versionado está em dia.
- `corpus/efeitos_correcoes.yaml`: correções que vencem o automático. Cada uma exige `fundamento`. Hoje a lista está vazia: o automático não deixou nenhum indeterminado.
- `corpus/dispositivos.json`: 487 versões, 474 ids, 16 campos por registro, na ordem da spec.
- Primeira dependência externa: `pyyaml` (só `yaml.safe_load`, que não executa nada vindo do arquivo).

## Como rodar

    uv run python -m taxlaw.ingest.build          # gera e imprime o relatório
    uv run python -m taxlaw.ingest.build --check  # 0 = em dia, 1 = desatualizado
    uv run pytest tests/test_build.py tests/test_build_real.py -v

## O que observar

- **O relatório é o painel do corpus:** total, por norma, por método, correções, revogações, indeterminados e avisos. Hoje: 487 `automatico`, 0 indeterminados, 0 avisos.
- **A estrutura mínima pegou um erro meu:** no protótipo, a lista tinha `CF.art195`, mas o caput do art. 195 aparece no texto da EC só como linha de pontos e não vira registro. O build abortou, como deveria.
- **O arquivo versionado é testado contra o build:** `test_committed_dispositivos_is_exactly_what_build_generates_today`. Mudou o parser e esqueceu de regerar? A suíte quebra.
- **Conferência humana:** 10 casos conferidos por você contra o texto oficial em 2026-11-07 estão em `CHECKED_BY_USER`. É a única verificação do pipeline que não foi feita por código.
- **Ordem numérica das versões:** `EC132.art3` vem antes de `EC132.art10`. Como texto, "art10" < "art3".

## Pergunta de previsão

O `dispositivos.json` vai ser a única fonte do server (passos 08 a 10). Se amanhã o Planalto corrigir uma vírgula na página e você coletar de novo, quais arquivos do repositório mudam e quais testes quebram? Isso é bom ou ruim?

# Bloco 2: corpus (passos 02 a 07)

Diagramas do fim do bloco Corpus: o pipeline que transforma a página do Planalto em `corpus/dispositivos.json` e o modelo de dados que circula entre as etapas.

## Pipeline

```mermaid
flowchart TD
    P["Página da EC 132 no Planalto"] -->|"navegador: fetch(location.href) no Console"| F
    F["fetch (passo 03)<br/>único módulo com rede<br/>--from-file"] --> RAW
    RAW[("corpus/raw/<br/>ec132-2023.html (bytes exatos)<br/>ec132-2023.meta.json (url, coletado_em, sha256)")]

    RAW --> V{"sha256 do HTML<br/>bate com o meta?"}
    V -->|não| ABORT
    V -->|sim| S

    S["structure (passos 04 e 05)<br/>decode_html, paragraphs, parse"] -->|"487 Record<br/>um por (id, versao)"| E
    S -->|"errors: âncora artN sem caput"| ABORT
    S -->|"warnings: parágrafo sem rótulo"| REP

    E["effects (passo 06)<br/>art. 23: vigência por artigo da EC<br/>art. 22: 16 revogações"] -->|"Effects por (id, versao)"| C
    E -->|"indeterminado + aviso"| REP

    Y[("corpus/efeitos_correcoes.yaml<br/>cada correção exige fundamento")] --> C
    C["correções vencem o automático (passo 07)"] --> M
    C -->|"correção inválida"| ABORT

    M{"estrutura mínima?<br/>CF.art149-B, CF.art156-A,<br/>ADCT.art125, 23 artigos da EC"} -->|falta algo| ABORT
    M -->|ok| R

    R["render determinístico<br/>ordem (id, artigo da EC)"] --> J[("corpus/dispositivos.json<br/>487 versões, 474 ids")]
    R --> REP["relatório<br/>por norma, por método,<br/>indeterminados, avisos"]

    ABORT["build abortado<br/>nada é gravado"]

    J --> T["test_build_real<br/>arquivo versionado = build de hoje<br/>10 casos conferidos pelo usuário"]
    G["guard (passo 02)<br/>CPF e CNPJ por DV"] -.->|"usado pelo hook e pelo server<br/>(passos 10 e 11)"| SRV["server (bloco 3)"]
    J -.-> SRV
```

O que o diagrama mostra:

- **Rede só na borda.** O `fetch` é o único módulo que poderia acessar a rede, e na prática a coleta foi feita pelo navegador, porque o Planalto derruba clientes automatizados. Daí em diante, tudo é puro e offline.
- **Três saídas possíveis para um problema:** `ABORT` (resultado errado, nada é gravado), `indeterminado` (dado incompleto, registrado como tal) e aviso no relatório. Nenhum problema some em silêncio.
- **O fecho do ciclo:** `test_build_real` compara o arquivo versionado com o que o build gera hoje. Se alguém mudar parser, effects, correções ou HTML sem rodar o build, a suíte quebra.

## Passo 13: a LC 214 como segunda fonte

O pipeline acima continua sendo o da EC 132. Desde os passos 13a e 13b, o build lê também a LC 214, por um caminho próprio, e junta as duas fontes no mesmo arquivo.

```mermaid
flowchart TD
    PL["Página da LC 214 no Planalto<br/>versão compilada (com a LC 227/2026)"] -->|"navegador: fetch(location.href)"| FL
    FL["fetch --source lc214-2025<br/>confere o título da página"] --> RL[("corpus/raw/lc214-2025.html<br/>+ .meta.json (sha256)")]
    RL --> LS["lc_structure (13a)<br/>descarta redação tachada<br/>só os 23 artigos do escopo"]
    LS -->|"162 Record, versao LC214"| LE
    LS -->|"tachado parcial, id repetido,<br/>artigo do escopo ausente"| AB["build abortado"]
    LE["lc_effects (13b)<br/>art. 544: vigor na publicação,<br/>efeitos por inciso (VI: 2026-01-01)"] --> B
    LE -->|"LC 227, ressalva, inciso<br/>não reconhecido"| IND["indeterminado"]
    EC["caminho da EC 132<br/>(diagrama acima)"] --> B
    B["build: duas fontes,<br/>correções, estrutura mínima"] --> J[("corpus/dispositivos.json<br/>fontes: ec132-2023, lc214-2025<br/>649 versões, 636 ids")]
```

- **As linhas da EC não se movem.** Os ids da LC começam com `LC214`, que vem depois de `EC132` na ordem do arquivo.
- **A fonte de cada registro** sai do prefixo da `versao` (`EC132.*` ou `LC214`). É assim que `obter_dispositivo` devolve o `fonte_url` certo.
- **`corpus.coletado_em`** é a coleta mais antiga entre as fontes.

## Modelo de dados

```mermaid
classDiagram
    direction LR

    class Record {
        +str id
        +str citacao
        +str norma
        +str pai
        +str versao
        +str origem
        +str alteracao
        +str texto
    }

    class ArticleRule {
        +date desde
        +str fundamento
        +str metodo
    }

    class Revocation {
        +str id
        +date desde
        +str fundamento
    }

    class Effects {
        +date vigor_desde
        +date efeitos_desde
        +date efeitos_ate
        +str fundamento
        +str fundamento_ate
        +str metodo
    }

    class Correction {
        +str id
        +str versao
        +date efeitos_desde
        +date efeitos_ate
        +str fundamento
    }

    class Dispositivo {
        +str id
        +str versao
        +str citacao
        +str texto
        +str alteracao
        +date efeitos_desde
        +date efeitos_ate
        +str fundamento_efeitos
        +str fundamento_ate
        +str metodo
    }

    ArticleRule "1" --> "*" Effects : início pelo artigo da EC da versão
    Revocation "1" --> "*" Effects : término de versões anteriores
    Record "1" --> "1" Effects : mesma chave (id, versao)
    Correction "0..1" --> "1" Effects : vence o automático
    Record "1" --> "1" Dispositivo : render
    Effects "1" --> "1" Dispositivo : render
```

Leitura do modelo:

- **Chave (`id`, `versao`).** `versao` é o artigo da EC que traz aquele texto (`EC132.art3`). Um mesmo `id` pode ter várias versões, como `CF.art156-A.par1.incIX` nos arts. 1º, 3º e 4º.
- **`pai` pode ser um ancestral omitido**, citado no texto da EC só como linha de pontos (ex.: `CF.art43` para `CF.art43.par4`).
- **`alteracao`:** `incluido` (bloco fechado só com aspas), `alterado` (bloco fechado com "(NR)") ou `original` (texto da própria EC).
- **`metodo`:** `automatico`, `correcao` ou `indeterminado`. Com `indeterminado`, as datas ficam nulas: nunca são inventadas.
- **Datas que podem ser nulas:** `efeitos_ate` nulo quer dizer "sem término conhecido". `fundamento_ate` só existe quando o término vem de uma revogação do art. 22.
- **Formato do arquivo:** até o passo 07, cada registro também levava `fonte_url` e `coletado_em`. Desde o passo 08, eles ficam uma vez só no cabeçalho (`url`, `coletado_em`, `sha256_html`), e os registros vão em `dispositivos` (spec, seção 5). Desde o passo 13b, o cabeçalho é `fontes`, uma entrada por norma.
- **`alteracao` na LC 214:** `alterado` e `incluido` indicam redação dada ou inclusão pela LC 227/2026 (não pela EC), e `origem` diz isso por extenso.

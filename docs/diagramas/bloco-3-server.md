# Bloco 3: server (passos 08 a 10)

Este diagrama mostra a primeira consulta real (2026-11-08, Claude Code com o server `taxlaw` via stdio, revisão `2026-07-28`). A pergunta foi: *"Pela EC 132, o IBS integra a própria base de cálculo em 2030? Cite o dispositivo."*

> Este diagrama é do caminho **local, via stdio**. O caminho remoto (HTTPS, nginx, token) está no [bloco 5](bloco-5-http-deploy.md).

## Sequência de uma consulta

```mermaid
sequenceDiagram
    autonumber
    participant U as Usuário
    participant M as Modelo (Claude Code)
    participant S as server.py (processo filho, stdio)
    participant T as tools.py
    participant B as search.py e versions.py
    participant C as corpus/dispositivos.json

    Note over S,C: ao subir: load_context() lê o corpus e monta o índice BM25 uma vez
    S->>C: lê o arquivo, sha256 vira corpus.versao
    C-->>S: 487 versões, 474 ids

    U->>M: o IBS integra a própria base em 2030?
    Note over M: reformula com palavras da lei<br/>(a EC não usa a sigla IBS)

    M->>S: tools/call buscar_dispositivos<br/>consulta, data_referencia 2030-06-01
    Note over S: guarda de CPF e CNPJ nos argumentos crus,<br/>antes da validação do SDK
    S->>T: buscar_dispositivos(ctx, ...)
    Note over T: guarda de novo, depois validação
    T->>B: search(index, consulta, limite)
    B-->>T: ids acima do limiar 0,15
    T->>B: choose_version(versões do id, 2030-06-01)
    B-->>T: versão EC132.art3, produz efeitos true
    T-->>S: dict com resultados, motivo null, corpus
    S-->>M: structuredContent e o mesmo JSON como texto
    Note over M: escolhe entre 5 resultados<br/>(o 1º era do Imposto Seletivo, o do IBS veio em 3º)

    M->>S: tools/call obter_dispositivo<br/>CF.art156-A.par1.incIX, 2030-06-01
    S->>T: obter_dispositivo(ctx, ...)
    T->>B: choose_version
    B-->>T: EC132.art3, de 2027-01-01 a 2032-12-31
    T-->>S: texto, efeitos, outras_versoes, observacao
    S-->>M: structuredContent

    M->>S: tools/call obter_dispositivo<br/>CF.art156-A.par1, sem filhos
    S-->>M: caput do parágrafo 1º (a que imposto o inciso se refere)

    M-->>U: não, citação literal do art. 156-A, parágrafo 1º, IX,<br/>efeitos com fundamento e data de referência
```

## O que o diagrama mostra

- **Duas camadas de guarda dentro do server.** A primeira roda em `TaxLawServer.call_tool`, antes do SDK, porque o erro de validação do SDK repete o valor recebido. A segunda roda em `tools.py`, para quem chama as funções direto. O hook do passo 11 será a terceira, no cliente, antes de a chamada sair do Claude Code.
- **O server não guarda estado entre chamadas.** Cada `tools/call` traz `data_referencia`, e a resposta ecoa essa data junto com `corpus.versao`. O que fica em memória é o corpus e o índice, carregados uma vez ao subir. Por isso, mudar o `dispositivos.json` só vale depois de reiniciar o server.
- **Decidir é papel do modelo, não do server.** O server devolve dados: os resultados acima do limiar, a versão que vale na data e as outras versões. Reformular a consulta ("IBS" não está no texto) e escolher entre os resultados é com o modelo. Os dois pontos são candidatos a avaliação no P3 e a regra da skill no passo 12.
- **"Não encontrei" e "não sei" são dados.** `encontrado: false` volta com `isError: false`, e `produz_efeitos_na_data: null` é diferente de `false`.

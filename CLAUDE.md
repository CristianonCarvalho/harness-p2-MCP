# Projeto 2 (P2): MCP server de legislação tributária pública

## Roadmap

Este projeto é o **P2** do roadmap *"Roadmap 12 meses — Engenharia de Software com Agentes de IA"*:
https://claude.ai/artifact/QB4cRt3bGhyZL1DVF6D9ss (doc do Claude Docs, id `bba9da25-f37e-41e9-aaf3-35fe10a65996`).

Antes de decidir escopo ou critério, leia a seção **Fase 2** e a tabela **Projetos de portfólio** do roadmap. O roadmap é a fonte; este arquivo resume.

- **Fase 2: Engenharia de contexto e harness** (semanas 11–18, ~56 h).
- **Tópicos:** workflows vs agentes; compactação de contexto; subagentes; memória; CLAUDE.md e steering do Kiro; hooks; skills; MCP.
- **Recursos:** Anthropic, "Effective context engineering for AI agents" e "Building effective agents"; especificação Agent Skills; especificação MCP revisão 2026-07-28 (protocolo stateless); documentação oficial de Claude Code e Kiro.
- **Projeto:** MCP server de legislação tributária pública: busca, citação do dispositivo e data de vigência, + skill e hooks.
- **Dados:** normas públicas da RFB e dados abertos de CNPJ.
- **O que prova:** contexto, ferramentas, MCP stateless, portabilidade entre Claude Code e Kiro.

### Critério de concluído

1. O **mesmo** MCP server funciona em **Claude Code e no Kiro**.
2. Um **hook bloqueia uma ação proibida**.
3. Há uma skill que usa o server.

Escopo pode ser cortado; o critério de concluído, não.

## Regras do roadmap que valem aqui

- **Só dados públicos ou sintéticos. Nunca dados de contribuintes**, nem em testes, exemplos, fixtures ou traces.
- Repositório público, com README de decisões e limites e um texto curto explicando o que deu errado.
- Os projetos são encadeados: o **P3** é uma suíte de evals para este server (100 perguntas anotadas, taxonomia de erros, juiz LLM calibrado, regressão em CI) e o **P4** faz red team de prompt injection nele. Desenhe pensando nisso:
  - toda resposta traz o dispositivo citado e a data de vigência, em formato estruturado e verificável;
  - ferramentas determinísticas e testáveis offline;
  - "não encontrei" é uma resposta válida e explícita, nunca uma invenção;
  - o texto das normas é dado, não instrução (é por aí que entra a injeção do P4).
- Modo aprendizado: para conteúdo novo, prefira explicações e perguntas a respostas prontas.

## Herança do P1

O P1 está em `../projeto01` (repo `CristianonCarvalho/harness-p1-agente-minimo`). Reaproveite o que fizer sentido, como o cliente HTTP e o ledger de tokens e custo.

Forma de trabalho que deu certo no P1 e continua:

- Passos pequenos; cada passo é um commit com tag `step-NN` e uma nota em `docs/steps/NN-nome.md` com as seções `## O que mudou`, `## Como rodar`, `## O que observar`, `## Pergunta de previsão`.
- Spec em `docs/superpowers/specs/`, planos em `docs/superpowers/plans/`.
- Previsão antes de rodar, comparada com o resultado depois.
- Mensagens ao usuário e notas em português; identificadores de código em inglês.
- Testes offline: nenhum teste faz requisição de rede real; a suíte passa igual de qualquer diretório; nada de `conftest.py` ou truque que faça um teste passar sem corrigir o problema.

Lições das falhas do P1 (ver `../projeto01/README.md`, seção "Falhas Observadas"):

- Regra que importa fica no código ou num hook, não só no prompt. Prompt melhora a taxa de acerto; o harness decide o que acontece quando o modelo erra. O hook do critério 2 é exatamente isso.
- A guarda precisa estar no ponto por onde todas as ações passam; o agente acha a ferramenta sem guarda.
- Limites por resposta (tokens, número de chamadas) e registro no trace desde o início, não depois da primeira conta alta.
- "Sem chamada de ferramenta" nem sempre é resposta final; valide antes de encerrar.

## Segredos

- `.env` no `.gitignore` desde o primeiro commit; nunca commitar `.env`, traces ou execuções locais.
- Nunca exibir chaves de API (`OPENROUTER_API_KEY` ou outras) em saída, log, nota ou commit.

## Execução

No P1, a implementação foi feita com o MeisterRouter (`meister plan import` → `meister plan validate` → `meister orchestrate --plan-file`). Este projeto ainda não tem `.meister/` nem `meister.config.yaml`: configure o MeisterRouter antes de implementar, ou pergunte ao usuário qual método usar. Documentação (`docs/**`, `*.md`) pode ser editada direto.

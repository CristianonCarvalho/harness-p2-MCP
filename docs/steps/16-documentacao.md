# Passo 16: a documentação alcança o código

## O que mudou

Só documentação, editada direto (sem o Meister, como o `CLAUDE.md` permite para `docs/**` e `*.md`):

- **`README.md`:**
  - 479 testes (eram 442);
  - os caminhos de uso novos (cliente de terminal, server HTTP, server remoto no Claude Code) e o deploy publicado;
  - a arquitetura com os dois caminhos, stdio e HTTP;
  - quatro decisões novas na tabela (transporte, autenticação do HTTP, deploy, cliente de terminal);
  - limites novos: o hook não cobre o server remoto, listas cortadas no corpus, o que o HTTP não faz (token único, sem OAuth) e os diagramas ainda sem renderização conferida.
- **`docs/o-que-deu-errado.md`:** de 11 para **24 falhas** e de 6 para **12 lições**. As 13 novas vêm do que apareceu depois do passo 15: a página da LC aceita como a EC, o teste de segurança que pendurava a suíte, o teste do 413 intermitente, as mensagens de erro do cliente, o `limit_req_zone` do nginx, o hook que não cobre o server remoto e os problemas que já existiam na VPS.
- **Specs:** os `Status` deixaram de dizer "aguardando revisão". A spec principal ganhou a decisão do transporte HTTP, a árvore de arquivos atual e as linhas dos passos extras na tabela da seção 10.
- **Diagramas dos blocos 3 e 4:** avisam que são do caminho local e apontam para o bloco 5.
- **`docs/steps/15-readme.md`:** a frase "o passo 13 ficou para depois" aponta para o que aconteceu.

## Como conferir

```
uv run pytest -q                    # 479 testes: nenhum código mudou
git diff --stat                     # só *.md
grep -c "^| [0-9]* |" docs/o-que-deu-errado.md   # 24
```

## O que observar

- **O README tem números e afirmações que envelhecem:** a contagem de testes, "24 falhas" e a lista de limites. Quando o código mudar, a documentação precisa mudar no mesmo passo, e uma frase sobre o estado do projeto tem de ser conferida contra o repositório (aqui, `git tag`, a suíte e o `grep` acima).
- **Um limite documentado é uma promessa:** o README agora diz que o hook não cobre o `taxlaw-remoto`. Esse limite está **aberto**: falta estender o matcher em `.claude/settings.json`, que é configuração e não documentação, e por isso ficou fora deste passo.
- **O `CLAUDE.md` do projeto** ainda diz que o projeto "não tem `.meister/` nem `meister.config.yaml`", o que deixou de ser verdade. Ele é seu e não foi tocado.

## Pergunta de previsão

Daqui a um mês, o P3 vai medir as respostas do server. Quais das afirmações do README você espera que a suíte de avaliação **confirme** e quais ela pode **contradizer** (por exemplo, "a skill compensa em parte a lacuna das siglas")?

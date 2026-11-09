# Passo 15: README de decisões e limites, e o que deu errado

## O que mudou

- **`README.md`** reescrito para quem chega ao repositório público:
  - os três critérios de concluído e a evidência de cada um;
  - como usar no Claude Code e no Kiro;
  - a arquitetura em quatro frases, com links para os diagramas;
  - uma tabela de decisões, com o porquê de cada uma;
  - os limites conhecidos, ditos sem rodeio.
- **`docs/o-que-deu-errado.md`:** 11 falhas reais em ordem de gravidade, com onde, o que aconteceu e a situação; e as 6 lições que elas ensinam.
- Nenhum código mudou. O passo 13 (LC 214) ficou para depois: escopo pode ser cortado, critério não.

## Como rodar

```
uv run pytest -q
```

Leia o `README.md` como se fosse a primeira vez: dá para entender o que o projeto faz, como provar que funciona e onde ele falha, sem abrir a spec?

## O que observar

- **As falhas mais graves estão em fronteiras, não no domínio.** O SDK ecoava o valor rejeitado, a regex errava a borda de uma URL, e o hook dependia do código de saída. Nenhuma estava na lógica tributária.
- **Quase tudo foi achado antes da entrega**, por três hábitos que se repetiram em todos os passos: protótipo no dado real, teste de mutação e uma consulta real no cliente.
- **Limites escritos são parte do produto.** O P3 vai medir exatamente o que está na seção "Limites conhecidos" (ranking, siglas, carregamento da skill), e o P4 vai atacar o que está no hook.

## Pergunta de previsão

Das falhas abertas no README, qual você acha que o P3 vai encontrar primeiro, só com perguntas comuns de usuário: a sigla que não acha nada, o tributo errado no topo do ranking, ou a skill que não é carregada?

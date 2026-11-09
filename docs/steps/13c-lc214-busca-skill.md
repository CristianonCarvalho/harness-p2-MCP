# Passo 13c: busca recalibrada, skill e documentação com a LC 214

## O que mudou

- **Busca remedida com EC + LC.** O limiar de 0,15 ficou.
  - Fora do tema, a maior relevância subiu de 0,130 para 0,138: "campeonato brasileiro de futebol" encosta num artigo da LC.
  - Dentro do tema, a menor é 0,248.
  - Um teste novo vigia a folga (`test_threshold_still_separates_the_groups_with_margin`). Se o corpus crescer e ela sumir, a suíte avisa antes de alguém notar uma resposta errada.
- **6 consultas da LC entram como teste:** educação (60%), cesta básica, Imposto Seletivo sobre minerais, advogados (30%), dispositivos médicos e veículos.
- **Skill:**
  - o corpus agora inclui os capítulos da LC 214, e os Anexos ficam fora;
  - a LC usa as siglas IBS e CBS, mas a EC e a CF não: a sigla sozinha acha a LC, nunca a Constituição;
  - a tabela ganhou cesta básica, reduções de 30% e 60% e alíquotas do IS;
  - duas regras novas: texto que remete a um Anexo não é completado de memória, e, na LC, o que vale para "já está valendo" é a data de **efeitos**, não a de vigor.
- **README:** a decisão de corpus e os limites (capítulos parciais, LC 227, vigor × efeitos, siglas).
- **Diagrama do corpus:** uma seção nova com a LC 214 como segunda fonte.

## Como rodar

```
uv run pytest tests/test_search_real.py tests/test_skill.py -v
uv run python client/taxlaw_client.py buscar "reduzidas em 30% profissionais"
uv run python client/taxlaw_client.py obter LC214.art125 --data 2026-06-01
```

No Claude Code: `/consultar-reforma-tributaria a cesta básica tem alíquota zero desde quando?`

## O que observar

- **Recalibrar não é só trocar um número.** O corpus cresceu 33%, o idf de cada termo mudou, e as duas pontas se moveram. O valor do limiar continuou o mesmo, mas agora a folga está medida e vigiada por teste.
- **Uma regra da skill virou meia-verdade.** "A EC não usa siglas" continuava certo, mas "a sigla sozinha não acha nada" deixou de ser, com a LC no corpus. Foi o teste da skill que acusou, no 13b. Sem ele, a skill afirmaria algo falso ao modelo.
- **A pergunta da cesta básica agora tem duas metades.** A EC (art. 8º) manda a lei complementar definir os produtos, e a LC (art. 125) zera as alíquotas dos produtos "relacionados no Anexo I". A resposta certa cita as duas e diz que a lista do Anexo não está no corpus.

## Pergunta de previsão

Com a skill nova, pergunte "a cesta básica tem alíquota zero desde quando?". Qual data o modelo deve dar: 2025-01-16 (vigor da LC), 2026-01-01 (efeitos) ou uma data de cobrança efetiva? O que a skill manda dizer sobre a diferença, e o que fica de fora do corpus?

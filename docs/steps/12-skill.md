# Passo 12: a skill que usa o server (critério 3)

## O que mudou

- **`.claude/skills/consultar-reforma-tributaria/SKILL.md`** (73 linhas). O Claude Code carrega só o frontmatter (`name` e `description`, com os gatilhos). O corpo entra no contexto quando a conversa casa com a descrição, ou quando o usuário digita `/consultar-reforma-tributaria`.
- **As regras da spec (seção 8):**
  - data de referência sempre explícita;
  - `buscar` → escolher → `obter` antes de citar;
  - formato de resposta citada;
  - os "não sei" como resposta;
  - o texto da norma é citação;
  - CPF/CNPJ fora das ferramentas.
- **O que a primeira consulta real (passo 10) acrescentou:**
  - **A tabela "usuário diz → busque".** "IBS" e "CBS" sozinhos não acham nada, porque a EC não usa siglas. "imposto sobre bens e serviços" acha o art. 156-A.
  - **A regra "confira de qual tributo é o dispositivo".** "Não integrará sua própria base de cálculo" aparece no IS, no IBS e na CBS. Um inciso não diz o tributo; o pai diz.
  - **Efeito não é cobrança.** Um dispositivo pode produzir efeitos antes de o tributo ser cobrado. A cobrança segue o ADCT, arts. 124 a 137.
- **`tests/test_skill.py`** confere a forma, não o comportamento do modelo, que é assunto do P3:
  - o frontmatter e os gatilhos;
  - menos de 100 linhas;
  - toda ferramenta e todo campo citados existem no server real;
  - a tabela de expressões acha o dispositivo-âncora no corpus;
  - o exemplo das três datas bate com `obter_dispositivo`.

## Como rodar

```
uv run pytest tests/test_skill.py -v
```

No Claude Code (a pasta `.claude/skills/` é nova: rode `/reload-skills` ou reinicie a sessão):

1. Em `/skills`, confira que `consultar-reforma-tributaria` aparece.
2. **Com a skill:** pergunte "A CBS já está valendo?", sem data e com a sigla. Confira:
   - se a skill foi carregada;
   - se a busca usou "contribuição sobre bens e serviços";
   - se `data_referencia` foi passada;
   - se a resposta separa produzir efeitos de ser cobrada.
3. **Sem a skill:** compare com a consulta do passo 10, feita sem ela (`docs/diagramas/bloco-3-server.md`), ou repita a pergunta numa sessão em que a skill esteja desligada.

## O que observar

- **Engenharia de contexto.** As 73 linhas só custam contexto quando o assunto aparece. A `description` é o que fica sempre carregado, e é ela que decide se a skill entra.
- **Prompt melhora a taxa de acerto; o harness decide o que acontece no erro** (lição do P1).
  - Quem garante a regra de CPF/CNPJ é o hook e o server. A skill só explica ao modelo como responder.
  - Quem garante "não encontrei" é o limiar da busca. A skill só pede que o modelo não preencha de memória.
- **O teste prende a skill ao código.** Se um campo do server mudar de nome, ou o corpus deixar de achar uma expressão da tabela, a suíte quebra. A skill não envelhece em silêncio.

## Pergunta de previsão

A `description` diz "Use quando o usuário perguntar sobre ... IBS". Se o usuário perguntar "qual a alíquota do ICMS em 2030?", a skill é carregada? E se for carregada, o que a busca devolve, e o que a skill manda o modelo responder?

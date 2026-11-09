# O que deu errado no P2

São falhas reais, de 2026-11-05 a 2026-11-09, em ordem de gravidade. Quase todas foram achadas **antes** da entrega: num protótipo no scratchpad, num teste de mutação ou numa consulta real. A coluna "Situação" diz o que ficou corrigido e o que continua aberto.

| # | Onde | O que aconteceu | Situação |
|---|---|---|---|
| 1 | SDK do MCP 2.3 | O erro de validação de argumentos repetia o valor recebido (`input_value='…'`). Um CPF mandado no campo `limite` voltaria inteiro na mensagem, antes de a guarda do `tools.py` rodar | Corrigida (passo 10): a guarda roda nos argumentos crus, antes do SDK, e o erro é reescrito só com o nome do campo |
| 2 | `guard.py` | A regex não achava CPF/CNPJ logo depois de uma `/` de URL nem em `cpf-<número>`, porque tratava `/` e letras como continuação do número. Justo o caso do `WebFetch` | Corrigida (passo 11), com teste de URL, slug e regressão no corpus inteiro |
| 3 | Hook | Pela documentação, só o código 2 bloqueia: um script que quebrasse com código 1 deixaria a chamada passar. E o matcher é uma regex sem âncora (`WebSearch` casaria `WebSearchV2`) | Corrigida (passo 11): o hook bloqueia na dúvida, e o matcher tem `^…$` |
| 4 | SDK do MCP 2.3 | Uma chave fora do tipo de retorno sumia do `structuredContent` sem erro, mas ficava no texto. O pydantic aceitava `True` e `"5"` como `limite` | Corrigida (passo 10): todos os campos foram declarados, com um teste que compara texto e estrutura, e os campos são `strict` |
| 5 | Gate do Meister | O gate importava `taxlaw` do repositório principal, e não do worktree. O "reparo" automático enfiou `sys.path` no teste para fazê-lo passar | O contorno foi removido à mão. O Meister foi corrigido para o caminho padrão; a ordem install → Python com `gate.commands` ficou como pendência relatada |
| 6 | `effects` | No protótipo: o nível de cada revogação do art. 22 era detectado pela contagem de pontos; peças citadas só como contexto eram revogadas inteiras; um inciso de vigência não reconhecido caía num padrão em silêncio | Corrigidas antes do plano (passo 06) |
| 7 | Spec | Três "fatos" errados: o exemplo de versões do art. 156-A, § 1º (era o inciso IX); "o pai sempre existe" (há ancestrais omitidos); `CF.art195` na estrutura mínima (o caput é só uma linha de pontos) | Corrigidas ao conferir no dado real |
| 8 | Busca | A pontuação BM25 absoluta não separava consultas do tema das de fora. Siglas e palavras que a EC não usa não acham nada; "x" acha o inciso X; o Imposto Seletivo vem à frente do IBS com a mesma frase | Mitigada: limiar relativo (0,15) e tabela de expressões na skill. O ranking continua aberto (P3) |
| 9 | Coleta | O Planalto derruba clientes automatizados. O PDF e o "salvar como" do navegador geravam cópias modificadas da página | Contornada: `fetch(location.href)` no Console, com sha256 no `.meta.json`. Atualizar o corpus continua manual |
| 10 | Testes de mutação | Restaurar um arquivo no mesmo segundo, com o mesmo tamanho, fez o Python usar um `.pyc` velho: o teste rodava contra o mutante | Corrigida no processo: o `__pycache__` é apagado depois de cada mutação |
| 11 | Ambiente | O `.mcp.json` novo só foi lido depois de reiniciar a sessão; a skill nova só depois de `/reload-skills`; e a skill não entrou sozinha, precisou de `/nome`. Num teste manual, dois comandos colados numa linha mandaram ao hook a saída do primeiro, e não o JSON | Registradas nas notas dos passos 10 a 12. O carregamento automático da skill fica para medir no P3 |

## O que cada uma ensina

1. **O erro também é um canal de saída.** Validar a entrada não basta se a mensagem de erro devolve a entrada. A guarda precisa estar antes de qualquer código que possa ecoar o valor, inclusive o da biblioteca.
2. **Fronteiras de regex são política, não detalhe.** "Não colado a outro número" virou "não depois de uma barra", e isso abriu um buraco exatamente onde as URLs passam. O teste certo usa o formato real de cada ferramenta (URL do `WebFetch`, query do `WebSearch`).
3. **Leia o contrato de quem chama o seu código.** O que bloqueia, o que é regex e o que tem âncora estão na documentação do Claude Code, e não no nosso código. A defesa é bloquear na dúvida (fail closed).
4. **Biblioteca que "ajuda" em silêncio é risco.** Coerção de tipo e descarte de campos não dão erro. Só um teste que compara as duas saídas (texto e estrutura) pega isso.
5. **Reparo automático otimiza para o teste passar.** O gate do Meister "consertou" um problema de ambiente mexendo no teste. Por isso, depois de cada orchestrate, o código entregue foi comparado arquivo a arquivo com o protótipo, e `sys.path` em testes virou um sinal de alerta.
6. **Protótipo no dado real antes do plano.** Os bugs do `effects` e os erros da spec apareceram ao rodar o protótipo no HTML real, e não ao ler a lei.

O padrão comum, o mesmo do P1: **o prompt (a skill) faz o modelo acertar mais vezes; o harness (o hook, a guarda antes do SDK, o limiar da busca) decide o que acontece quando ele erra.** A diferença do P2 é que quase tudo foi achado antes de chegar ao usuário, porque cada passo teve protótipo, mutação e uma consulta real.

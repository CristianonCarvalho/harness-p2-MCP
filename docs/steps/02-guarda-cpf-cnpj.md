# Passo 02: guarda de CPF/CNPJ

## O que mudou

- `src/taxlaw/guard.py`: `find_taxpayer_ids(text)` acha CPF, CNPJ numérico e CNPJ alfanumérico num texto e devolve só o tipo e a posição (`Finding`). `describe_findings` monta a mensagem sem nenhum número. Também calcula os dígitos verificadores (`cpf_check_digits`, `cnpj_check_digits`).
- `src/taxlaw/synthetic_ids.py`: `make_cpf` e `make_cnpj` geram números válidos a partir de bases inventadas, em tempo de execução. Nenhum CPF/CNPJ válido fica escrito no repositório.
- É a peça que o hook (passo 11) e o server (passo 10) vão chamar: uma guarda só, no ponto por onde tudo passa.

## Como rodar

    uv run pytest tests/test_check_digits.py tests/test_guard.py -v

Para brincar no terminal:

    uv run python -c "from taxlaw.synthetic_ids import make_cnpj; from taxlaw.guard import find_taxpayer_ids, describe_findings; t = 'empresa ' + make_cnpj('ABCDEFGH0001', formatted=True); f = find_taxpayer_ids(t); print(f, describe_findings(f))"

## O que observar

- **Regex não basta:** a regex só acha candidatos. O que separa um CPF de um número de processo é o dígito verificador. Por isso "Processo 0001234-56.2023.8.26.0100" não vira achado.
- **CNPJ alfanumérico:** cada caractere vale o código ASCII menos 48 ('A' = 17). Para dígitos isso dá o próprio dígito, então o CNPJ numérico de sempre continua com os mesmos DVs. Conferido no exemplo resolvido da RFB ("Perguntas & Respostas: CNPJ alfanumérico", pergunta 14).
- **Fronteiras:** `1.` + um CPF formatado não é achado, porque o número continua para a esquerda. Já um CPF seguido de ponto final é.
- **`[0-9]` e não `\d`:** em Python, `\d` casa dígitos de outros alfabetos (árabe, largura total), e `ord(c) - 48` daria lixo.
- **O número nunca sai da guarda:** `Finding` guarda tipo e posição; a mensagem diz "1 CPF e 1 CNPJ (números omitidos)". Se o motivo do bloqueio repetisse o número, o log do hook vazaria exatamente o que ele deveria barrar.
- **Repetidos:** `000.000.000-00` tem DV "válido" pela conta, mas é descartado.

## Pergunta de previsão

O resto 0 e o resto 1 viram o mesmo DV (0). Então trocar um único dígito da base sempre muda o DV? Pense num caso em que a soma muda de resto 0 para resto 1. E o que isso diz sobre usar o DV como prova de que o número é "real"?

# Correções depois do passo HTTP

## O que mudou

- **As descrições das ferramentas agora citam a LC 214.** O modelo decide se e como usar uma ferramenta pela descrição dela, e a de `buscar_dispositivos` ainda dizia só "(EC 132/2023)". O 13c tinha atualizado a skill, mas não as descrições do server.
  - A descrição de `buscar_dispositivos` lista o corpus (EC 132, CF/ADCT, os capítulos da LC 214) e diz que os Anexos não estão nele.
  - A descrição do parâmetro `consulta` cita as duas normas.
  - A de `obter_dispositivo` fala em "artigo da EC 132/2023 ou LC 214/2025".
- **Um teste amarra as descrições ao corpus.** `test_descriptions_name_every_norm_in_the_corpus` falha se o corpus ganhar uma fonte nova sem que as descrições a mencionem.
- **O cliente diz quando não há server.** Com `--url`, uma conexão recusada virava "não consegui falar com o server (ExceptionGroup)". Agora é "não há server escutando em <url>". Foi o que aconteceu no teste manual: o cliente rodou antes de o server terminar de subir.
- **Um teste intermitente foi corrigido.** O `test_body_over_the_limit_is_413` mandava 64 KB de verdade, e às vezes o server respondia 413 e fechava antes de o cliente terminar de enviar, o que virava um "connection reset". Agora o teste manda só os cabeçalhos, com `Content-Length` acima do limite: o SDK decide pelo cabeçalho, sem corrida.

## Como rodar

```
uv run pytest tests/test_server.py tests/test_http.py -v
uv run python client/taxlaw_client.py ferramentas
uv run python client/taxlaw_client.py --url http://127.0.0.1:8999/mcp ferramentas   # sem server: "não há server escutando em ..."
```

## O que observar

- **Três lugares contam ao modelo o que existe no corpus:** a skill, as descrições das ferramentas e o próprio retorno. Atualizar um e esquecer outro deixa o modelo com informação contraditória. O teste novo prende as descrições ao corpus, como o `test_skill` já prendia a skill.
- **Mensagem de erro é interface.** "ExceptionGroup" diz o que quebrou no código; "não há server escutando em ..." diz o que fazer.
- **Um teste intermitente é um defeito.** Ele só aparecia de vez em quando, numa máquina com carga, e foi pego porque a suíte rodou várias vezes seguidas.

## Pergunta de previsão

Se você mudar o corpus para incluir outro capítulo da LC 214 (o de combustíveis, por exemplo) sem mexer nas descrições, o teste novo pega? Por quê? E o que pegaria esse esquecimento?

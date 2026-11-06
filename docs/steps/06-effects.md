# Passo 06: effects (datas de vigor e efeitos)

## O que mudou

- `src/taxlaw/ingest/effects.py`, puro como o `structure`:
  - `find_publication_date` lê "publicado no DOU 21.12.2023" na nota da página.
  - `parse_vigencia` interpreta os incisos do **art. 23** e dá uma regra por artigo da EC: arts. 3º e 11 em 2027, arts. 4º e 5º em 2033, os demais na publicação.
  - `parse_revocation_list` e `parse_revocations` leem o **art. 22**: 16 dispositivos revogados em 2027 e 2033.
  - `compute_effects` dá a cada (`id`, `versao`) `vigor_desde` = `efeitos_desde`, `efeitos_ate`, `fundamento`, `fundamento_ate` e `metodo`.
  - `effects_for` junta tudo para o build (passo 07).
- 23 testes com registros sintéticos e 9 contra o corpus real.

## Como rodar

    uv run pytest tests/test_effects.py tests/test_effects_real.py -v

Para ver as três versões do inciso IX:

    uv run python -c "from taxlaw.ingest.structure import *; from taxlaw.ingest.effects import *; h = decode_html(open('corpus/raw/ec132-2023.html','rb').read()); r = parse(h).records; e = effects_for(r, find_publication_date(t for _, t in paragraphs(h))); [print(k[1], v.efeitos_desde, '->', v.efeitos_ate) for k, v in e.by_version.items() if k[0] == 'CF.art156-A.par1.incIX']"

## O que observar

- **A letra da lei corrigiu a spec:** o art. 23 diz "esta Emenda **entra em vigor**: I - em 2027...". A vigência é escalonada, não só os efeitos. Para a EC 132, `vigor_desde` = `efeitos_desde`.
- **Ano sem dia vira 1º de janeiro:** "em 2027" → 2027-01-01, regra escrita no código.
- **Término pela versão seguinte:** o inciso IX vale de 2023-12-21 a 2026-12-31 (art. 1º), de 2027-01-01 a 2032-12-31 (art. 3º) e a partir de 2033-01-01 (art. 4º).
- **Revogação também encerra:** o art. 155, § 3º, alterado em 2023, vale até 2032-12-31 porque o art. 22, II, "a" o revoga em 2033. Sem isso, o server diria "sem término".
- **Contexto não é revogado:** em "158, IV, \"a\"", só a alínea a cai. O inciso IV e a alínea b continuam.
- **"(Revogado)" é uma versão:** o art. 5º republica o ADCT 82, § 2º, como "(Revogado)" a partir de 2033. Essa versão representa o estado depois da revogação e não é encerrada por ela.
- **Nada de regra geral silenciosa:** se um inciso do art. 23 não for entendido, ninguém cai nos "demais". Fica tudo `indeterminado`, com aviso.

## Pergunta de previsão

Com `data_referencia` 2035-01-01, alguém pergunta sobre o art. 155, § 3º, da CF. O registro existe no corpus, com texto e citação. O que o server deve responder: o texto, um "não encontrei", ou outra coisa? Pense em `produz_efeitos_na_data` e em `fundamento_ate`.

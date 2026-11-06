# Passo 05: structure no HTML real

## O que mudou

- `src/taxlaw/ingest/structure.py`, três correções achadas ao rodar no arquivo real:
  1. **Número colado no texto:** `Art. 12.Fica instituído...` (arts. 12 e 17 da EC) agora é reconhecido como artigo.
  2. **`errors` novo em `ParseResult`:** uma âncora `<a name="artN">` sem caput reconhecido, ou com caput de outro número, vira erro. O build (passo 07) aborta com erro.
  3. **Fim do texto:** "Brasília, em <data>" encerra a norma. Assinaturas e o aviso do DOU deixam de gerar aviso.
- `tests/test_structure_real.py`: 10 testes contra `corpus/raw/ec132-2023.html`, conferindo antes o sha256 com o meta.
- `tests/test_structure.py`: o teste da assinatura passou a esperar zero avisos, e há 4 testes sintéticos novos, um para cada caso real.

## Como rodar

    uv run pytest tests/test_structure.py tests/test_structure_real.py -v

## O que observar

- **O bug que o aviso escondia:** antes, `Art. 12.Fica` gerava um aviso só na linha do caput. Mas o parser continuava "dentro" do art. 11, e os 22 filhos do art. 12 eram registrados como `EC132.art11.par...` **sem nenhum aviso**. O teste `test_children_of_art12_are_not_glued_to_art11` fixa isso. Lição: um aviso no ponto do problema não basta quando o erro se propaga para o que vem depois. Por isso a âncora sem caput virou erro, não aviso.
- **Fonte independente:** os textos de `KNOWN` foram comparados com a impressão em PDF da mesma página. O parser e o navegador concordam.
- **A EC repete texto:** o art. 4º republica o art. 156-A, § 1º, IX, e o art. 195, § 17, com o mesmo texto do art. 3º. Só a data de efeito muda (2033 em vez de 2027). A versão importa mesmo com texto idêntico.
- **Números como âncora de regressão:** 487 registros, 23 artigos da EC, 9 dispositivos com várias versões. Se o corpus mudar, esses testes quebram de propósito.

## Pergunta de previsão

O art. 3º da EC tira do inciso IX a menção à contribuição para o PIS, a partir de 2027. Se alguém perguntar ao server, com `data_referencia` 2026-06-01, se o IBS integra a base do PIS, qual versão o server deve citar? E o que muda se a data for 2028-06-01?

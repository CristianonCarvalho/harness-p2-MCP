"""O server como processo filho via stdio, como o Claude Code o usa.

Sobe `python -m taxlaw.server` com o mesmo interpretador da suíte, a partir
de um diretório temporário (o corpus tem de ser achado sem depender do
diretório atual), e conversa com o `Client` oficial do SDK. Nada de rede: o
processo filho só lê `corpus/dispositivos.json`.
"""

import sys
from datetime import date

import anyio

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from taxlaw import tools


def test_stdio_server_speaks_the_stateless_revision_and_matches_tools_py(tmp_path):
    params = StdioServerParameters(command=sys.executable, args=["-m", "taxlaw.server"], cwd=tmp_path)
    ctx = tools.load_context()

    async def main():
        # Teto de tempo: se o processo filho travar, o teste falha em vez de pendurar a suíte.
        with anyio.fail_after(30):
            async with Client(params) as client:
                names = sorted(t.name for t in (await client.list_tools()).tools)
                result = await client.call_tool("obter_dispositivo", {"id": "CF.art156-A.par1.incIX", "data_referencia": "2030-06-01"})
                return client.protocol_version, names, result

    version, names, result = anyio.run(main)

    assert version == "2026-07-28"  # a revisão stateless que o Claude Code também fala (passo 01)
    assert names == ["buscar_dispositivos", "obter_dispositivo"]
    assert result.is_error is False
    # data_referencia explícita: o `today` do processo filho não importa aqui.
    assert result.structured_content == tools.obter_dispositivo(ctx, "CF.art156-A.par1.incIX", "2030-06-01", today=date(2026, 11, 7))
    assert result.structured_content["versao"] == "EC132.art3"

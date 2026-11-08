"""Ponto de entrada do hook PreToolUse (registrado em .claude/settings.json).

A lógica está em `taxlaw.hook`, que é testável como função. Este arquivo só
traduz o resultado em código de saída. Se o pacote não puder ser importado, o
hook bloqueia: um código diferente de 0 e 2 deixaria a chamada passar.
"""

import sys

try:
    from taxlaw.hook import main
except ImportError:
    sys.stderr.write("Chamada bloqueada: o hook do projeto não encontrou o pacote taxlaw (rode `uv sync`).\n")
    sys.exit(2)

sys.exit(main())

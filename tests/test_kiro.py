"""Portabilidade para o Kiro (passo 14, critério 1): o mesmo server, hook e skill.

Nada aqui chama o Kiro (os testes são offline). Confere-se o que o Kiro vai
usar:
- o server fala o handshake `initialize` (o Kiro CLI 3.1 abre com ele,
  revisão 2025-11-25, medido em 2026-11-09), além da revisão stateless que o
  Claude Code usa;
- `.kiro/settings/mcp.json` sobe o mesmo comando do `.mcp.json`;
- o hook do Kiro chama o mesmo script, que bloqueia com o `tool_name` no
  formato do Kiro (`mcp_<server>_<ferramenta>`);
- a skill do Kiro é um link para a do Claude Code: um arquivo só.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import anyio
import pytest

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from taxlaw import tools
from taxlaw.synthetic_ids import make_cpf

ROOT = Path(__file__).resolve().parents[1]
KIRO = ROOT / ".kiro"
CPF = make_cpf("987654321", formatted=True)
TOOLS = ["buscar_dispositivos", "obter_dispositivo"]


def test_server_speaks_the_initialize_handshake_too(tmp_path):
    # mode="legacy": initialize + notifications/initialized, como o Kiro faz.
    params = StdioServerParameters(command=sys.executable, args=["-m", "taxlaw.server"], cwd=tmp_path)

    async def main():
        with anyio.fail_after(30):
            async with Client(params, mode="legacy") as client:
                names = sorted(t.name for t in (await client.list_tools()).tools)
                result = await client.call_tool("obter_dispositivo", {"id": "CF.art156-A.par1.incIX", "data_referencia": "2030-06-01"})
                return client.protocol_version, names, result

    version, names, result = anyio.run(main)
    assert version != "2026-07-28" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", version)
    assert names == TOOLS and result.is_error is False
    expected = tools.obter_dispositivo(tools.load_context(), "CF.art156-A.par1.incIX", "2030-06-01", today=date(2026, 11, 9))
    assert result.structured_content == expected


def test_kiro_mcp_config_runs_the_same_server_as_claude_code():
    kiro = json.loads((KIRO / "settings" / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["taxlaw"]
    claude = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["taxlaw"]
    assert (kiro["command"], kiro["args"]) == (claude["command"], claude["args"])
    assert kiro.get("disabled", False) is False


@pytest.mark.parametrize("tool", TOOLS)
def test_tool_names_fit_kiro_rules(tool):
    # Kiro: id interno mcp_<server>_<ferramenta>, até 64 caracteres, ^[a-zA-Z][a-zA-Z0-9_]*$
    internal = f"mcp_taxlaw_{tool}"
    assert len(internal) <= 64 and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", internal)


def kiro_hooks():
    document = json.loads((KIRO / "hooks" / "block-taxpayer-ids.json").read_text(encoding="utf-8"))
    assert document["version"] == "v1"
    return document["hooks"]


def test_kiro_hooks_cover_the_server_and_the_web():
    hooks = kiro_hooks()
    assert {h["matcher"] for h in hooks} == {"@taxlaw", "web"}
    for hook in hooks:
        assert hook["trigger"] == "PreToolUse" and hook["action"]["type"] == "command"
        assert "hooks/block_taxpayer_ids.py" in hook["action"]["command"]


def test_kiro_hook_command_blocks_with_kiro_tool_name():
    # O Kiro roda hooks de comando na raiz do projeto; qualquer código != 0 bloqueia.
    (hook, *_) = kiro_hooks()
    stdin_text = json.dumps(
        {"hook_event_name": "PreToolUse", "cwd": str(ROOT), "session_id": "sessao-sintetica", "tool_name": "mcp_taxlaw_buscar_dispositivos", "tool_input": {"consulta": f"IBS {CPF}"}}
    )
    done = subprocess.run(["/bin/sh", "-c", hook["action"]["command"]], input=stdin_text, capture_output=True, text=True, cwd=ROOT, env=dict(os.environ), timeout=120)
    assert done.returncode != 0 and "'consulta'" in done.stderr
    assert CPF not in done.stderr and CPF.replace(".", "").replace("-", "") not in done.stderr


def test_kiro_hook_command_allows_clean_call():
    (hook, *_) = kiro_hooks()
    stdin_text = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "mcp_taxlaw_buscar_dispositivos", "tool_input": {"consulta": "zona franca de manaus"}})
    done = subprocess.run(["/bin/sh", "-c", hook["action"]["command"]], input=stdin_text, capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert done.returncode == 0 and done.stdout == ""  # no Kiro, stdout com código 0 iria para o contexto do agente


def test_kiro_skill_is_a_link_to_the_claude_code_skill():
    link = KIRO / "skills" / "consultar-reforma-tributaria"
    assert link.is_symlink()
    assert os.readlink(link) == "../../.claude/skills/consultar-reforma-tributaria"  # relativo: funciona em qualquer clone
    assert link.resolve() == (ROOT / ".claude" / "skills" / "consultar-reforma-tributaria").resolve()
    assert (link / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: consultar-reforma-tributaria\n")

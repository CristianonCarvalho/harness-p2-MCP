"""Testes do hook PreToolUse (passo 11, critério 2).

Três níveis: a função `check`, o script `hooks/block_taxpayer_ids.py` como
processo (JSON no stdin, código de saída e stderr) e o comando exato
registrado em `.claude/settings.json`. Os CPF/CNPJ são gerados em tempo de
execução a partir de bases sintéticas; nenhum número válido fica escrito aqui.
"""

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from taxlaw.guard import find_in_arguments
from taxlaw.hook import ALLOW, BLOCK, INTERNAL_ERROR, UNREADABLE, check, main
from taxlaw.synthetic_ids import make_cnpj, make_cpf

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "block_taxpayer_ids.py"
SETTINGS = ROOT / ".claude" / "settings.json"

CPF = make_cpf("987654321", formatted=True)
CPF_COMPACT = make_cpf("987654321")
CNPJ = make_cnpj("123456780001")
CNPJ_ALNUM = make_cnpj("ABCDEFGH0001", formatted=True)


def payload(tool_name, tool_input):
    """Forma da entrada do PreToolUse (documentação de hooks do Claude Code)."""
    return {
        "session_id": "sessao-sintetica",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/tmp/projeto",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "toolu_sintetico",
    }


def no_number_in(text):
    for number in (CPF, CPF_COMPACT, CNPJ, CNPJ_ALNUM):
        compact = re.sub(r"[./-]", "", number)
        assert number not in text and compact not in text


# ------------------------------------------------------------------ guard.find_in_arguments


@pytest.mark.parametrize(
    ("arguments", "field"),
    [
        ({"query": f"situação cadastral {CPF}"}, "query"),
        ({"url": f"https://exemplo.invalid/consulta?cnpj={CNPJ}", "prompt": "resuma"}, "url"),
        ({"consulta": "ibs", "extra": {"lista": ["ok", CNPJ_ALNUM]}}, "extra.lista[1]"),
        ({CPF_COMPACT: "x"}, "<chave>"),
        ({"extra": {CPF: "x"}}, "extra.<chave>"),
    ],
)
def test_find_in_arguments_names_the_field_without_the_number(arguments, field):
    reason = find_in_arguments(arguments)
    assert reason is not None and reason.endswith(f"no campo '{field}'")
    no_number_in(reason)


def test_find_in_arguments_ignores_clean_and_non_text_values():
    clean = {"consulta": "art. 156-A, processo 12345678901, data 2023-12-21", "limite": 5, "incluir_filhos": True, "data_referencia": None}
    assert find_in_arguments(clean) is None


# ------------------------------------------------------------------ check e main


def test_check_blocks_each_matched_tool_shape():
    assert check(payload("WebSearch", {"query": f"dono do {CPF}"}))
    assert check(payload("WebFetch", {"url": f"https://exemplo.invalid/{CNPJ}", "prompt": "x"}))
    assert check(payload("mcp__taxlaw__buscar_dispositivos", {"consulta": f"IBS {CNPJ_ALNUM}", "limite": 5}))
    assert check(payload("mcp__taxlaw__obter_dispositivo", {"id": "CF.art156-A", "data_referencia": CPF_COMPACT}))


def test_check_allows_clean_call():
    assert check(payload("mcp__taxlaw__buscar_dispositivos", {"consulta": "alíquota do IBS em 2030", "limite": 5})) is None


@pytest.mark.parametrize("bad", [None, [], "texto", {"tool_name": "WebSearch"}, {"tool_input": ["lista"]}, {"tool_input": "texto"}])
def test_unreadable_payload_is_blocked(bad):
    assert check(bad) == UNREADABLE


def run_main(stdin_text):
    err = io.StringIO()
    code = main(io.StringIO(stdin_text), err)
    return code, err.getvalue()


def test_main_exit_codes_and_stderr():
    code, err = run_main(json.dumps(payload("WebSearch", {"query": f"situação {CPF}"})))
    assert code == BLOCK == 2 and "1 CPF" in err and "'query'" in err
    no_number_in(err)
    assert run_main(json.dumps(payload("WebSearch", {"query": "reforma tributária"}))) == (ALLOW, "")


def test_main_blocks_invalid_json():
    code, err = run_main("isto não é json")
    assert code == BLOCK and UNREADABLE in err


def test_main_blocks_on_internal_error(monkeypatch):
    def boom(_):
        raise RuntimeError("falha inesperada")

    monkeypatch.setattr("taxlaw.hook.find_in_arguments", boom)
    code, err = run_main(json.dumps(payload("WebSearch", {"query": "x"})))
    assert code == BLOCK and INTERNAL_ERROR in err  # nunca 1: código 1 deixaria a chamada passar


# ------------------------------------------------------------------ o script como processo


def run_script(stdin_text, cwd):
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text, capture_output=True, text=True, cwd=cwd, timeout=30)


def test_script_blocks_with_exit_2_from_any_directory(tmp_path):
    done = run_script(json.dumps(payload("WebFetch", {"url": f"https://exemplo.invalid/?doc={CNPJ}", "prompt": "x"})), tmp_path)
    assert done.returncode == 2 and done.stdout == ""
    assert "1 CNPJ" in done.stderr
    no_number_in(done.stderr)


def test_script_allows_clean_call(tmp_path):
    done = run_script(json.dumps(payload("mcp__taxlaw__obter_dispositivo", {"id": "CF.art156-A"})), tmp_path)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")


# ------------------------------------------------------------------ .claude/settings.json


def settings_hook():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    (entry,) = settings["hooks"]["PreToolUse"]
    (hook,) = entry["hooks"]
    return entry["matcher"], hook


@pytest.mark.parametrize(
    ("tool_name", "matched"),
    [
        ("mcp__taxlaw__buscar_dispositivos", True),
        ("mcp__taxlaw__obter_dispositivo", True),
        ("WebSearch", True),
        ("WebFetch", True),
        ("Bash", False),
        ("Read", False),
        ("mcp__eco__eco", False),
        ("mcp__outro__WebSearch", False),
        ("WebSearchV2", False),
        ("websearch", False),
    ],
)
def test_matcher_selects_exactly_the_guarded_tools(tool_name, matched):
    # O Claude Code testa o matcher como regex JavaScript sem âncora (RegExp.test);
    # re.search tem a mesma semântica para este padrão. As âncoras ^...$ é que
    # impedem "WebSearch" de casar dentro de outro nome.
    matcher, _ = settings_hook()
    assert bool(re.search(matcher, tool_name)) is matched


def test_registered_command_runs_the_hook_and_blocks(tmp_path):
    # Roda o comando exatamente como está no settings.json, pelo shell, com a
    # variável que o Claude Code exporta para hooks.
    _, hook = settings_hook()
    assert hook["type"] == "command" and hook["timeout"] == 30
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)}
    stdin_text = json.dumps(payload("mcp__taxlaw__buscar_dispositivos", {"consulta": f"IBS {CPF}"}))
    done = subprocess.run(["/bin/sh", "-c", hook["command"]], input=stdin_text, capture_output=True, text=True, cwd=tmp_path, env=env, timeout=120)
    assert done.returncode == 2 and "'consulta'" in done.stderr
    no_number_in(done.stderr)

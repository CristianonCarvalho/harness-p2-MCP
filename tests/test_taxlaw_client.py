"""Testes do cliente MCP de terminal (`client/taxlaw_client.py`).

O cliente fica fora do pacote `taxlaw` (como o `echo/`), então é carregado
pelo caminho do arquivo. Os testes de ponta a ponta sobem o server de verdade
via stdio com o próprio Python da suíte (`--server`), sem depender do `uv`;
um teste separado usa o comando do `.mcp.json`. CPF/CNPJ são sintéticos,
gerados em tempo de execução.
"""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from taxlaw.synthetic_ids import make_cpf

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "client" / "taxlaw_client.py"
_spec = importlib.util.spec_from_file_location("taxlaw_client", SCRIPT)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

SERVER = f"{sys.executable} -m taxlaw.server"


def run(capsys, *argv):
    code = cli.main(["--server", SERVER, *argv])
    out, err = capsys.readouterr()
    return code, out, err


# ------------------------------------------------------------------ formatação (sem server)

EFFECTS = {"desde": "2027-01-01", "ate": "2032-12-31", "fundamento": "EC 132/2023, art. 23, I", "metodo": "automatico"}


@pytest.mark.parametrize(("value", "word"), [(True, "sim"), (False, "não"), (None, "não se sabe")])
def test_three_effect_states(value, word):
    data = {"encontrado": True, "id": "X", "citacao": "X", "texto": "t", "efeitos": {**EFFECTS, "produz_efeitos_na_data": value}}
    assert f"produz efeitos na data: {word}" in cli.render_dispositivo(data)


def test_device_with_observation_truncation_and_child_without_text():
    data = {
        "encontrado": True, "id": "CF.art1", "citacao": "CF, art. 1º", "texto": "Art. 1º …", "versao": "EC132.art1",
        "origem": "EC 132/2023, art. 1º", "alteracao": "alterado", "data_referencia": "2030-06-01",
        "filhos": [{"citacao": "CF, art. 1º, I", "texto": "I - um;"}, {"citacao": "CF, art. 1º, II", "texto": None}],
        "efeitos": {**EFFECTS, "produz_efeitos_na_data": False},
        "outras_versoes": [{"versao": "EC132.art4", "efeitos": {"desde": "2033-01-01", "ate": None}}],
        "observacao": "redação anterior não incluída no corpus", "truncado": True,
        "fonte_url": "https://exemplo.invalid", "corpus": {"versao": "0123456789abcdef" * 4, "coletado_em": "2026-11-06"},
    }
    text = cli.render_dispositivo(data)
    assert "CF, art. 1º, I: I - um;" in text
    assert "CF, art. 1º, II: (não coube no teto; peça este id)" in text
    assert "outras versões: EC132.art4 (desde 2033-01-01)" in text
    assert "observação: redação anterior não incluída no corpus" in text and "truncado" in text
    assert "01234567…" in text and "012345678" not in text  # só 8 caracteres do hash


def test_not_found_messages():
    assert cli.render_busca({"encontrado": False, "consulta": "bolo", "motivo": "abaixo do limiar"}).endswith("Nada encontrado: abaixo do limiar")
    assert cli.render_dispositivo({"encontrado": False, "id": "XX", "motivo": "id inexistente no corpus"}) == "Não encontrado: XX (id inexistente no corpus)"


def test_missing_fields_become_dash_not_exceptions():
    text = cli.render_busca({"encontrado": True, "resultados": [{"id": "X"}]})
    assert "relevância —" in text and "efeitos: —" in text
    assert cli.render_dispositivo({"encontrado": True}).startswith("—   [—]")


# ------------------------------------------------------------------ configuração


def test_server_params_from_the_real_mcp_json():
    params = cli.server_params(ROOT / ".mcp.json")
    assert (params.command, params.args) == ("uv", ["run", "--quiet", "python", "-m", "taxlaw.server"])
    assert Path(params.cwd) == ROOT


def test_server_override_is_split_like_a_shell():
    params = cli.server_params(ROOT / ".mcp.json", override='python -m "taxlaw.server"')
    assert (params.command, params.args) == ("python", ["-m", "taxlaw.server"])


@pytest.mark.parametrize("content", [None, "{nao e json", '{"mcpServers": {"eco": {"command": "x"}}}'])
def test_bad_configuration_is_client_error_code_2(tmp_path, capsys, content):
    config = tmp_path / ".mcp.json"
    if content is not None:
        config.write_text(content, encoding="utf-8")
    assert cli.main(["--mcp-json", str(config), "ferramentas"]) == 2
    assert capsys.readouterr().err.startswith("erro: ")


# ------------------------------------------------------------------ de ponta a ponta (server real via stdio)


def test_tools_lists_both(capsys):
    code, out, _ = run(capsys, "ferramentas")
    assert code == 0 and "buscar_dispositivos:" in out and "obter_dispositivo:" in out and "consulta (obrigatório)" in out


def test_search_real(capsys):
    code, out, _ = run(capsys, "buscar", "zona franca de manaus", "--limite", "2")
    assert code == 0 and "[ADCT.art126.incIII.alia]" in out and "relevância 0," in out


def test_get_real_with_date(capsys):
    code, out, _ = run(capsys, "obter", "CF.art156-A.par1.incIX", "--data", "2030-06-01")
    assert code == 0 and "versão EC132.art3" in out and "produz efeitos na data: sim" in out


def test_json_is_the_structured_content(capsys):
    code, out, _ = run(capsys, "--json", "obter", "CF.art155.par3", "--data", "2033-01-01", "--sem-filhos")
    data = json.loads(out)
    assert code == 0 and data["filhos"] == [] and data["observacao"].startswith("revogado a partir de 2033-01-01")
    assert data["data_referencia"] == "2033-01-01"


def test_not_found_is_exit_0(capsys):
    code, out, _ = run(capsys, "buscar", "receita de bolo de chocolate")
    assert code == 0 and "Nada encontrado:" in out


def test_server_error_is_exit_1_with_the_server_message(capsys):
    code, out, err = run(capsys, "buscar", "ibs", "--limite", "11")
    assert code == 1 and out == "" and json.loads(err)["erro"] == "entrada_invalida"


def test_taxpayer_id_is_blocked_by_the_server_without_echo(capsys):
    # Fora do Claude Code não há hook: quem bloqueia é o server (camada 2).
    number = make_cpf("987654321", formatted=True)
    code, out, err = run(capsys, "buscar", f"situação do contribuinte {number}")
    assert code == 1 and json.loads(err)["erro"] == "dados_de_contribuinte"
    for shown in (out, err):
        assert number not in shown and number.replace(".", "").replace("-", "") not in shown


def test_server_that_does_not_start_is_exit_2(capsys):
    assert cli.main(["--server", "comando-que-nao-existe-xyz", "ferramentas"]) == 2
    assert "não consegui falar com o server" in capsys.readouterr().err


def test_shared_mcp_json_command_works(capsys):
    # Sem --server: o mesmo comando do Claude Code (uv run ... taxlaw.server).
    assert cli.main(["ferramentas"]) == 0
    assert "obter_dispositivo:" in capsys.readouterr().out


# ------------------------------------------------------------------ desacoplamento


def test_client_does_not_import_taxlaw():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert "taxlaw" not in modules and "mcp" in modules


def test_runs_as_a_script_from_another_directory(tmp_path):
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--server", SERVER, "obter", "CF.art195.incV"],
        capture_output=True, text=True, cwd=tmp_path, timeout=60,
    )
    assert done.returncode == 0 and "CF, art. 195, V" in done.stdout and done.stderr == ""


# ------------------------------------------------------------------ argumentos enviados


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["buscar", "ibs"], ("buscar_dispositivos", {"consulta": "ibs"})),
        (["buscar", "ibs", "--limite", "3", "--data", "2030-06-01"], ("buscar_dispositivos", {"consulta": "ibs", "limite": 3, "data_referencia": "2030-06-01"})),
        (["obter", "CF.art1"], ("obter_dispositivo", {"id": "CF.art1"})),
        (["obter", "CF.art1", "--sem-filhos"], ("obter_dispositivo", {"id": "CF.art1", "incluir_filhos": False})),
    ],
)
def test_only_given_options_are_sent_defaults_are_the_servers(argv, expected):
    assert cli._arguments(cli._parser().parse_args(argv)) == expected


def test_json_output_keeps_accents_literal(capsys):
    code, out, _ = run(capsys, "--json", "obter", "CF.art155.par3", "--sem-filhos")
    assert code == 0 and '"citacao": "CF, art. 155, § 3º"' in out

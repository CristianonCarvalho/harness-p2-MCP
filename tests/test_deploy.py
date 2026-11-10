"""Os arquivos de deploy da VPS (spec 2026-11-10-deploy-vps-design).

Offline e só de leitura: nada de daemon Docker nem de rede. Estes testes
prendem as decisões de segurança do deploy, para que ninguém as afrouxe sem
perceber: porta só em 127.0.0.1, container endurecido, segredos fora do git e
da imagem, nginx sem logar o token, e a mesma porta e o mesmo domínio nos
três arquivos. O build de verdade foi verificado à mão (Mac e VPS).
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "mcpreforma.cristianocarvalho.cloud"
HOST_PORT = 8020


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def compose_service() -> dict:
    return yaml.safe_load(read("compose.yaml"))["services"]["taxlaw"]


def dockerfile_instructions() -> list[str]:
    """Instruções do Dockerfile, com as continuações (\\) juntadas e sem comentários."""
    text = re.sub(r"\\\n\s*", " ", read("Dockerfile"))
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


# ------------------------------------------------------------------ compose


def test_compose_publishes_only_on_localhost():
    assert compose_service()["ports"] == [f"127.0.0.1:{HOST_PORT}:8000"]


def test_compose_reads_the_token_from_env_file_and_restarts():
    service = compose_service()
    assert service["env_file"] == ".env"
    assert service["restart"] == "unless-stopped"
    assert "TAXLAW_HTTP_TOKEN" not in str(service.get("environment", {}))  # o token não fica no compose


def test_compose_is_hardened():
    service = compose_service()
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["mem_limit"] and service["cpus"]


def test_compose_default_allowed_host_is_the_domain():
    assert compose_service()["environment"]["TAXLAW_ALLOWED_HOST"] == f"${{TAXLAW_ALLOWED_HOST:-{DOMAIN}}}"


# ------------------------------------------------------------------ Dockerfile


def test_dockerfile_runs_as_non_root():
    users = [line.split()[1] for line in dockerfile_instructions() if line.startswith("USER ")]
    assert users and users[-1] not in {"root", "0"}


def test_dockerfile_installs_the_locked_runtime_only():
    assert any(line == "RUN uv sync --frozen --no-dev" for line in dockerfile_instructions())


def test_dockerfile_copies_only_what_it_serves():
    copies = [line for line in dockerfile_instructions() if line.startswith("COPY ")]
    assert not any(re.fullmatch(r"COPY \. \S+", line) for line in copies), "COPY . copiaria tudo, até segredos"
    assert not any("corpus/raw" in line for line in copies)
    assert "COPY corpus/dispositivos.json ./corpus/dispositivos.json" in copies


def test_dockerfile_starts_the_http_server_with_allowed_host():
    instructions = dockerfile_instructions()
    cmd = next(line for line in reversed(instructions) if line.startswith("CMD "))
    assert "-m taxlaw.http" in cmd and "--allowed-host" in cmd and "--port 8000" in cmd
    assert f"ENV TAXLAW_ALLOWED_HOST={DOMAIN}" in instructions


def test_dockerfile_pins_the_uv_image():
    assert re.search(r"^FROM ghcr\.io/astral-sh/uv:\d+\.\d+\.\d+ AS uv$", "\n".join(dockerfile_instructions()), re.MULTILINE)


# ------------------------------------------------------------------ segredos


def test_dockerignore_keeps_secrets_and_bulk_out_of_the_image():
    entries = {line.strip() for line in read(".dockerignore").splitlines() if line.strip() and not line.startswith("#")}
    assert {".env", ".git", "tests/", "corpus/raw/"} <= entries


def test_env_is_gitignored_and_example_has_no_value():
    assert ".env" in [line.strip() for line in read(".gitignore").splitlines()]
    values = [line for line in read(".env.example").splitlines() if line.startswith("TAXLAW_HTTP_TOKEN=")]
    assert values == ["TAXLAW_HTTP_TOKEN="]


def test_no_token_written_in_deploy_files():
    # Um token gerado por token_urlsafe(32) tem 43 caracteres de [A-Za-z0-9_-].
    for path in [ROOT / "compose.yaml", ROOT / "Dockerfile", ROOT / ".env.example", *sorted((ROOT / "deploy").iterdir())]:
        assert not re.search(r"Bearer\s+[A-Za-z0-9_-]{20,}|TAXLAW_HTTP_TOKEN=[A-Za-z0-9_-]{20,}", path.read_text(encoding="utf-8")), path


# ------------------------------------------------------------------ nginx


def test_nginx_site_proxies_to_the_container_with_host_and_limits():
    site = read("deploy/nginx-mcpreforma.conf")
    assert f"server_name {DOMAIN};" in site
    assert f"proxy_pass http://127.0.0.1:{HOST_PORT};" in site
    assert "proxy_set_header Host $host;" in site  # o server confere o Host
    assert "limit_req zone=mcpreforma" in site and "limit_req_status 429;" in site
    assert "client_max_body_size 64k;" in site


def test_rate_limit_zone_is_defined_separately_for_the_http_block():
    # limit_req_zone só vale no bloco http: fica num arquivo próprio de conf.d.
    zone = read("deploy/nginx-mcpreforma-ratelimit.conf")
    assert re.search(r"^limit_req_zone \$binary_remote_addr zone=mcpreforma:\d+m rate=\d+r/s;$", zone, re.MULTILINE)
    assert "limit_req_zone" not in read("deploy/nginx-mcpreforma.conf")


def test_nginx_never_logs_the_authorization_header():
    for name in ("deploy/nginx-mcpreforma.conf", "deploy/nginx-mcpreforma-ratelimit.conf"):
        assert "$http_authorization" not in read(name), name


# ------------------------------------------------------------------ documentação


def test_deploy_guide_installs_zone_before_site_and_never_prints_the_token():
    guide = read("docs/deploy.md")
    assert guide.index("mcpreforma-ratelimit.conf") < guide.index("sites-enabled")
    assert "certbot --nginx -d " + DOMAIN in guide
    assert "umask 077" in guide
    assert not re.search(r"cat\s+\S*\.env\b", guide), "o roteiro não deve imprimir o .env na tela"

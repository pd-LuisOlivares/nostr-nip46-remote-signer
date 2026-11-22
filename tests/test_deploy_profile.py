"""Instalacion oficial (D-18, D-20): perfil de evaluacion `deploy/demo.env`, reenvio de variables en `compose.yaml`, coherencia con el README y puertos sin choques.

Deterministas: sin red y sin necesitar el demonio de Docker (el CLI solo se usa para `compose config`, que no crea nada; se omite si no esta).
Estas pruebas NO demuestran interoperabilidad con Stacker News.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yaml"
FORWARDED = ("SIGNER_WINDOW_S", "SECRET_TTL_S", "CONNECTION_TTL_S", "MAX_REQUESTS", "MAX_PENDING", "COOKIE_SECURE", "SIGNER_MODE", "REQUESTS_PER_MIN")
DEMO = ROOT / "deploy" / "demo.env"
README = ROOT / "README.md"
DEMO_COMMAND = "docker compose --env-file deploy/demo.env -p nip46-evaluacion up --build -d"
DEMO_KEYS = {"APP_IMAGE", "APP_PORT", "ADMIN_USERNAME", "ADMIN_PASSWORD", "JWT_TTL_S", "SIGNER_MODE", "RELAY_URL", "RELAY_TLS_GROUPS", "SERVICE_ORIGIN"}
MANUAL = ROOT / "lab" / "manual" / "manual.env"
MANUAL_COMPOSE = ROOT / "lab" / "manual" / "compose.manual.yaml"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


# ------------------------------------------------------------------------------------------------ compose.yaml
def test_compose_forwards_every_limit_and_never_the_insecure_relay_switch_or_a_password_file():
    text = COMPOSE.read_text(encoding="utf-8")
    for name in FORWARDED + ("APPROVAL_TTL_S", "MAX_SIGNATURES", "SESSION_TTL_S", "JWT_TTL_S", "RELAY_URL", "RELAY_TLS_GROUPS", "SERVICE_ORIGIN", "ALLOWED_HOSTS"):
        assert f"{name}: ${{{name}:-}}" in text, name  # vacio = valor por defecto de app/config.py
    for forbidden in ("RELAY_ALLOW_INSECURE: ", "ADMIN_PASSWORD_FILE: ", "0.0.0.0:", "privileged", "network_mode"):
        assert forbidden not in text.replace("# A PROPOSITO", "#"), forbidden
    assert '"127.0.0.1:${APP_PORT:-8000}:8000"' in text and "DATABASE_PATH: /data/nip46.db" in text
    assert "read_only: true" in text and "cap_drop:" in text and "no-new-privileges:true" in text


def test_every_variable_the_official_profile_sets_reaches_the_container():
    text = COMPOSE.read_text(encoding="utf-8")
    for key in read_env(DEMO):
        if key not in ("APP_PORT", "APP_IMAGE"):
            assert f"{key}: ${{{key}:-}}" in text, key


# ------------------------------------------------------------------------------------------------ perfil de evaluacion (instalacion oficial)
def test_the_demo_profile_has_exactly_the_authorized_values_and_a_policy_valid_unique_password() -> None:
    from app.security.passwords import validate_new_password

    values = read_env(DEMO)
    assert set(values) == DEMO_KEYS
    assert {k: v for k, v in values.items() if k != "ADMIN_PASSWORD"} == {
        "APP_IMAGE": "nostr-nip46-remote-signer:evaluation", "APP_PORT": "8000", "ADMIN_USERNAME": "evaluador", "JWT_TTL_S": "3600", "SIGNER_MODE": "continuous",
        "RELAY_URL": "wss://relay.primal.net", "RELAY_TLS_GROUPS": "X25519", "SERVICE_ORIGIN": "https://stacker.news"}
    password = values["ADMIN_PASSWORD"]
    assert len(password) >= 20 and re.fullmatch(r"[A-Za-z0-9-]+", password)  # sin caracteres que el formato de .env o la terminal interpreten
    validate_new_password(values["ADMIN_USERNAME"], password)  # la misma politica que aplica la aplicacion
    assert values["APP_IMAGE"] != "nostr-nip46-remote-signer:dev"  # no pisa la imagen por defecto de otras copias del repositorio
    assert password not in (ROOT / ".env.example").read_text(encoding="utf-8")  # la contrasena publica no se reutiliza en ningun otro archivo de configuracion


def test_the_demo_profile_contains_no_nostr_keys_tokens_uris_or_extra_secrets() -> None:
    text = DEMO.read_text(encoding="utf-8")
    assert not re.search(r"nsec1|bunker://|[0-9a-f]{64}", text, re.IGNORECASE)  # ni claves ni URI ni cadenas hexadecimales de 32 bytes, tampoco en los comentarios
    assert not re.search(r"PRIVATE|TOKEN|JWT_SECRET|RELAY_ALLOW_INSECURE|ADMIN_PASSWORD_FILE", "\n".join(k for k in read_env(DEMO)), re.IGNORECASE)  # ninguna variable de ese tipo
    assert [k for k in read_env(DEMO) if re.search("PASS|SECRET|KEY", k)] == ["ADMIN_PASSWORD"]  # la unica variable sensible, y publica a proposito
    assert "PUBLICA A PROPOSITO" in text and "No la use en produccion" in text  # el aviso de uso exclusivamente local esta en el propio archivo


def test_the_demo_profile_is_valid_for_the_application_continuous_and_creates_a_working_administrator(tmp_path: Path) -> None:
    from app.security.passwords import PasswordService
    from app.services.admin_accounts import AdminAccounts, BootstrapResult
    from app.storage.admins import AdminRepository
    from app.storage.database import Database

    values = read_env(DEMO)
    cfg = Settings.from_env({k: v for k, v in values.items() if k not in ("APP_IMAGE", "APP_PORT")})
    assert (cfg.signer_mode, cfg.jwt_ttl_s, cfg.relay_url, cfg.relay_tls_groups, cfg.service_origin, cfg.relay_allow_insecure) == (
        "continuous", 3600, "wss://relay.primal.net", "X25519", "https://stacker.news", False)
    assert (cfg.requests_per_min, cfg.connection_ttl_s, cfg.secret_ttl_s, cfg.approval_ttl_s) == (30, 28800, 300, 300)  # limites del modo continuo, sin tocar
    assert cfg.admin_username == "evaluador" and cfg.admin_password == values["ADMIN_PASSWORD"] and "ADMIN_PASSWORD" not in repr(cfg) and values["ADMIN_PASSWORD"] not in repr(cfg)
    db = Database(str(tmp_path / "demo.db"))
    accounts = AdminAccounts(db, AdminRepository(db), PasswordService())
    assert accounts.prepare(cfg.admin_username, lambda: cfg.admin_password) is BootstrapResult.CREATED  # la primera vez crea el administrador
    assert accounts.authenticate("evaluador", values["ADMIN_PASSWORD"]) is True
    assert accounts.authenticate("evaluador", values["ADMIN_PASSWORD"] + "x") is False and accounts.authenticate("admin", values["ADMIN_PASSWORD"]) is False
    assert accounts.prepare(cfg.admin_username, lambda: "otra-contrasena-distinta-1") is BootstrapResult.EXISTS  # despues se ignora: no se sobrescribe


def test_the_official_administrator_survives_a_restart_of_the_application(tmp_path: Path) -> None:
    """Reiniciar el contenedor equivale a reabrir la misma base SQLite (volumen) sin la contrasena inicial: el usuario y la contrasena se conservan."""
    from app.security.passwords import PasswordService
    from app.services.admin_accounts import AdminAccounts, BootstrapResult
    from app.storage.admins import AdminRepository
    from app.storage.database import Database

    values = read_env(DEMO)
    path = str(tmp_path / "persist.db")
    first_db = Database(path)
    first = AdminAccounts(first_db, AdminRepository(first_db), PasswordService())
    assert first.prepare("evaluador", lambda: values["ADMIN_PASSWORD"]) is BootstrapResult.CREATED
    second_db = Database(path)  # «reinicio»: nuevo proceso, misma base, sin contrasena inicial en el entorno
    second = AdminAccounts(second_db, AdminRepository(second_db), PasswordService())
    assert second.prepare("evaluador", lambda: None) is BootstrapResult.EXISTS
    assert second.authenticate("evaluador", values["ADMIN_PASSWORD"]) is True and second.authenticate("evaluador", "contrasena-incorrecta-1234") is False


def test_provisioning_is_idempotent_and_never_overwrites_or_duplicates_the_administrator(tmp_path: Path) -> None:
    import sqlite3

    from app.security.passwords import PasswordService
    from app.services.admin_accounts import AdminAccounts, BootstrapResult
    from app.storage.admins import AdminRepository
    from app.storage.database import Database

    values = read_env(DEMO)
    path = str(tmp_path / "idem.db")

    def accounts() -> AdminAccounts:
        db = Database(path)
        return AdminAccounts(db, AdminRepository(db), PasswordService())

    def row() -> tuple[object, ...]:
        with sqlite3.connect(path) as con:
            return con.execute("SELECT id, username, password_hash, is_active, created_at, updated_at FROM admins").fetchall()  # type: ignore[no-any-return]

    assert accounts().prepare("evaluador", lambda: values["ADMIN_PASSWORD"]) is BootstrapResult.CREATED
    first = row()
    assert len(first) == 1 and first[0][1] == "evaluador" and first[0][3] == 1  # type: ignore[index]
    stored = str(first[0][2])  # type: ignore[index]
    assert stored.startswith("$argon2id$") and values["ADMIN_PASSWORD"] not in stored  # solo el hash Argon2id, nunca la contrasena
    for other_password in (values["ADMIN_PASSWORD"], "otra-contrasena-distinta-1", None):  # reinicios: misma contrasena, otra distinta o ninguna
        assert accounts().prepare("evaluador", lambda p=other_password: p) is BootstrapResult.EXISTS  # type: ignore[misc]
    assert row() == first  # ni duplicada, ni regenerada, ni con otra contrasena, ni con otra fecha
    assert accounts().authenticate("evaluador", values["ADMIN_PASSWORD"]) is True


def test_a_database_with_another_administrator_is_neither_overwritten_nor_given_the_evaluation_account(tmp_path: Path) -> None:
    """Escenario documentado en el README: la base admite UN administrador; `evaluador` no se agrega ni se sobrescribe nada (se usa un volumen nuevo)."""
    import sqlite3

    from app.security.passwords import PasswordService
    from app.services.admin_accounts import AdminAccounts, BootstrapResult
    from app.storage.admins import AdminRepository
    from app.storage.database import Database

    values = read_env(DEMO)
    path = str(tmp_path / "other.db")
    db = Database(path)
    accounts = AdminAccounts(db, AdminRepository(db), PasswordService())
    assert accounts.prepare("otroadmin", lambda: "contrasena-de-otro-administrador-1") is BootstrapResult.CREATED
    with sqlite3.connect(path) as con:
        before = con.execute("SELECT id, username, password_hash, is_active, created_at, updated_at FROM admins").fetchall()
    assert accounts.prepare("evaluador", lambda: values["ADMIN_PASSWORD"]) is BootstrapResult.EXISTS  # arranca sin error, pero no crea nada
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT id, username, password_hash, is_active, created_at, updated_at FROM admins").fetchall() == before
        with pytest.raises(sqlite3.IntegrityError):  # ni siquiera a mano: el esquema admite un unico administrador (id = 1)
            con.execute("INSERT INTO admins (id, username, password_hash, created_at, updated_at) VALUES (2, 'evaluador', '$argon2id$x', 0, 0)")
    assert accounts.authenticate("evaluador", values["ADMIN_PASSWORD"]) is False  # evaluador no existe en esa base
    assert accounts.authenticate("otroadmin", "contrasena-de-otro-administrador-1") is True  # la cuenta anterior sigue funcionando


def test_the_readme_documents_how_to_provision_evaluador_when_the_database_has_another_administrator() -> None:
    readme = README.read_text(encoding="utf-8")
    assert "Si el volumen ya tenía otro administrador" in readme and "-p nip46-evaluacion-2" in readme
    assert "nunca" in readme.split("Si el volumen ya tenía otro administrador", 1)[1][:400] and "restablecimiento automático" in readme


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker no disponible")
def test_compose_resolves_the_demo_profile_to_its_own_project_image_port_and_volume() -> None:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("ADMIN_") and k not in FORWARDED and k not in DEMO_KEYS and k not in ("PYTHON_IMAGE", "COMPOSE_PROJECT_NAME")}
    done = subprocess.run(["docker", "compose", "--env-file", str(DEMO), "-p", "nip46-evaluacion", "-f", str(COMPOSE), "config", "--format", "json"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False, env=clean)
    if done.returncode != 0:
        pytest.skip(f"docker compose config no disponible: {done.stderr[-120:]}")
    config = json.loads(done.stdout)
    app = config["services"]["app"]
    env = app["environment"]
    assert config["name"] == "nip46-evaluacion" and app["image"] == "nostr-nip46-remote-signer:evaluation"
    assert [(p["host_ip"], int(p["published"]), int(p["target"])) for p in app["ports"]] == [("127.0.0.1", 8000, 8000)]  # solo loopback
    assert (env["SIGNER_MODE"], env["ADMIN_USERNAME"], env["JWT_TTL_S"], env["RELAY_URL"], env["SERVICE_ORIGIN"]) == ("continuous", "evaluador", "3600", "wss://relay.primal.net", "https://stacker.news")
    assert env["ADMIN_PASSWORD"] == read_env(DEMO)["ADMIN_PASSWORD"] and "RELAY_ALLOW_INSECURE" not in env
    assert app["read_only"] is True and app["cap_drop"] == ["ALL"] and "no-new-privileges:true" in app["security_opt"]
    assert [v["source"] for v in app["volumes"]] == ["app_data"] and list(config["volumes"]) == ["app_data"]
    assert config["volumes"]["app_data"]["name"] == "nip46-evaluacion_app_data" != "nostr-nip46-remote-signer_app_data"  # volumen propio: no comparte la base con el proyecto por defecto


def test_the_readme_quick_start_matches_the_demo_profile_and_never_presents_down_v_as_routine() -> None:
    readme = README.read_text(encoding="utf-8")
    values = read_env(DEMO)
    head = readme.split("\n## ", 2)[1] if readme.startswith("# ") else readme  # la primera seccion tras el titulo es la instalacion oficial
    assert head.startswith("Instalación oficial")
    assert DEMO_COMMAND in head and "http://127.0.0.1:8000" in head
    assert f"`{values['ADMIN_USERNAME']}`" in head and f"`{values['ADMIN_PASSWORD']}`" in head
    assert "solo en memoria" in head and "reiniciar" in head.lower()  # la identidad no persiste: hay que crearla o importarla de nuevo
    for line in readme.splitlines():
        if "down -v" in line:
            assert "-p nip46-evaluacion" in line or "destruye" in line.lower() or "borra" in line.lower(), line  # nunca como paso rutinario ni sin el proyecto propio
    assert "nip46-evaluacion_app_data" in readme  # el volumen que se eliminaria al restablecer, identificado explicitamente
    for stale in ("sin reconexión automática", "15 minutos máximo"):
        assert stale not in readme, stale  # el modo continuo y la reconexion ya existen


def test_the_env_example_points_to_the_demo_profile_without_copying_its_password() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "deploy/demo.env" in text and read_env(DEMO)["ADMIN_PASSWORD"] not in text


# ------------------------------------------------------------------------------------------------ una sola instalacion oficial
def test_deploy_holds_only_the_official_profile_and_no_operational_reference_to_the_retired_ones() -> None:
    assert sorted(p.name for p in (ROOT / "deploy").iterdir() if p.name != "__pycache__") == ["demo.env"]  # los perfiles de B6.2 y su herramienta de importacion se retiraron (D-20)
    retired = ("b62.env", "continuous.env", "import_admin_db", "b62-admin", "manual-b61d", "d17-continuous")
    operational = [README, COMPOSE, ROOT / ".env.example", DEMO, MANUAL, MANUAL_COMPOSE, ROOT / "lab" / "README.md", ROOT / "lab" / "manual" / "check_live.py"]
    for path in operational:
        text = path.read_text(encoding="utf-8")
        assert [name for name in retired if name in text] == [], path.name


# ------------------------------------------------------------------------------------------------ puertos de los entornos documentados (sin choques)
def test_no_documented_environment_shares_a_host_port_and_the_lab_signer_is_not_on_the_official_port() -> None:
    manual = read_env(MANUAL)
    assert manual == {"APP_PORT": "18000", "ADMIN_USERNAME": "admin-manual"}  # el firmante del laboratorio tiene perfil propio; sin contrasenas ni secretos
    assert not re.search(r"PASSWORD|SECRET|TOKEN|nsec|bunker://", "\n".join(manual), re.IGNORECASE)
    lab_ports = re.findall(r"127\.0\.0\.1:\$\{MANUAL_\w+:-(\d+)\}:", MANUAL_COMPOSE.read_text(encoding="utf-8"))
    assert lab_ports == ["17777", "18080"]  # relay y cliente de laboratorio
    published = [read_env(DEMO)["APP_PORT"], manual["APP_PORT"], *lab_ports]
    assert len(set(published)) == len(published) == 4, published  # oficial 8000, firmante de laboratorio 18000, relay 17777, cliente 18080


def test_the_lab_client_docs_point_to_the_lab_signer_port_not_to_the_official_one() -> None:
    readme = README.read_text(encoding="utf-8")
    assert "--env-file lab/manual/manual.env -p nip46-demo -f compose.yaml -f lab/manual/compose.manual.yaml up --build -d" in readme
    assert "<http://127.0.0.1:18000>" in readme and "**Pestaña A (firmante):** <http://127.0.0.1:8000>" not in readme
    assert "127.0.0.1:18000" in (ROOT / "lab" / "manual" / "client_web" / "index.html").read_text(encoding="utf-8")
    assert "127.0.0.1:8000" not in MANUAL_COMPOSE.read_text(encoding="utf-8").split("services:")[0]  # el encabezado del compose de laboratorio no anuncia el 8000
    assert '"18000"' in (ROOT / "lab" / "manual" / "check_live.py").read_text(encoding="utf-8")


def test_the_docker_build_context_excludes_profiles_docs_lab_tests_and_tools_and_the_image_copies_only_what_it_needs() -> None:
    ignored = {line.strip() for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}
    assert {"deploy/", "docs/", "lab/", "tests/", "tools/", "**/.env", "**/*.db", "**/*.key"} <= ignored  # la credencial de demostracion y las transcripciones no viajan al daemon
    copies = [line.split(maxsplit=1)[1] for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines() if line.startswith("COPY ") and "--from" not in line]
    assert copies == ["pyproject.toml README.md constraints.txt ./", "app ./app"]  # nada de lo excluido se copia a la imagen: el Dockerfile y .dockerignore son coherentes

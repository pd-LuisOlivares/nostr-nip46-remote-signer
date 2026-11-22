"""D-16: perfil de validacion `deploy/b62.env`, reenvio de limites en `compose.yaml` y herramienta `deploy/import_admin_db.py`.

Deterministas: sin red y sin necesitar el demonio de Docker (el CLI solo se usa para `compose config`, que no crea nada; se omite si no esta).
Estas pruebas NO demuestran interoperabilidad con Stacker News.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "deploy" / "b62.env"
COMPOSE = ROOT / "compose.yaml"
FORWARDED = ("SIGNER_WINDOW_S", "SECRET_TTL_S", "CONNECTION_TTL_S", "MAX_REQUESTS", "MAX_PENDING", "COOKIE_SECURE", "SIGNER_MODE", "REQUESTS_PER_MIN")
EXPECTED_PROFILE = {
    "APP_PORT": "8001", "SIGNER_MODE": "supervised", "RELAY_URL": "wss://relay.primal.net", "RELAY_TLS_GROUPS": "X25519", "SERVICE_ORIGIN": "https://stacker.news",
    "SIGNER_WINDOW_S": "120", "SECRET_TTL_S": "600", "APPROVAL_TTL_S": "120", "MAX_SIGNATURES": "1", "MAX_REQUESTS": "30",
    "SESSION_TTL_S": "720", "CONNECTION_TTL_S": "720", "JWT_TTL_S": "900", "ADMIN_USERNAME": "b62-admin",
}


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("import_admin_db", ROOT / "deploy" / "import_admin_db.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_admin_db"] = module
    spec.loader.exec_module(module)
    return module


def read_profile() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in PROFILE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


# ------------------------------------------------------------------------------------------------ perfil de validacion
def test_the_profile_holds_exactly_the_b62_limits_and_nothing_secret():
    assert read_profile() == EXPECTED_PROFILE
    text = PROFILE.read_text(encoding="utf-8")
    assert "NO es la configuracion definitiva" in text  # es un perfil de validacion, no el del producto
    assert not re.search(r"PASSWORD|PRIVATE|NSEC|BUNKER|TOKEN|bunker://|nsec1", text, re.IGNORECASE)
    assert "RELAY_ALLOW_INSECURE" not in text


def test_the_profile_is_valid_for_the_application_and_matches_the_plan_limits():
    cfg = Settings.from_env({k: v for k, v in read_profile().items() if k != "APP_PORT"})
    assert (cfg.relay_url, cfg.relay_tls_groups, cfg.service_origin, cfg.relay_allow_insecure) == ("wss://relay.primal.net", "X25519", "https://stacker.news", False)
    assert (cfg.window_s, cfg.secret_ttl_s, cfg.approval_ttl_s, cfg.max_signatures, cfg.max_requests) == (120, 600, 120, 1, 30)
    assert (cfg.session_ttl_s, cfg.connection_ttl_s, cfg.jwt_ttl_s) == (720, 720, 900)
    assert cfg.connection_ttl_s <= 15 * 60 and cfg.session_ttl_s <= 15 * 60  # caducan antes del limite duro de 15 minutos
    assert cfg.admin_password is None and cfg.admin_password_file is None
    assert cfg.signer_mode == "supervised"  # D-17: el perfil de validacion fija el modo supervisado de forma explicita (el modo por defecto es continuous)


# ------------------------------------------------------------------------------------------------ compose.yaml
def test_compose_forwards_every_limit_and_never_the_insecure_relay_switch_or_a_password_file():
    text = COMPOSE.read_text(encoding="utf-8")
    for name in FORWARDED + ("APPROVAL_TTL_S", "MAX_SIGNATURES", "SESSION_TTL_S", "JWT_TTL_S", "RELAY_URL", "RELAY_TLS_GROUPS", "SERVICE_ORIGIN", "ALLOWED_HOSTS"):
        assert f"{name}: ${{{name}:-}}" in text, name  # vacio = valor por defecto de app/config.py
    for forbidden in ("RELAY_ALLOW_INSECURE: ", "ADMIN_PASSWORD_FILE: ", "0.0.0.0:", "privileged", "network_mode"):
        assert forbidden not in text.replace("# A PROPOSITO", "#"), forbidden
    assert '"127.0.0.1:${APP_PORT:-8000}:8000"' in text and "DATABASE_PATH: /data/nip46.db" in text
    assert "read_only: true" in text and "cap_drop:" in text and "no-new-privileges:true" in text


def test_every_variable_read_by_the_config_that_the_profile_sets_reaches_the_container():
    text = COMPOSE.read_text(encoding="utf-8")
    for key in EXPECTED_PROFILE:
        if key != "APP_PORT":
            assert f"{key}: ${{{key}:-}}" in text, key


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker no disponible")
def test_compose_config_resolves_the_profile_into_the_container_environment() -> None:
    done = subprocess.run(["docker", "compose", "--env-file", str(PROFILE), "-p", "nip46-b62-config-check", "-f", str(COMPOSE), "config", "--format", "json"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
                          env={k: v for k, v in os.environ.items() if k not in EXPECTED_PROFILE and not k.startswith("ADMIN_") and k not in FORWARDED})
    if done.returncode != 0:
        pytest.skip(f"docker compose config no disponible: {done.stderr[-120:]}")
    app = json.loads(done.stdout)["services"]["app"]
    env = app["environment"]
    for key, value in EXPECTED_PROFILE.items():
        if key != "APP_PORT":
            assert env[key] == value, key
    assert env["DATABASE_PATH"] == "/data/nip46.db" and env["ADMIN_PASSWORD"] == "" and "RELAY_ALLOW_INSECURE" not in env
    (port,) = app["ports"]
    assert (port["host_ip"], int(port["published"]), int(port["target"])) == ("127.0.0.1", 8001, 8000)
    assert app["read_only"] is True and app["cap_drop"] == ["ALL"] and "no-new-privileges:true" in app["security_opt"]


# ------------------------------------------------------------------------------------------------ herramienta de importacion
def make_db(path: Path) -> Path:
    import sqlite3
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE admins (id INTEGER PRIMARY KEY, username TEXT)")
    con.execute("INSERT INTO admins (username) VALUES ('toy')")
    con.commit()
    con.close()
    return path


class FakeDocker:
    """Sustituye al CLI: registra los comandos y devuelve resultados programados; nunca ejecuta Docker."""

    def __init__(self, tool: ModuleType, *, volume_ok: bool = True, image_ok: bool = True, running: str = "", run_stdout: str = '{"ok": true, "admins": [1, 1]}', run_code: int = 0,
                 mutate: Path | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.volume_ok, self.image_ok, self.running, self.run_stdout, self.run_code, self.mutate = volume_ok, image_ok, running, run_stdout, run_code, mutate
        self._tool = tool

    def __call__(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args[:2] == ("volume", "inspect"):
            return subprocess.CompletedProcess(args, 0 if self.volume_ok else 1, "", "")
        if args[:2] == ("image", "inspect"):
            return subprocess.CompletedProcess(args, 0 if self.image_ok else 1, "", "")
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, self.running, "")
        if args[0] == "run":
            if self.mutate is not None:
                self.mutate.write_bytes(self.mutate.read_bytes() + b"x")
            return subprocess.CompletedProcess(args, self.run_code, self.run_stdout + "\n", "")
        raise AssertionError(args)


def run_with(tool: ModuleType, monkeypatch: pytest.MonkeyPatch, source: Path, fake: FakeDocker) -> dict[str, object]:
    monkeypatch.setattr(tool, "docker", fake)
    return tool.run_import(source, "proyecto_app_data", "imagen:local")  # type: ignore[no-any-return]


def test_import_mounts_the_source_read_only_without_network_and_with_the_unprivileged_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_tool()
    source = make_db(tmp_path / "origen.db")
    fake = FakeDocker(tool)
    facts = run_with(tool, monkeypatch, source, fake)
    assert facts["ok"] is True and facts["source_sha256_unchanged"] is True
    (run,) = [c for c in fake.calls if c[0] == "run"]
    joined = " ".join(run[:-1])  # sin el codigo del contenedor
    for needed in ("--rm", "--pull never", "--network none", "--read-only", "--cap-drop ALL", "no-new-privileges:true", "--user 10001:10001", ":/src/source.db:ro", "proyecto_app_data:/data"):
        assert needed in joined, needed
    assert "O_EXCL" in run[-1] and "destination_exists" in run[-1]  # nunca sobrescribe
    assert "unlink(DST)" in run[-1]  # revierte solo el archivo recien creado


def test_import_refuses_a_source_that_is_not_sqlite_or_has_pending_journals_or_is_a_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_tool()
    fake = FakeDocker(tool)
    notdb = tmp_path / "no.db"
    notdb.write_bytes(b"esto no es sqlite")
    with pytest.raises(tool.ImportRejected, match="no es una base SQLite"):
        run_with(tool, monkeypatch, notdb, fake)
    with pytest.raises(tool.ImportRejected, match="archivo regular"):
        run_with(tool, monkeypatch, tmp_path, fake)
    source = make_db(tmp_path / "origen.db")
    (tmp_path / "origen.db-journal").write_bytes(b"")
    with pytest.raises(tool.ImportRejected, match="-journal"):
        run_with(tool, monkeypatch, source, fake)
    assert fake.calls == []  # se rechazo ANTES de usar Docker


@pytest.mark.parametrize("kwargs, message", [({"volume_ok": False}, "volumen no existe"), ({"image_ok": False}, "imagen no existe"),
                                             ({"running": "abc123"}, "EN MARCHA")])
def test_import_refuses_when_the_volume_image_or_running_instance_precondition_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, object], message: str) -> None:
    tool = load_tool()
    fake = FakeDocker(tool, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(tool.ImportRejected, match=message):
        run_with(tool, monkeypatch, make_db(tmp_path / "origen.db"), fake)
    assert not [c for c in fake.calls if c[0] == "run"]  # no se llego a ejecutar el contenedor de copia


def test_import_reports_the_rejection_of_an_existing_destination_without_claiming_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_tool()
    fake = FakeDocker(tool, run_stdout='{"ok": false, "error": "destination_exists"}', run_code=3)
    with pytest.raises(tool.ImportRejected, match="destination_exists.*no se modifico"):
        run_with(tool, monkeypatch, make_db(tmp_path / "origen.db"), fake)


def test_import_detects_a_source_that_changes_during_the_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_tool()
    source = make_db(tmp_path / "origen.db")
    with pytest.raises(tool.ImportRejected, match="cambio durante"):
        run_with(tool, monkeypatch, source, FakeDocker(tool, mutate=source))


def test_import_rejects_an_unreadable_helper_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = load_tool()
    with pytest.raises(tool.ImportRejected, match="resultado valido"):
        run_with(tool, monkeypatch, make_db(tmp_path / "origen.db"), FakeDocker(tool, run_stdout="basura"))


def test_the_cli_returns_1_on_rejection_and_prints_only_counts_on_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    tool = load_tool()
    source = make_db(tmp_path / "origen.db")
    monkeypatch.setattr(tool, "docker", FakeDocker(tool, volume_ok=False))
    assert tool.main(["--source", str(source), "--volume", "v"]) == 1
    assert "[importacion]" in capsys.readouterr().err
    monkeypatch.setattr(tool, "docker", FakeDocker(tool))
    assert tool.main(["--source", str(source), "--volume", "v"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and "password" not in json.dumps(out).lower() and "hash" not in json.dumps(out).lower()


def test_the_tool_source_never_reads_or_prints_credentials() -> None:
    text = (ROOT / "deploy" / "import_admin_db.py").read_text(encoding="utf-8")
    code = text.split('"""', 2)[2]  # sin la documentacion del modulo
    for forbidden in ("password_hash", "SELECT username", "SELECT password", "ADMIN_PASSWORD", "os.environ", "docker\", \"pull", "\"build\"", "volume\", \"rm", "prune"):
        assert forbidden not in code, forbidden


# ------------------------------------------------------------------------------------------------ perfil del entorno local definitivo (continuo)
CONTINUOUS = ROOT / "deploy" / "continuous.env"
RECOVERY_IMAGE = "nostr-nip46-remote-signer:manual-b61d"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_the_continuous_profile_is_continuous_secret_free_and_never_reuses_the_recovery_image_tag() -> None:
    values = read_env(CONTINUOUS)
    assert values == {"APP_IMAGE": "nostr-nip46-remote-signer:d17-continuous", "APP_PORT": "8001", "SIGNER_MODE": "continuous", "RELAY_URL": "wss://relay.primal.net",
                      "RELAY_TLS_GROUPS": "X25519", "SERVICE_ORIGIN": "https://stacker.news", "ADMIN_USERNAME": "b62-admin"}
    assert values["APP_IMAGE"] not in (RECOVERY_IMAGE, "nostr-nip46-remote-signer:dev")  # la imagen anterior NO se sobrescribe: se conserva la vuelta a manual-b61d
    text = CONTINUOUS.read_text(encoding="utf-8")
    assert not re.search(r"PASSWORD|PRIVATE|NSEC|TOKEN|bunker://[0-9a-f]|nsec1", text, re.IGNORECASE) and "RELAY_ALLOW_INSECURE" not in text
    cfg = Settings.from_env({k: v for k, v in values.items() if k not in ("APP_IMAGE", "APP_PORT")})
    assert (cfg.signer_mode, cfg.requests_per_min, cfg.secret_ttl_s, cfg.connection_ttl_s, cfg.approval_ttl_s) == ("continuous", 30, 300, 28800, 300)
    assert cfg.relay_allow_insecure is False and cfg.admin_password is None


def test_the_recovery_profile_still_points_to_the_supervised_b62_setup_and_is_untouched() -> None:
    assert read_profile() == EXPECTED_PROFILE and EXPECTED_PROFILE["SIGNER_MODE"] == "supervised"  # deploy/b62.env sigue siendo el perfil de B6.2 (vía de recuperación)
    assert "APP_IMAGE" not in read_profile()  # la imagen se elige al recuperar: APP_IMAGE=...:manual-b61d


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker no disponible")
def test_compose_resolves_the_continuous_profile_to_the_new_image_and_the_recovery_command_to_the_old_one() -> None:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("ADMIN_") and k not in FORWARDED and k not in EXPECTED_PROFILE and k not in ("APP_IMAGE", "PYTHON_IMAGE")}

    def resolve(profile: Path, extra: dict[str, str]) -> dict[str, object]:
        done = subprocess.run(["docker", "compose", "--env-file", str(profile), "-p", "nostr-nip46-remote-signer", "-f", str(COMPOSE), "config", "--format", "json"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False, env={**clean, **extra})
        if done.returncode != 0:
            pytest.skip(f"docker compose config no disponible: {done.stderr[-120:]}")
        service: dict[str, object] = json.loads(done.stdout)["services"]["app"]
        return service

    new = resolve(CONTINUOUS, {})
    assert new["image"] == "nostr-nip46-remote-signer:d17-continuous" and new["environment"]["SIGNER_MODE"] == "continuous"  # type: ignore[index]
    assert "REQUESTS_PER_MIN" in new["environment"] and new["environment"]["RELAY_URL"] == "wss://relay.primal.net"  # type: ignore[operator, index]
    old = resolve(PROFILE, {"APP_IMAGE": RECOVERY_IMAGE})  # el comando de recuperación documentado
    assert old["image"] == RECOVERY_IMAGE and old["environment"]["SIGNER_MODE"] == "supervised"  # type: ignore[index]
    assert [(p["host_ip"], int(p["published"])) for p in new["ports"]] == [("127.0.0.1", 8001)] == [(p["host_ip"], int(p["published"])) for p in old["ports"]]  # type: ignore[attr-defined, index]
    assert new["volumes"] == old["volumes"]  # el MISMO volumen en ambos: los datos no se tocan


# ------------------------------------------------------------------------------------------------ perfil de demostracion para evaluadores (D-18)
DEMO = ROOT / "deploy" / "demo.env"
README = ROOT / "README.md"
DEMO_COMMAND = "docker compose --env-file deploy/demo.env -p nip46-evaluacion up --build -d"
DEMO_KEYS = {"APP_IMAGE", "APP_PORT", "ADMIN_USERNAME", "ADMIN_PASSWORD", "JWT_TTL_S", "SIGNER_MODE", "RELAY_URL", "RELAY_TLS_GROUPS", "SERVICE_ORIGIN"}


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
    assert values["APP_IMAGE"] not in (RECOVERY_IMAGE, "nostr-nip46-remote-signer:dev", "nostr-nip46-remote-signer:d17-continuous")  # no pisa ninguna imagen de otro perfil
    for other in (PROFILE, CONTINUOUS, ROOT / ".env.example"):
        assert password not in other.read_text(encoding="utf-8")  # la contrasena publica no se reutiliza en ningun otro archivo de configuracion


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


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker no disponible")
def test_compose_resolves_the_demo_profile_to_its_own_project_image_port_and_volume_without_touching_b62() -> None:
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
    assert config["volumes"]["app_data"]["name"] == "nip46-evaluacion_app_data" != "nostr-nip46-remote-signer_app_data"  # volumen propio: el de B6.2 no se toca


def test_the_readme_quick_start_matches_the_demo_profile_and_never_presents_down_v_as_routine() -> None:
    readme = README.read_text(encoding="utf-8")
    values = read_env(DEMO)
    head = readme.split("\n## ", 2)[1] if readme.startswith("# ") else readme  # la primera seccion tras el titulo es el inicio rapido
    assert head.startswith("Inicio rápido")
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

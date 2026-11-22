"""Configuración por variables de entorno: valores por defecto no sensibles, validación y errores sin valores."""
import re
from pathlib import Path

import pytest

from app.config import DEFAULT_RELAY_URL, DEFAULT_SIGNER_MODE, MODE_DEFAULTS, SIGNER_MODES, ConfigError, Settings

ROOT = Path(__file__).resolve().parents[1]


def test_defaults_are_the_reference_relay_with_default_tls():
    assert Settings.from_env({}) == Settings(relay_url="wss://relay.primal.net", relay_tls_groups=None)
    assert DEFAULT_RELAY_URL == "wss://relay.primal.net"


def test_environment_overrides_and_whitespace_is_ignored():
    s = Settings.from_env({"RELAY_URL": "  wss://relay.example.com/  ", "RELAY_TLS_GROUPS": " X25519 "})
    assert (s.relay_url, s.relay_tls_groups) == ("wss://relay.example.com/", "X25519")
    assert Settings.from_env({"RELAY_URL": "", "RELAY_TLS_GROUPS": ""}) == Settings()


@pytest.mark.parametrize("env", [
    {"RELAY_URL": "ws://relay.example.com"}, {"RELAY_URL": "https://relay.example.com"}, {"RELAY_URL": "relay.example.com"},
    {"RELAY_URL": "wss://user:clave-secreta@relay.example.com"}, {"RELAY_URL": "wss://relay.example.com?x=1"},
    {"RELAY_TLS_GROUPS": "X25519:P-256"}, {"RELAY_TLS_GROUPS": "a b"}, {"RELAY_TLS_GROUPS": "x" * 33}, {"RELAY_TLS_GROUPS": "../x"},
])
def test_invalid_values_fail_closed_without_echoing_the_value(env):
    with pytest.raises(ConfigError) as info:
        Settings.from_env(env)
    assert all(value not in str(info.value) for value in env.values() if len(value) > 6)
    assert "RELAY_" in str(info.value)


def test_settings_are_immutable():
    with pytest.raises(AttributeError):
        Settings().relay_url = "wss://otro.example.com"  # type: ignore[misc]


# --------------------------------------------------------------------------------------------- B2/B3: firmante y API local
def test_signer_defaults_are_conservative():
    s = Settings.from_env({})
    assert (s.max_signatures, s.window_s, s.relay_allow_insecure, s.service_origin) == (1, 120, False, "https://stacker.news")
    assert s.allowed_hosts == ("127.0.0.1", "localhost", "[::1]")


def test_signer_variables_are_read_and_bounded():
    s = Settings.from_env({"SIGNER_WINDOW_S": "60", "SECRET_TTL_S": "30", "CONNECTION_TTL_S": "300", "SESSION_TTL_S": "600", "APPROVAL_TTL_S": "30",
                           "MAX_SIGNATURES": "2", "MAX_REQUESTS": "10", "MAX_PENDING": "4", "ALLOWED_HOSTS": "localhost, 127.0.0.1",
                           "SERVICE_ORIGIN": "https://example.org"})
    assert (s.window_s, s.secret_ttl_s, s.connection_ttl_s, s.session_ttl_s, s.approval_ttl_s) == (60, 30, 300, 600, 30)
    assert (s.max_signatures, s.max_requests, s.max_pending, s.allowed_hosts, s.service_origin) == (2, 10, 4, ("localhost", "127.0.0.1"), "https://example.org")


@pytest.mark.parametrize("env", [
    {"MAX_SIGNATURES": "0"}, {"MAX_SIGNATURES": "4"}, {"SIGNER_WINDOW_S": "301"}, {"SIGNER_WINDOW_S": "-1"}, {"SIGNER_WINDOW_S": "1e3"},
    {"APPROVAL_TTL_S": "4"}, {"MAX_REQUESTS": "abc"}, {"MAX_PENDING": "0"}, {"SESSION_TTL_S": "59"},
    {"RELAY_ALLOW_INSECURE": "quizas"}, {"SERVICE_ORIGIN": "http://stacker.news"}, {"SERVICE_ORIGIN": "https://stacker.news/"},
    {"SERVICE_ORIGIN": "https://stacker.news/x"}, {"SERVICE_ORIGIN": "https://u:p@stacker.news"}, {"ALLOWED_HOSTS": "a b"}, {"ALLOWED_HOSTS": "x/y"},
])
def test_signer_variables_fail_closed(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_insecure_relay_is_only_accepted_with_the_explicit_flag():
    assert Settings.from_env({"RELAY_URL": "ws://127.0.0.1:7777", "RELAY_ALLOW_INSECURE": "1"}).relay_allow_insecure is True
    with pytest.raises(ConfigError):
        Settings.from_env({"RELAY_URL": "ws://127.0.0.1:7777"})


def test_database_and_admin_defaults_are_portable_and_contain_no_credentials():
    s = Settings.from_env({})
    assert (s.database_path, s.admin_username, s.admin_password, s.admin_password_file) == ("data/nip46.db", "admin", None, None)
    assert not s.database_path.startswith(("/", "\\")) and ":" not in s.database_path  # relativa: no depende de ninguna ruta del equipo


def test_database_and_admin_variables_are_read():
    s = Settings.from_env({"DATABASE_PATH": " /data/nip46.db ", "ADMIN_USERNAME": "  Operador.1 ", "ADMIN_PASSWORD": "una-contrasena-ficticia-12"})
    assert (s.database_path, s.admin_username, s.admin_password) == ("/data/nip46.db", "Operador.1", "una-contrasena-ficticia-12")
    f = Settings.from_env({"ADMIN_PASSWORD_FILE": " pw.txt "})
    assert f.admin_password_file == "pw.txt" and f.admin_password is None
    assert Settings.from_env({"ADMIN_PASSWORD": "", "ADMIN_PASSWORD_FILE": "", "DATABASE_PATH": "", "ADMIN_USERNAME": ""}) == Settings()


def test_the_initial_password_never_appears_in_repr_or_equality():
    s = Settings.from_env({"ADMIN_PASSWORD": "una-contrasena-ficticia-12"})
    assert "una-contrasena" not in repr(s) and "una-contrasena" not in str(s)
    assert s == Settings()  # el secreto no participa en la comparacion (compare=False)


@pytest.mark.parametrize("env", [
    {"ADMIN_USERNAME": "ab"}, {"ADMIN_USERNAME": "x" * 65}, {"ADMIN_USERNAME": "con espacio"}, {"ADMIN_USERNAME": "-empieza"}, {"ADMIN_USERNAME": "a;b'c"},
    {"DATABASE_PATH": "x" * 1025}, {"DATABASE_PATH": "a\x00b"}, {"ADMIN_PASSWORD_FILE": "y" * 1025}, {"ADMIN_PASSWORD_FILE": "a\x00b"},
    {"ADMIN_PASSWORD": "una-contrasena-ficticia-12", "ADMIN_PASSWORD_FILE": "pw.txt"},
])
def test_database_and_admin_variables_fail_closed_without_echoing_secrets(env):
    with pytest.raises(ConfigError) as info:
        Settings.from_env(env)
    assert "una-contrasena" not in str(info.value) and "ADMIN_" in str(info.value) or "DATABASE_PATH" in str(info.value)


def test_jwt_and_cookie_settings():
    s = Settings.from_env({})
    assert (s.jwt_ttl_s, s.cookie_secure) == (900, False)
    s = Settings.from_env({"JWT_TTL_S": "300", "COOKIE_SECURE": "1"})
    assert (s.jwt_ttl_s, s.cookie_secure) == (300, True)
    for bad in ({"JWT_TTL_S": "4"}, {"JWT_TTL_S": "3601"}, {"JWT_TTL_S": "x"}, {"COOKIE_SECURE": "quizas"}):
        with pytest.raises(ConfigError):
            Settings.from_env(bad)


# --------------------------------------------------------------------------------------------- D-17, paso 1: modo del firmante
# Valores del modo SUPERVISADO tal como eran ANTES de D-17 (literales a proposito: si alguien los cambia, esta prueba lo detecta).
LEGACY_SUPERVISED = {"signer_mode": "supervised", "window_s": 120, "secret_ttl_s": 600, "connection_ttl_s": 1800, "session_ttl_s": 3600, "approval_ttl_s": 120,
                     "max_signatures": 1, "max_requests": 60, "max_pending": 16}


def fields(s: Settings, names: tuple[str, ...]) -> dict[str, object]:
    return {n: getattr(s, n) for n in names}


def test_the_default_mode_is_continuous_and_consistent_between_settings_and_from_env():
    assert DEFAULT_SIGNER_MODE == "continuous" and SIGNER_MODES == ("supervised", "continuous")
    for s in (Settings(), Settings.from_env({}), Settings.from_env({"SIGNER_MODE": ""}), Settings.from_env({"SIGNER_MODE": "  CONTINUOUS "})):
        assert (s.signer_mode, s.requests_per_min) == ("continuous", 30)
        assert (s.secret_ttl_s, s.connection_ttl_s, s.approval_ttl_s) == (300, 28800, 300)
    assert Settings() == Settings.from_env({})  # Settings() y from_env({}) son exactamente lo mismo: un unico valor por defecto
    assert (MODE_DEFAULTS["continuous"].secret_ttl_s, MODE_DEFAULTS["continuous"].connection_ttl_s, MODE_DEFAULTS["continuous"].approval_ttl_s) == (300, 28800, 300)


def test_supervised_mode_keeps_the_previous_values_exactly():
    s = Settings.from_env({"SIGNER_MODE": "supervised"})
    assert fields(s, tuple(LEGACY_SUPERVISED)) == LEGACY_SUPERVISED
    assert Settings.from_env({"SIGNER_MODE": " Supervised "}) == s  # mayusculas y espacios no cambian el modo
    assert (MODE_DEFAULTS["supervised"].secret_ttl_s, MODE_DEFAULTS["supervised"].connection_ttl_s, MODE_DEFAULTS["supervised"].approval_ttl_s) == (600, 1800, 120)


@pytest.mark.parametrize("mode", SIGNER_MODES)
def test_explicit_variables_always_override_the_mode_defaults(mode):
    s = Settings.from_env({"SIGNER_MODE": mode, "SECRET_TTL_S": "45", "CONNECTION_TTL_S": "900", "APPROVAL_TTL_S": "60"})
    assert (s.signer_mode, s.secret_ttl_s, s.connection_ttl_s, s.approval_ttl_s) == (mode, 45, 900, 60)


@pytest.mark.parametrize("bad", ["continuo", "supervisado", "auto", "0", "1", "true", "continuous;supervised", "x" * 40])
def test_an_invalid_mode_fails_closed_without_echoing_the_value(bad):
    with pytest.raises(ConfigError) as info:
        Settings.from_env({"SIGNER_MODE": bad})
    assert str(info.value) == "SIGNER_MODE debe ser supervised o continuous"  # mensaje fijo: nombra la variable y nunca el valor recibido


def test_the_requests_per_minute_limit_is_read_and_bounded():
    assert Settings.from_env({"REQUESTS_PER_MIN": "1"}).requests_per_min == 1
    assert Settings.from_env({"REQUESTS_PER_MIN": " 120 "}).requests_per_min == 120
    for bad in ("0", "121", "-1", "1e2", "abc"):
        with pytest.raises(ConfigError, match="REQUESTS_PER_MIN"):
            Settings.from_env({"REQUESTS_PER_MIN": bad})


def test_the_requests_per_minute_default_is_the_same_in_both_modes():
    for mode in SIGNER_MODES:
        assert Settings.from_env({"SIGNER_MODE": mode}).requests_per_min == 30


def test_there_is_no_automatic_signing_setting_anywhere():
    """Alcance de D-17: cada `connect` y cada `sign_event` requieren aprobacion humana; no existe ninguna variable ni campo de firma automatica."""
    assert not [name for name in Settings.__dataclass_fields__ if "auto" in name]
    assert Settings.from_env({"AUTO_SIGN_PER_HOUR": "abc"}) == Settings()  # una variable ajena se ignora: ya no se lee ni se valida
    for relative in ("app/config.py", "compose.yaml", ".env.example", "deploy/b62.env"):
        text = (ROOT / relative).read_text(encoding="utf-8").lower().replace("á", "a")
        assert "auto_sign" not in text and "firma automatica" not in text and "firmas automaticas" not in text, relative


def test_env_example_documents_every_variable_read_by_the_configuration():
    source = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    read = set(re.findall(r'env\.get\("([A-Z0-9_]+)"', source)) | set(re.findall(r'_(?:int|flag)\(env, "([A-Z0-9_]+)"', source))
    assert {"SIGNER_MODE", "REQUESTS_PER_MIN"} <= read and "AUTO_SIGN_PER_HOUR" not in read
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert [name for name in sorted(read) if name not in example] == []  # `.env.example` no se queda atras de la configuracion real
    active = [line for line in example.splitlines() if re.match(r"[A-Z_]+=", line)]
    assert active == ["APP_PORT=8000"]  # todo lo demas va comentado: los valores por defecto los decide app/config.py, no la plantilla

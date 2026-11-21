"""Configuración por variables de entorno: valores por defecto no sensibles, validación y errores sin valores."""
import pytest

from app.config import DEFAULT_RELAY_URL, ConfigError, Settings


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


def test_jwt_and_cookie_settings():
    s = Settings.from_env({})
    assert (s.jwt_ttl_s, s.cookie_secure) == (900, False)
    s = Settings.from_env({"JWT_TTL_S": "300", "COOKIE_SECURE": "1"})
    assert (s.jwt_ttl_s, s.cookie_secure) == (300, True)
    for bad in ({"JWT_TTL_S": "4"}, {"JWT_TTL_S": "3601"}, {"JWT_TTL_S": "x"}, {"COOKIE_SECURE": "quizas"}):
        with pytest.raises(ConfigError):
            Settings.from_env(bad)

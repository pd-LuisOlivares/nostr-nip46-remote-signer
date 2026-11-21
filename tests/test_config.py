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

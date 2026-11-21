"""Configuración de la aplicación: único punto de lectura y validación de variables de entorno (decisión D-2).

Los valores por defecto no son sensibles. NO se leen secretos aquí: el token de operador (D-4) se genera al arrancar la aplicación y
la clave Nostr vive solo en memoria (D-3). Sin lectura de archivos `.env` (las variables las aporta el entorno, Docker Compose o la
terminal) y sin rutas ni direcciones propias de un equipo.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Self
from urllib.parse import urlsplit

from app.nostr.errors import InvalidBunkerUri
from app.nostr.nip46 import validate_relay_url

DEFAULT_RELAY_URL: Final = "wss://relay.primal.net"  # relay de referencia validado en la Fase 1.0A (D-7)
DEFAULT_SERVICE_ORIGIN: Final = "https://stacker.news"  # valor de `u` observado en la Compuerta B de la Fase 1.0A
DEFAULT_ALLOWED_HOSTS: Final = ("127.0.0.1", "localhost", "[::1]")
_TLS_GROUPS_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,32}\Z")  # un único nombre de curva, p. ej. X25519
_HOST_RE: Final = re.compile(r"^(\[[0-9a-fA-F:]+\]|[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)\Z")
_TRUE: Final = frozenset({"1", "true", "yes", "si"})
_FALSE: Final = frozenset({"", "0", "false", "no"})


class ConfigError(Exception):
    """Variable de entorno inválida. El mensaje nombra la variable, nunca su valor."""


def _int(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    if not re.fullmatch(r"[0-9]{1,9}", raw) or not low <= int(raw) <= high:
        raise ConfigError(f"{name} debe ser un entero entre {low} y {high}")
    return int(raw)


def _flag(env: Mapping[str, str], name: str) -> bool:
    value = env.get(name, "").strip().lower()
    if value not in _TRUE | _FALSE:
        raise ConfigError(f"{name} debe ser 1 o 0")
    return value in _TRUE


@dataclass(frozen=True, slots=True)
class Settings:
    relay_url: str = DEFAULT_RELAY_URL
    relay_tls_groups: str | None = None  # None = TLS por defecto; "X25519" = ClientHello pequeño (verificación completa en ambos casos)
    relay_allow_insecure: bool = False  # ws:// solo para el relay local de pruebas; nunca en una demostración real
    service_origin: str = DEFAULT_SERVICE_ORIGIN  # valor exacto esperado de la etiqueta `u` del evento de login
    window_s: int = 120  # antigüedad máxima (y adelanto de 30 s) aceptados de `created_at` y de los eventos de transporte
    secret_ttl_s: int = 600  # vida del secreto de conexión de la URI bunker://
    connection_ttl_s: int = 1800  # vida de una conexión activa
    session_ttl_s: int = 3600  # vida máxima de una sesión del firmante
    approval_ttl_s: int = 120  # tiempo que una solicitud espera la decisión del operador; vencida = denegada
    max_signatures: int = 1  # firmas reales por sesión (una aprobación = una firma de un reto)
    max_requests: int = 60  # solicitudes NIP-46 atendidas por sesión
    max_pending: int = 16  # solicitudes pendientes simultáneas
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS  # valores admitidos de la cabecera Host de la API (anti DNS rebinding)
    jwt_ttl_s: int = 900  # vida de la sesion JWT del operador (corta; al vencer hay que volver a iniciar sesion)
    cookie_secure: bool = False  # atributo Secure de la cookie de sesion: 1 solo si se sirve por HTTPS (la API local usa http://127.0.0.1)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """Lee y valida las variables de entorno de un mapeo (normalmente `os.environ`)."""
        insecure = _flag(env, "RELAY_ALLOW_INSECURE")
        relay = env.get("RELAY_URL", DEFAULT_RELAY_URL).strip() or DEFAULT_RELAY_URL
        try:
            relay = validate_relay_url(relay, allow_insecure=insecure)
        except InvalidBunkerUri:
            raise ConfigError("RELAY_URL debe ser una URL wss:// valida (sin credenciales, consulta ni fragmento)") from None
        groups = env.get("RELAY_TLS_GROUPS", "").strip() or None
        if groups is not None and not _TLS_GROUPS_RE.match(groups):
            raise ConfigError("RELAY_TLS_GROUPS debe ser un unico nombre de curva, por ejemplo X25519")
        origin = env.get("SERVICE_ORIGIN", DEFAULT_SERVICE_ORIGIN).strip() or DEFAULT_SERVICE_ORIGIN
        parts = urlsplit(origin)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.path or parts.query or parts.fragment or origin.endswith("/")):
            raise ConfigError("SERVICE_ORIGIN debe ser un origen https sin ruta, consulta ni barra final")
        hosts_raw = env.get("ALLOWED_HOSTS", "").strip()
        hosts = tuple(h.strip() for h in hosts_raw.split(",") if h.strip()) if hosts_raw else DEFAULT_ALLOWED_HOSTS
        if not hosts or not all(_HOST_RE.match(h) for h in hosts):
            raise ConfigError("ALLOWED_HOSTS debe ser una lista de nombres de host separados por comas")
        return cls(
            relay_url=relay, relay_tls_groups=groups, relay_allow_insecure=insecure, service_origin=origin,
            window_s=_int(env, "SIGNER_WINDOW_S", 120, 1, 300), secret_ttl_s=_int(env, "SECRET_TTL_S", 600, 30, 3600),
            connection_ttl_s=_int(env, "CONNECTION_TTL_S", 1800, 30, 86400), session_ttl_s=_int(env, "SESSION_TTL_S", 3600, 60, 86400),
            approval_ttl_s=_int(env, "APPROVAL_TTL_S", 120, 5, 600), max_signatures=_int(env, "MAX_SIGNATURES", 1, 1, 3),
            max_requests=_int(env, "MAX_REQUESTS", 60, 1, 1000), max_pending=_int(env, "MAX_PENDING", 16, 1, 100), allowed_hosts=hosts,
            jwt_ttl_s=_int(env, "JWT_TTL_S", 900, 5, 3600), cookie_secure=_flag(env, "COOKIE_SECURE"))

"""Configuración de la aplicación: único punto de lectura y validación de variables de entorno (decisión D-2).

Los valores por defecto no son sensibles. La clave Nostr vive solo en memoria (D-3) y la clave de firma del JWT se genera al arrancar (D-8).
El único secreto que se lee aquí es la contraseña INICIAL del administrador (`ADMIN_PASSWORD` o `ADMIN_PASSWORD_FILE`, D-9): solo se usa si la
base aún no tiene administrador, no aparece en `repr` ni en los errores y no se guarda (solo se guarda su hash Argon2id). Sin lectura de
archivos `.env` (las variables las aporta el entorno, Docker Compose o la terminal) y sin rutas ni direcciones propias de un equipo.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Self
from urllib.parse import urlsplit

from app.nostr.errors import InvalidBunkerUri
from app.nostr.nip46 import validate_relay_url

DEFAULT_RELAY_URL: Final = "wss://relay.primal.net"  # relay de referencia validado en la Fase 1.0A (D-7)
DEFAULT_SERVICE_ORIGIN: Final = "https://stacker.news"  # valor de `u` observado en la Compuerta B de la Fase 1.0A
DEFAULT_ALLOWED_HOSTS: Final = ("127.0.0.1", "localhost", "[::1]")
DEFAULT_DATABASE_PATH: Final = "data/nip46.db"  # relativa al directorio de trabajo; en Docker se fija a /data/nip46.db (volumen)
DEFAULT_ADMIN_USERNAME: Final = "admin"  # nombre de usuario NO secreto; no hay contraseña por defecto
_USERNAME_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}\Z")
_TLS_GROUPS_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,32}\Z")  # un único nombre de curva, p. ej. X25519
_HOST_RE: Final = re.compile(r"^(\[[0-9a-fA-F:]+\]|[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)\Z")
_TRUE: Final = frozenset({"1", "true", "yes", "si"})
_FALSE: Final = frozenset({"", "0", "false", "no"})
SIGNER_MODES: Final = ("supervised", "continuous")
DEFAULT_SIGNER_MODE: Final = "continuous"  # D-17: modo principal; `supervised` conserva el comportamiento de validación de B6.2 (aprobación humana, una firma, sin reintentos)


@dataclass(frozen=True, slots=True)
class ModeDefaults:
    """Valores por defecto de los plazos que dependen del modo. Una variable de entorno explícita siempre los reemplaza."""

    secret_ttl_s: int
    connection_ttl_s: int
    approval_ttl_s: int


MODE_DEFAULTS: Final = {"supervised": ModeDefaults(secret_ttl_s=600, connection_ttl_s=1800, approval_ttl_s=120),
                        "continuous": ModeDefaults(secret_ttl_s=300, connection_ttl_s=28800, approval_ttl_s=300)}


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
    signer_mode: str = DEFAULT_SIGNER_MODE  # "continuous" (por defecto) o "supervised" (D-17): continuo = sin topes totales de sesión, con límites de frecuencia y reconexión
    secret_ttl_s: int = MODE_DEFAULTS["continuous"].secret_ttl_s  # vida del secreto de la URI bunker:// (por modo: 300 continuo, 600 supervisado)
    connection_ttl_s: int = MODE_DEFAULTS["continuous"].connection_ttl_s  # vida absoluta de una conexión activa (por modo: 28800 continuo, 1800 supervisado)
    session_ttl_s: int = 3600  # vida máxima de una sesión del firmante (solo modo supervisado)
    approval_ttl_s: int = MODE_DEFAULTS["continuous"].approval_ttl_s  # tiempo que una solicitud espera la decisión del operador; vencida = denegada (por modo: 300 / 120)
    max_signatures: int = 1  # firmas reales por sesión (una aprobación = una firma de un reto; solo modo supervisado)
    max_requests: int = 60  # solicitudes NIP-46 atendidas por sesión (solo modo supervisado)
    requests_per_min: int = 30  # solicitudes por minuto y por conexión (solo modo continuo)
    max_pending: int = 16  # solicitudes pendientes simultáneas
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS  # valores admitidos de la cabecera Host de la API (anti DNS rebinding)
    jwt_ttl_s: int = 900  # vida de la sesion JWT del operador (corta; al vencer hay que volver a iniciar sesion)
    cookie_secure: bool = False  # atributo Secure de la cookie de sesion: 1 solo si se sirve por HTTPS (la API local usa http://127.0.0.1)
    database_path: str = DEFAULT_DATABASE_PATH  # archivo SQLite del administrador local (solo guarda el hash Argon2id; nunca claves Nostr ni tokens)
    admin_username: str = DEFAULT_ADMIN_USERNAME  # usuario del administrador inicial (solo se usa si la base no tiene administrador)
    admin_password: str | None = field(default=None, repr=False, compare=False)  # contraseña inicial (solo primer arranque); NUNCA en repr
    admin_password_file: str | None = None  # alternativa: ruta de un archivo local con la contraseña inicial (no se lee si ya hay administrador)

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
        db_path = env.get("DATABASE_PATH", "").strip() or DEFAULT_DATABASE_PATH
        if len(db_path) > 1024 or "\x00" in db_path:
            raise ConfigError("DATABASE_PATH debe ser una ruta de archivo de hasta 1024 caracteres")
        username = env.get("ADMIN_USERNAME", "").strip() or DEFAULT_ADMIN_USERNAME
        if not _USERNAME_RE.match(username):
            raise ConfigError("ADMIN_USERNAME debe tener de 3 a 64 caracteres: letras, numeros, punto, guion y guion bajo")
        mode = env.get("SIGNER_MODE", "").strip().lower() or DEFAULT_SIGNER_MODE
        if mode not in SIGNER_MODES:
            raise ConfigError("SIGNER_MODE debe ser supervised o continuous")
        ttl = MODE_DEFAULTS[mode]
        password = env.get("ADMIN_PASSWORD", "") or None
        password_file = env.get("ADMIN_PASSWORD_FILE", "").strip() or None
        if password is not None and password_file is not None:
            raise ConfigError("ADMIN_PASSWORD y ADMIN_PASSWORD_FILE son excluyentes: defina solo una")
        if password_file is not None and (len(password_file) > 1024 or "\x00" in password_file):
            raise ConfigError("ADMIN_PASSWORD_FILE debe ser una ruta de archivo de hasta 1024 caracteres")
        return cls(
            relay_url=relay, relay_tls_groups=groups, relay_allow_insecure=insecure, service_origin=origin,
            signer_mode=mode, window_s=_int(env, "SIGNER_WINDOW_S", 120, 1, 300), secret_ttl_s=_int(env, "SECRET_TTL_S", ttl.secret_ttl_s, 30, 3600),
            connection_ttl_s=_int(env, "CONNECTION_TTL_S", ttl.connection_ttl_s, 30, 86400), session_ttl_s=_int(env, "SESSION_TTL_S", 3600, 60, 86400),
            approval_ttl_s=_int(env, "APPROVAL_TTL_S", ttl.approval_ttl_s, 5, 600), max_signatures=_int(env, "MAX_SIGNATURES", 1, 1, 3),
            max_requests=_int(env, "MAX_REQUESTS", 60, 1, 1000), requests_per_min=_int(env, "REQUESTS_PER_MIN", 30, 1, 120),
            max_pending=_int(env, "MAX_PENDING", 16, 1, 100), allowed_hosts=hosts,
            jwt_ttl_s=_int(env, "JWT_TTL_S", 900, 5, 3600), cookie_secure=_flag(env, "COOKIE_SECURE"),
            database_path=db_path, admin_username=username, admin_password=password, admin_password_file=password_file)

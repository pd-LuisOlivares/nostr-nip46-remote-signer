"""Configuración de la aplicación: único punto de lectura y validación de variables de entorno (decisión D-2).

Solo contiene lo ya decidido: el relay de referencia y la opción TLS validada en el laboratorio. Los valores por defecto no son
sensibles. NO se leen secretos aquí: el token de operador (D-4) se generará al arrancar, en el Bloque B3. Sin lectura de
archivos `.env` (las variables las aporta el entorno, Docker Compose o la terminal) y sin rutas ni direcciones propias de un equipo.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Self

from app.nostr.errors import InvalidBunkerUri
from app.nostr.nip46 import validate_relay_url

DEFAULT_RELAY_URL: Final = "wss://relay.primal.net"  # relay de referencia validado en la Fase 1.0A (D-7)
_TLS_GROUPS_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,32}\Z")  # un único nombre de curva, p. ej. X25519


class ConfigError(Exception):
    """Variable de entorno inválida. El mensaje nombra la variable, nunca su valor."""


@dataclass(frozen=True, slots=True)
class Settings:
    relay_url: str = DEFAULT_RELAY_URL
    relay_tls_groups: str | None = None  # None = TLS por defecto; "X25519" = ClientHello pequeño (verificación TLS completa en ambos casos)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """Lee y valida `RELAY_URL` y `RELAY_TLS_GROUPS` de un mapeo (normalmente `os.environ`)."""
        relay = env.get("RELAY_URL", DEFAULT_RELAY_URL).strip() or DEFAULT_RELAY_URL
        try:
            relay = validate_relay_url(relay)
        except InvalidBunkerUri:
            raise ConfigError("RELAY_URL debe ser una URL wss:// valida (sin credenciales, consulta ni fragmento)") from None
        groups = env.get("RELAY_TLS_GROUPS", "").strip() or None
        if groups is not None and not _TLS_GROUPS_RE.match(groups):
            raise ConfigError("RELAY_TLS_GROUPS debe ser un unico nombre de curva, por ejemplo X25519")
        return cls(relay_url=relay, relay_tls_groups=groups)

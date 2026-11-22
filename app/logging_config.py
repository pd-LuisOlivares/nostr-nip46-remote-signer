"""Registro operacional mínimo de la autenticación local (logger `nip46.auth`). Distinto de la auditoría NIP-46 (`app/services/audit.py`, en memoria).

Formato `fecha nivel logger event=<evento> clave=valor`. Solo metadatos no sensibles (nombre del evento, prefijo del id de sesión, segundos de espera).
NUNCA: contraseñas, hashes, nombres de usuario escritos en el formulario, tokens, cookies, claves ni secretos de conexión.
"""
import logging
import sys

AUTH_LOGGER = "nip46"


def configure_logging() -> None:
    """Añade un manejador a stderr una sola vez (idempotente). uvicorn no configura el logger raíz, así que sin esto los INFO se perderían."""
    logger = logging.getLogger(AUTH_LOGGER)
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "_nip46", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler._nip46 = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

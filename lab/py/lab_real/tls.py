"""Contexto TLS del cliente (sonda y firmante). Por defecto NO cambia nada: se usa el contexto por defecto de websockets.

Medido en la Compuerta A (relay.nsec.app): con OpenSSL 3.5 el ClientHello ocupa 1530 B (key share post-cuantico
X25519MLKEM768) y no volvio ningun byte; restringido a X25519 ocupa 517 B. Con `TLS_GROUPS=X25519` el cliente ofrece
solo ese grupo. La verificacion de certificado y de nombre de host NO se tocan (se parte de create_default_context).
"""
import re
import ssl

_GROUPS = re.compile(r"^[A-Za-z0-9_-]{1,32}$")   # un solo nombre de curva (set_ecdh_curve no admite listas)


def client_context(groups: str | None) -> ssl.SSLContext | None:
    """None = comportamiento por defecto (identico a la sonda de la Compuerta A). Con `groups`, mismo contexto verificado."""
    if not groups:
        return None
    if not _GROUPS.match(groups):
        raise ValueError("TLS_GROUPS debe ser un unico nombre de curva, p. ej. X25519")
    ctx = ssl.create_default_context()
    ctx.set_ecdh_curve(groups)
    return ctx


def ssl_kwargs(groups: str | None) -> dict:
    """Argumentos para websockets.connect: vacio por defecto (`ssl=None` explicito es incompatible con wss://)."""
    ctx = client_context(groups)
    return {"ssl": ctx} if ctx is not None else {}

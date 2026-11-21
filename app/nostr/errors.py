"""Errores de dominio del núcleo Nostr.

Los mensajes son genéricos y estables: nunca incluyen claves, textos planos, cargas cifradas ni entradas del usuario.
"""


class NostrError(Exception):
    """Base de todos los errores del núcleo."""


class InvalidKeyError(NostrError):
    """Clave privada o pública inválida (formato, rango o punto fuera de la curva)."""


class SigningError(NostrError):
    """No se pudo firmar (argumento inválido)."""


class InvalidEventError(NostrError):
    """Evento NIP-01 malformado, con `id` o firma que no coinciden."""


class Nip04Error(NostrError):
    """Carga NIP-04 inválida o imposible de descifrar."""


class Nip44Error(NostrError):
    """Base de los errores de NIP-44."""


class UnsupportedVersion(Nip44Error):
    """Versión de carga desconocida."""


class InvalidPayload(Nip44Error):
    """Carga NIP-44 mal formada (base64, tamaño)."""


class InvalidMac(Nip44Error):
    """El MAC no coincide: clave equivocada o carga alterada."""


class InvalidPadding(Nip44Error):
    """Relleno inválido tras descifrar."""


class InvalidLength(Nip44Error):
    """Longitud de texto plano fuera de 1 a 65535 bytes."""


class Nip46Error(NostrError):
    """Base de los errores de NIP-46."""


class InvalidBunkerUri(Nip46Error):
    """URI `bunker://` mal formada o que incumple las reglas del proyecto."""


class InvalidNip46Message(Nip46Error):
    """Solicitud o respuesta NIP-46 mal formada."""

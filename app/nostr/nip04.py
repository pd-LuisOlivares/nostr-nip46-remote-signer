"""NIP-04 (heredado, «unrecommended»): SOLO para DESCIFRAR solicitudes entrantes.

Stacker News (NDK 2.12.2) envía el primer `connect` cifrado con NIP-04; sin descifrarlo no hay flujo. Este módulo
**no ofrece cifrado**: las respuestas se cifran siempre con NIP-44 (`app/nostr/nip44.py`). NIP-04 no autentica el mensaje:
la integridad la dan la firma del evento de transporte y la política del firmante, no este módulo.

AES-256-CBC con la coordenada X del secreto ECDH (sin hash) y relleno PKCS7. Formato: `<base64 cifrado>?iv=<base64 iv>`.
"""
import base64
import binascii
from typing import Final

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.nostr.errors import Nip04Error
from app.nostr.keys import Keypair

MAX_PAYLOAD_CHARS: Final = 200_000  # cota defensiva (más de 3 veces el máximo de NIP-44): evita decodificar entradas enormes


def decrypt(keypair: Keypair, peer_pubkey: str, payload: str) -> str:
    """Descifra una carga NIP-04. Formato, longitudes, relleno o UTF-8 inválidos: `Nip04Error` genérico; clave pública inválida: `InvalidKeyError`."""
    if not isinstance(payload, str) or len(payload) > MAX_PAYLOAD_CHARS:
        raise Nip04Error("carga nip04 invalida")
    parts = payload.split("?iv=")
    if len(parts) != 2:
        raise Nip04Error("carga nip04 invalida")
    try:
        ciphertext = base64.b64decode(parts[0], validate=True)
        iv = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        raise Nip04Error("carga nip04 invalida") from None
    if len(iv) != 16 or not ciphertext or len(ciphertext) % 16:
        raise Nip04Error("carga nip04 invalida")
    try:
        key = keypair.ecdh_x(peer_pubkey)
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise Nip04Error("carga nip04 invalida") from None

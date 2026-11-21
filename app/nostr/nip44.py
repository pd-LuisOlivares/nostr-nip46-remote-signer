"""NIP-44 v2 (cifrado autenticado): ECDH sin hash, HKDF, relleno, ChaCha20 y HMAC-SHA256.

Primitivas de bibliotecas: ECDH (`coincurve`, vía `Keypair.ecdh_x`), HKDF-expand y ChaCha20 (`cryptography`), HMAC y SHA-256
(biblioteca estándar). Propio del protocolo: relleno, formato de la carga y validaciones. Verificado con los vectores oficiales
(`tests/nostr/test_nip44.py`) y contra `nostr-tools` 2.16.2.

Restricción PROVISIONAL del proyecto (P-14, no normativa): texto plano de 1 a 65535 bytes. El prefijo extendido de longitud
(>= 65536) que permite el texto vigente de NIP-44 no está soportado y se rechaza.
"""
import base64
import binascii
import hashlib
import hmac
import os
from typing import Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

from app.nostr.errors import InvalidLength, InvalidMac, InvalidPadding, InvalidPayload, UnsupportedVersion
from app.nostr.keys import Keypair

MAX_PLAINTEXT: Final = 65535
_VERSION: Final = 2
_MIN_PAYLOAD_CHARS: Final = 132
_MIN_DATA_BYTES: Final = 99


def get_conversation_key(keypair: Keypair, peer_pubkey: str) -> bytes:
    """Clave de conversación (HKDF-extract con la sal `nip44-v2`) entre una clave privada y la pública del otro lado."""
    return hmac.new(b"nip44-v2", keypair.ecdh_x(peer_pubkey), hashlib.sha256).digest()


def get_message_keys(conversation_key: bytes, nonce: bytes) -> tuple[bytes, bytes, bytes]:
    """Claves de un mensaje: (clave ChaCha20, nonce ChaCha20 de 12 bytes, clave HMAC)."""
    if len(conversation_key) != 32 or len(nonce) != 32:
        raise InvalidPayload("longitud invalida de clave o nonce")
    keys = HKDFExpand(algorithm=hashes.SHA256(), length=76, info=nonce).derive(conversation_key)
    return keys[0:32], keys[32:44], keys[44:76]


def calc_padded_len(unpadded_len: int) -> int:
    if unpadded_len <= 32:
        return 32
    next_power = 1 << (unpadded_len - 1).bit_length()
    chunk = 32 if next_power <= 256 else next_power // 8
    return chunk * ((unpadded_len - 1) // chunk + 1)


def pad(plaintext: str) -> bytes:
    unpadded = plaintext.encode("utf-8", errors="strict")
    size = len(unpadded)
    if not 1 <= size <= MAX_PLAINTEXT:
        raise InvalidLength("longitud de texto plano invalida")
    return size.to_bytes(2, "big") + unpadded + b"\x00" * (calc_padded_len(size) - size)


def unpad(padded: bytes) -> str:
    if len(padded) < 2:
        raise InvalidPadding("relleno invalido")
    size = int.from_bytes(padded[0:2], "big")
    unpadded = padded[2:2 + size]
    if size == 0 or len(unpadded) != size or len(padded) != 2 + calc_padded_len(size):
        raise InvalidPadding("relleno invalido")
    try:
        return unpadded.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidPadding("relleno invalido") from None


def _chacha20(key: bytes, nonce12: bytes, data: bytes) -> bytes:
    return Cipher(algorithms.ChaCha20(key, b"\x00\x00\x00\x00" + nonce12), mode=None).encryptor().update(data)


def _hmac_aad(hmac_key: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    return hmac.new(hmac_key, aad + ciphertext, hashlib.sha256).digest()


def _encrypt_with_nonce(plaintext: str, conversation_key: bytes, nonce: bytes) -> str:
    """Solo para los vectores oficiales (nonce fijo). El uso normal es `encrypt`, que genera un nonce aleatorio."""
    chacha_key, chacha_nonce, hmac_key = get_message_keys(conversation_key, nonce)
    ciphertext = _chacha20(chacha_key, chacha_nonce, pad(plaintext))
    return base64.b64encode(bytes([_VERSION]) + nonce + ciphertext + _hmac_aad(hmac_key, ciphertext, nonce)).decode("ascii")


def encrypt(plaintext: str, conversation_key: bytes) -> str:
    return _encrypt_with_nonce(plaintext, conversation_key, os.urandom(32))


def _decode_payload(payload: str) -> tuple[bytes, bytes, bytes]:
    if not isinstance(payload, str) or not payload or payload[0] == "#":
        raise UnsupportedVersion("version desconocida")
    if len(payload) < _MIN_PAYLOAD_CHARS:
        raise InvalidPayload("tamano de carga invalido")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidPayload("base64 invalido") from None
    if len(data) < _MIN_DATA_BYTES:
        raise InvalidPayload("tamano de datos invalido")
    if data[0] != _VERSION:
        raise UnsupportedVersion("version no soportada")
    return data[1:33], data[33:-32], data[-32:]


def decrypt(payload: str, conversation_key: bytes) -> str:
    """Descifra una carga NIP-44 v2: comprueba el MAC (en tiempo constante) antes de descifrar."""
    nonce, ciphertext, mac = _decode_payload(payload)
    chacha_key, chacha_nonce, hmac_key = get_message_keys(conversation_key, nonce)
    if not hmac.compare_digest(_hmac_aad(hmac_key, ciphertext, nonce), mac):
        raise InvalidMac("MAC invalido")
    return unpad(_chacha20(chacha_key, chacha_nonce, ciphertext))

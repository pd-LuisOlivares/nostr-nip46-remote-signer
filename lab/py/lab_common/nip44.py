"""NIP-44 v2 para el laboratorio (segun el texto de la especificacion y sus vectores oficiales).

Primitivas de bibliotecas: ECDH (coincurve), HKDF-expand y ChaCha20 (cryptography), HMAC y SHA-256
(biblioteca estandar). Logica del protocolo propia: relleno, formato de la carga y validaciones.
Restriccion PROVISIONAL del laboratorio (propuesta P-14): texto plano de 1 a 65535 bytes; el
prefijo extendido de longitud (>= 65536) NO esta soportado y se rechaza.
"""
import base64
import binascii
import hashlib
import hmac
import os

from coincurve import PublicKey
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

CURVE_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
MAX_PLAINTEXT = 65535


class Nip44Error(Exception):
    pass


class InvalidKey(Nip44Error):
    pass


class UnsupportedVersion(Nip44Error):
    pass


class InvalidPayload(Nip44Error):
    pass


class InvalidMac(Nip44Error):
    pass


class InvalidPadding(Nip44Error):
    pass


class InvalidLength(Nip44Error):
    pass


def shared_x(secret: bytes, pub_hex: str) -> bytes:
    """Coordenada X del punto compartido, SIN hash (NO usar PrivateKey.ecdh, que hashea)."""
    if len(secret) != 32 or not 1 <= int.from_bytes(secret, "big") < CURVE_N:
        raise InvalidKey("clave privada fuera de rango")
    if not isinstance(pub_hex, str) or len(pub_hex) != 64:
        raise InvalidKey("clave publica con formato invalido")
    try:
        point = PublicKey(b"\x02" + bytes.fromhex(pub_hex)).multiply(secret)
    except (ValueError, TypeError) as exc:
        raise InvalidKey("clave publica invalida") from exc
    return point.format(compressed=True)[1:]


def get_conversation_key(secret: bytes, pub_hex: str) -> bytes:
    return hmac.new(b"nip44-v2", shared_x(secret, pub_hex), hashlib.sha256).digest()  # HKDF-extract


def get_message_keys(conversation_key: bytes, nonce: bytes) -> tuple[bytes, bytes, bytes]:
    if len(conversation_key) != 32 or len(nonce) != 32:
        raise InvalidKey("longitud invalida de clave de conversacion o nonce")
    keys = HKDFExpand(algorithm=hashes.SHA256(), length=76, info=nonce).derive(conversation_key)
    return keys[0:32], keys[32:44], keys[44:76]


def calc_padded_len(unpadded_len: int) -> int:
    if unpadded_len <= 32:
        return 32
    next_power = 1 << (unpadded_len - 1).bit_length()
    chunk = 32 if next_power <= 256 else next_power // 8
    return chunk * ((unpadded_len - 1) // chunk + 1)


def pad(plaintext: str) -> bytes:
    unpadded = plaintext.encode("utf-8")
    n = len(unpadded)
    if n < 1 or n > MAX_PLAINTEXT:
        raise InvalidLength(f"longitud de texto plano invalida: {n}")
    return n.to_bytes(2, "big") + unpadded + b"\x00" * (calc_padded_len(n) - n)


def unpad(padded: bytes) -> str:
    if len(padded) < 2:
        raise InvalidPadding("relleno demasiado corto")
    n = int.from_bytes(padded[0:2], "big")
    if n == 0:
        raise InvalidPadding("prefijo extendido no soportado (P-14) o longitud 0")
    unpadded = padded[2:2 + n]
    if len(unpadded) != n or len(padded) != 2 + calc_padded_len(n):
        raise InvalidPadding("relleno invalido")
    try:
        return unpadded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidPadding("texto no es UTF-8") from exc


def _chacha20(key: bytes, nonce12: bytes, data: bytes) -> bytes:
    return Cipher(algorithms.ChaCha20(key, b"\x00\x00\x00\x00" + nonce12), mode=None).encryptor().update(data)


def _mac(hmac_key: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    if len(aad) != 32:
        raise InvalidPayload("AAD debe medir 32 bytes")
    return hmac.new(hmac_key, aad + ciphertext, hashlib.sha256).digest()


def encrypt(plaintext: str, conversation_key: bytes, nonce: bytes | None = None) -> str:
    nonce = os.urandom(32) if nonce is None else nonce  # el nonce inyectable solo existe para los vectores
    chacha_key, chacha_nonce, hmac_key = get_message_keys(conversation_key, nonce)
    ciphertext = _chacha20(chacha_key, chacha_nonce, pad(plaintext))
    return base64.b64encode(b"\x02" + nonce + ciphertext + _mac(hmac_key, ciphertext, nonce)).decode()


def decode_payload(payload: str) -> tuple[bytes, bytes, bytes]:
    plen = len(payload)
    if plen == 0 or payload[0] == "#":
        raise UnsupportedVersion("version desconocida")
    if plen < 132:
        raise InvalidPayload("tamano de carga invalido")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidPayload("base64 invalido") from exc
    if len(data) < 99:
        raise InvalidPayload("tamano de datos invalido")
    if data[0] != 2:
        raise UnsupportedVersion(f"version {data[0]} no soportada")
    return data[1:33], data[33:-32], data[-32:]


def decrypt(payload: str, conversation_key: bytes) -> str:
    nonce, ciphertext, mac = decode_payload(payload)
    chacha_key, chacha_nonce, hmac_key = get_message_keys(conversation_key, nonce)
    if not hmac.compare_digest(_mac(hmac_key, ciphertext, nonce), mac):
        raise InvalidMac("MAC invalido")
    return unpad(_chacha20(chacha_key, chacha_nonce, ciphertext))

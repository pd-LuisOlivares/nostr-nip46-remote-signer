"""NIP-04 (heredado, 'unrecommended') SOLO para compatibilidad entrante en el laboratorio.

AES-256-CBC con la coordenada X del secreto ECDH (sin hash) y relleno PKCS7. No autenticado.
"""
import base64
import binascii
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .nip44 import shared_x


class Nip04Error(Exception):
    pass


def encrypt(secret: bytes, pub_hex: str, plaintext: str, iv: bytes | None = None) -> str:
    iv = os.urandom(16) if iv is None else iv
    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    enc = Cipher(algorithms.AES(shared_x(secret, pub_hex)), modes.CBC(iv)).encryptor()
    ct = enc.update(data) + enc.finalize()
    return base64.b64encode(ct).decode() + "?iv=" + base64.b64encode(iv).decode()


def decrypt(secret: bytes, pub_hex: str, payload: str) -> str:
    parts = payload.split("?iv=")
    if len(parts) != 2:
        raise Nip04Error("formato invalido")
    try:
        ct = base64.b64decode(parts[0], validate=True)
        iv = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Nip04Error("base64 invalido") from exc
    if len(iv) != 16 or len(ct) == 0 or len(ct) % 16:
        raise Nip04Error("longitudes invalidas")
    dec = Cipher(algorithms.AES(shared_x(secret, pub_hex)), modes.CBC(iv)).decryptor()
    padded = dec.update(ct) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    try:
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise Nip04Error("relleno invalido") from exc

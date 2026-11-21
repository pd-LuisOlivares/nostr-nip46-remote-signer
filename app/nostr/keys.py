"""Identidad Nostr: clave privada opaca, clave pública x-only, firma y verificación BIP-340 (Schnorr) y ECDH sin hash.

La clave privada solo vive dentro de `Keypair` (en memoria): no hay forma pública de leerla, y `repr`, `str`, el formato,
las excepciones, `pickle` y `copy` no la exponen.
"""
import hmac
import re
from collections.abc import Sequence
from typing import Final, NoReturn

from coincurve import PrivateKey, PublicKey, PublicKeyXOnly

from app.nostr.errors import InvalidKeyError, SigningError

CURVE_ORDER: Final = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_PUBKEY_RE: Final = re.compile(r"^[0-9a-f]{64}\Z")
_SECRET_HEX_RE: Final = re.compile(r"^[0-9a-fA-F]{64}\Z")
_BECH32_CHARSET: Final = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32_GENERATOR: Final = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_NSEC_MAX_CHARS: Final = 90


def is_valid_pubkey(value: object) -> bool:
    """Clave pública x-only válida: 64 hexadecimales en minúsculas y un punto de la curva."""
    if not isinstance(value, str) or not _PUBKEY_RE.match(value):
        return False
    try:
        PublicKeyXOnly(bytes.fromhex(value))
    except ValueError:
        return False
    return True


def require_pubkey(value: object) -> str:
    """Devuelve la clave pública si es válida; si no, `InvalidKeyError` (sin reproducir la entrada)."""
    if not is_valid_pubkey(value):
        raise InvalidKeyError("clave publica invalida")
    assert isinstance(value, str)
    return value


def verify_schnorr(pubkey: str, signature: bytes, message: bytes) -> bool:
    """Verifica una firma BIP-340 de 64 bytes sobre un mensaje de 32 bytes. Nunca lanza: devuelve False si algo es inválido."""
    if not is_valid_pubkey(pubkey) or len(signature) != 64 or len(message) != 32:
        return False
    try:
        return bool(PublicKeyXOnly(bytes.fromhex(pubkey)).verify(signature, message))
    except ValueError:
        return False


def _polymod(values: Sequence[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i, gen in enumerate(_BECH32_GENERATOR):
            if (top >> i) & 1:
                chk ^= gen
    return chk


def _convert_bits_5_to_8(data: Sequence[int]) -> bytes | None:
    """Conversión BIP-173 de grupos de 5 bits a bytes, sin relleno: devuelve None si los bits sobrantes no son cero."""
    acc, bits, out = 0, 0, bytearray()
    for value in data:
        acc = (acc << 5) | value
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
        acc &= (1 << bits) - 1
    if bits >= 5 or acc:
        return None
    return bytes(out)


def _decode_nsec(text: str) -> bytes:
    """Decodifica `nsec1...` (NIP-19, bech32 de BIP-173) a los 32 bytes de la clave. Solo minúsculas."""
    if not text.isascii() or text != text.lower() or not 8 <= len(text) <= _NSEC_MAX_CHARS:
        raise InvalidKeyError("nsec invalido")
    hrp, sep, data_part = text.rpartition("1")
    if hrp != "nsec" or not sep or len(data_part) < 6:
        raise InvalidKeyError("nsec invalido")
    try:
        values = [_BECH32_CHARSET.index(c) for c in data_part]
    except ValueError:
        raise InvalidKeyError("nsec invalido") from None
    expanded = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    if _polymod(expanded + values) != 1:
        raise InvalidKeyError("nsec invalido")
    secret = _convert_bits_5_to_8(values[:-6])
    if secret is None or len(secret) != 32:
        raise InvalidKeyError("nsec invalido")
    return secret


class Keypair:
    """Par de claves Nostr. La clave privada es opaca y no se puede serializar ni copiar."""

    __slots__ = ("_secret", "_public")

    def __init__(self, secret: bytes) -> None:
        if not isinstance(secret, bytes | bytearray) or len(secret) != 32:
            raise InvalidKeyError("clave privada invalida")
        try:
            private = PrivateKey(bytes(secret))
        except ValueError:
            raise InvalidKeyError("clave privada invalida") from None
        self._secret: bytes = private.secret
        self._public: str = private.public_key_xonly.format().hex()

    @classmethod
    def generate(cls) -> "Keypair":
        """Clave nueva con el generador criptográfico del sistema."""
        return cls(PrivateKey().secret)

    @classmethod
    def from_hex(cls, value: str) -> "Keypair":
        """Importa 64 hexadecimales (mayúsculas o minúsculas)."""
        if not isinstance(value, str) or not _SECRET_HEX_RE.match(value):
            raise InvalidKeyError("clave privada invalida")
        return cls(bytes.fromhex(value))

    @classmethod
    def from_nsec(cls, value: str) -> "Keypair":
        """Importa una clave `nsec1...` (NIP-19)."""
        if not isinstance(value, str):
            raise InvalidKeyError("nsec invalido")
        return cls(_decode_nsec(value))

    @classmethod
    def from_secret_input(cls, value: str) -> "Keypair":
        """Importa lo que escribe una persona: `nsec1...` o 64 hexadecimales. Entrada estricta, sin espacios."""
        if isinstance(value, str) and value.startswith("nsec1"):
            return cls.from_nsec(value)
        return cls.from_hex(value)

    @property
    def public_hex(self) -> str:
        return self._public

    def sign(self, message: bytes) -> bytes:
        """Firma Schnorr (BIP-340) de un mensaje de 32 bytes (p. ej. el `id` de un evento), con aleatoriedad fresca."""
        if not isinstance(message, bytes) or len(message) != 32:
            raise SigningError("el mensaje a firmar debe medir 32 bytes")
        return PrivateKey(self._secret).sign_schnorr(message)

    def ecdh_x(self, peer_pubkey: str) -> bytes:
        """Coordenada X del secreto compartido, SIN hash (no usar `PrivateKey.ecdh`, que aplica SHA-256)."""
        peer = require_pubkey(peer_pubkey)
        point = PublicKey(b"\x02" + bytes.fromhex(peer)).multiply(self._secret)
        return bytes(point.format(compressed=True)[1:])

    def __repr__(self) -> str:
        return f"Keypair(public={self._public[:8]}...)"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return format(repr(self), spec)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Keypair) and hmac.compare_digest(self._public.encode(), other._public.encode())

    def __hash__(self) -> int:
        return hash(self._public)

    def __reduce__(self) -> NoReturn:
        raise TypeError("Keypair no se puede serializar ni copiar")

"""Contraseña del administrador local (decisión D-9): política de longitud y hash/verificación con Argon2id (`argon2-cffi`). Sin FastAPI ni SQLite.

- Se guarda SOLO el hash Argon2id con sal aleatoria de 16 bytes y los parámetros del perfil RFC 9106 «low memory» (t=3, m=64 MiB, p=4). Nada de SHA-256
  simple, cifrado reversible ni texto plano.
- La política exige longitud (12 a 128 caracteres) y rechaza solo lo evidentemente inválido (caracteres de control, igual al usuario, casi un único
  carácter repetido). No impone reglas arbitrarias de composición (mayúsculas, símbolos…).
- Verificar contra una cuenta inexistente cuesta lo mismo que contra una real (hash de señuelo): la respuesta y su duración no revelan si el usuario existe.
- Ni las contraseñas ni los hashes se registran ni aparecen en excepciones.
"""
import secrets
import threading
import unicodedata
from typing import Final

from argon2 import PasswordHasher, profiles
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH: Final = 12
MAX_PASSWORD_LENGTH: Final = 128
MIN_DISTINCT_CHARACTERS: Final = 5


class PasswordPolicyError(ValueError):
    """La contraseña no cumple la política. El mensaje describe la regla incumplida, nunca el contenido."""


def validate_new_password(username: str, password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"la contrasena debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres")
    if any(unicodedata.category(ch).startswith("C") for ch in password):
        raise PasswordPolicyError("la contrasena no puede contener caracteres de control")
    if password.casefold() == username.casefold():
        raise PasswordPolicyError("la contrasena no puede ser igual al nombre de usuario")
    if len(set(password)) < MIN_DISTINCT_CHARACTERS:
        raise PasswordPolicyError("la contrasena es demasiado repetitiva")


def default_hasher() -> PasswordHasher:
    return PasswordHasher.from_parameters(profiles.RFC_9106_LOW_MEMORY)


class PasswordService:
    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or default_hasher()
        self._decoy: str | None = None
        self._lock = threading.Lock()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def _decoy_hash(self) -> str:
        with self._lock:
            if self._decoy is None:  # perezoso: importar la aplicación no debe costar un hash
                self._decoy = self._hasher.hash(secrets.token_urlsafe(24))
            return self._decoy

    def verify(self, stored_hash: str | None, password: str) -> bool:
        """True solo si `stored_hash` existe y corresponde a `password`. Con `None` (usuario inexistente) hace igualmente un cálculo completo."""
        target = stored_hash if stored_hash is not None else self._decoy_hash()
        try:
            self._hasher.verify(target, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        return stored_hash is not None

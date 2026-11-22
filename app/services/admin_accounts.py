"""Cuenta del administrador local (D-9): arranque de la primera cuenta y autenticación con usuario y contraseña. Sin FastAPI.

Primer arranque: si la base no tiene administrador se crea UNO a partir de la contraseña inicial que aporta el entorno (`ADMIN_PASSWORD` o
`ADMIN_PASSWORD_FILE`); se valida con la política y se guarda solo su hash Argon2id. Si no hay administrador y falta una contraseña válida, el arranque
FALLA con instrucciones (nunca se crea una cuenta con una contraseña débil ni conocida). En arranques posteriores la cuenta existente se conserva tal
cual: no se sobrescribe, no se recrea y la contraseña de entorno se ignora (ni siquiera se lee).
"""
import logging
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Final

from app.security.passwords import PasswordPolicyError, PasswordService, validate_new_password
from app.storage.admins import AdminRepository
from app.storage.database import Database

log = logging.getLogger("nip46.auth")

SETUP_HELP: Final = (
    "No existe un administrador y falta una contrasena inicial valida. Defina ADMIN_PASSWORD (o ADMIN_PASSWORD_FILE con la ruta de un archivo local) "
    "con entre 12 y 128 caracteres, opcionalmente ADMIN_USERNAME, y vuelva a arrancar. Es necesaria solo la primera vez; consulte el README (seccion 'Primer arranque')."
)


class AdminBootstrapError(Exception):
    """No se pudo preparar la cuenta del administrador. El mensaje es seguro para mostrar: nunca contiene la contraseña ni el hash."""


class BootstrapResult(StrEnum):
    CREATED = "created"
    EXISTS = "exists"


class AdminAccounts:
    def __init__(self, database: Database, repository: AdminRepository, passwords: PasswordService, *, now: Callable[[], float] = time.time) -> None:
        self._db, self._repo, self._passwords, self._now = database, repository, passwords, now

    def prepare(self, username: str, initial_password: Callable[[], str | None]) -> BootstrapResult:
        """Inicializa la base (esquema incluido) y crea el administrador inicial si no existe. Bloqueante: llamar desde un hilo."""
        self._db.initialize()
        if self._repo.count() > 0:
            log.info("auth event=admin_bootstrap result=exists")
            return BootstrapResult.EXISTS
        password = initial_password()
        if not password:
            raise AdminBootstrapError(SETUP_HELP)
        try:
            validate_new_password(username, password)
        except PasswordPolicyError as exc:
            raise AdminBootstrapError(f"La contrasena inicial no es valida: {exc}. {SETUP_HELP}") from None
        created = self._repo.create_if_none(username, self._passwords.hash(password), int(self._now()))
        result = BootstrapResult.CREATED if created else BootstrapResult.EXISTS  # EXISTS: otro proceso la creó entre la comprobación y el INSERT
        log.info("auth event=admin_bootstrap result=%s", result.value)
        return result

    def authenticate(self, username: str, password: str) -> bool:
        """True si el usuario existe, está activo y la contraseña coincide. Bloqueante (Argon2 + SQLite): llamar desde un hilo."""
        record = self._repo.get_by_username(username)
        usable = record if record is not None and record.is_active else None
        if not self._passwords.verify(usable.password_hash if usable else None, password) or usable is None:
            return False
        self._repo.touch_login(usable.id, int(self._now()))
        return True

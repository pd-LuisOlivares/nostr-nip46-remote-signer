"""SQLite local del administrador (decisión D-9). ÚNICO módulo que abre la base; ningún SQL fuera de `app/storage/`.

Qué guarda: solo la cuenta del administrador local (usuario y hash Argon2id). NUNCA claves privadas Nostr, secretos bunker, JWT, cookies ni la clave
de firma del JWT (esos viven solo en memoria). Se crea sola en el primer arranque: directorio, archivo (permisos 0600 donde el sistema los admite) y
esquema. El esquema se versiona con `PRAGMA user_version`; una base con una versión más nueva que la soportada se rechaza (falla de forma segura).
Una conexión por operación (sqlite3 no comparte conexiones entre hilos) y escrituras con `BEGIN IMMEDIATE`: dos procesos que arrancan a la vez no
pueden crear dos administradores.
"""
import contextlib
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Final

SCHEMA_VERSION: Final = 1
BUSY_TIMEOUT_S: Final = 5.0
_SCHEMA: Final = (
    # Alcance inicial: UN administrador local (id fijo = 1). Ampliarlo exigiría una migración y una decisión nueva.
    """CREATE TABLE IF NOT EXISTS admins (
        id            INTEGER PRIMARY KEY CHECK (id = 1),
        username      TEXT    NOT NULL UNIQUE COLLATE NOCASE CHECK (length(username) BETWEEN 3 AND 64),
        password_hash TEXT    NOT NULL CHECK (password_hash LIKE '$argon2id$%' AND length(password_hash) <= 512),
        is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at    INTEGER NOT NULL,
        updated_at    INTEGER NOT NULL,
        last_login_at INTEGER
    )""",
)


class StorageError(Exception):
    """La base no se pudo abrir, crear o consultar. El mensaje es genérico: no incluye rutas ni datos de la cuenta."""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    # ------------------------------------------------------------------------------------------ conexión
    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        try:
            conn = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_S, isolation_level=None)  # autocommit; las transacciones son explícitas
        except sqlite3.Error:
            raise StorageError("no se pudo abrir la base de datos local") from None
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA temp_store = MEMORY")  # sin archivos temporales (el sistema de archivos del contenedor es de solo lectura)
            yield conn
        except sqlite3.Error:
            raise StorageError("error al consultar la base de datos local") from None
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Escritura serializada: `BEGIN IMMEDIATE` toma el bloqueo de escritura antes de leer, así que la comprobación y el INSERT son atómicos."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    # ------------------------------------------------------------------------------------------ inicialización
    def initialize(self) -> None:
        """Crea directorio, archivo y esquema si faltan. Idempotente y segura frente a arranques simultáneos."""
        path = Path(self._path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                raise StorageError("DATABASE_PATH apunta a un directorio, no a un archivo")
            if not path.exists():
                os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))  # propietario solamente (en Windows el modo se ignora)
        except OSError:
            raise StorageError("no se pudo crear la base de datos local: revise DATABASE_PATH y los permisos del directorio") from None
        with self.transaction() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise StorageError("la base de datos tiene un esquema mas nuevo que esta version de la aplicacion")
            if version < SCHEMA_VERSION:
                for statement in _SCHEMA:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")  # constante entera propia: PRAGMA no admite parámetros

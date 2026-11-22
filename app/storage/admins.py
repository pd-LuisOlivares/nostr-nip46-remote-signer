"""Repositorio del administrador local: todas las consultas SQL del producto, siempre parametrizadas."""
from dataclasses import dataclass, field

from app.storage.database import Database


@dataclass(frozen=True, slots=True)
class AdminRecord:
    id: int
    username: str
    password_hash: str = field(repr=False)  # el hash tampoco debe aparecer en registros ni en trazas
    is_active: bool
    created_at: int
    updated_at: int
    last_login_at: int | None


_COLUMNS = "id, username, password_hash, is_active, created_at, updated_at, last_login_at"


class AdminRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def count(self) -> int:
        with self._db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0])

    def get_by_username(self, username: str) -> AdminRecord | None:
        with self._db.connect() as conn:
            row = conn.execute(f"SELECT {_COLUMNS} FROM admins WHERE username = ?", (username,)).fetchone()  # noqa: S608 - columnas constantes
        return None if row is None else AdminRecord(row[0], row[1], row[2], bool(row[3]), row[4], row[5], row[6])

    def create_if_none(self, username: str, password_hash: str, now: int) -> bool:
        """Inserta el administrador SOLO si la tabla está vacía, en una sola sentencia atómica. Devuelve False si ya existía alguno."""
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO admins (id, username, password_hash, is_active, created_at, updated_at) "
                "SELECT 1, ?, ?, 1, ?, ? WHERE NOT EXISTS (SELECT 1 FROM admins)",
                (username, password_hash, now, now))
            return cursor.rowcount == 1

    def touch_login(self, admin_id: int, now: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("UPDATE admins SET last_login_at = ? WHERE id = ?", (now, admin_id))

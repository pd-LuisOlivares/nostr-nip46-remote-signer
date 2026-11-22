"""SQLite local: inicialización desde cero, esquema, restricciones de integridad, repositorio parametrizado y errores controlados."""
import os
import sqlite3
import stat
import threading
from pathlib import Path

import pytest

from app.storage.admins import AdminRepository
from app.storage.database import SCHEMA_VERSION, Database, StorageError
from app.storage.secret_file import MAX_SECRET_FILE_BYTES, read_password_file

HASH = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHRzYWx0$aGFzaGhhc2hoYXNoaGFzaGhhc2hoYXNoaGFzaGhhc2g"  # forma valida, sin valor real


def fresh(tmp_path: Path, name: str = "admin.db") -> tuple[Database, AdminRepository]:
    db = Database(str(tmp_path / name))
    db.initialize()
    return db, AdminRepository(db)


# ------------------------------------------------------------------------------------------------ inicialización
def test_initialize_creates_directories_file_and_schema_from_scratch(tmp_path: Path) -> None:
    target = tmp_path / "no" / "existe" / "aun" / "app.db"
    assert not target.parent.exists()
    Database(str(target)).initialize()
    assert target.is_file()
    con = sqlite3.connect(target)
    assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert [r[1] for r in con.execute("PRAGMA table_info(admins)")] == ["id", "username", "password_hash", "is_active", "created_at", "updated_at", "last_login_at"]
    con.close()


def test_initialize_is_idempotent_and_keeps_existing_data(tmp_path: Path) -> None:
    db, repo = fresh(tmp_path)
    assert repo.create_if_none("operador", HASH, 100)
    db.initialize()
    db.initialize()
    stored = repo.get_by_username("operador")
    assert repo.count() == 1 and stored is not None and stored.password_hash == HASH and stored.created_at == 100


@pytest.mark.skipif(os.name == "nt", reason="los permisos POSIX no aplican en Windows (el modo se ignora)")
def test_the_database_file_is_private_to_the_owner(tmp_path: Path) -> None:
    db, _ = fresh(tmp_path)
    assert stat.S_IMODE(os.stat(db.path).st_mode) == 0o600


def test_a_directory_instead_of_a_file_is_a_controlled_error_without_the_path(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as info:
        Database(str(tmp_path)).initialize()
    assert str(tmp_path) not in str(info.value)


def test_a_parent_that_is_a_file_is_a_controlled_error(tmp_path: Path) -> None:
    blocker = tmp_path / "bloqueo"
    blocker.write_text("no soy un directorio")
    with pytest.raises(StorageError) as info:
        Database(str(blocker / "app.db")).initialize()
    assert "bloqueo" not in str(info.value)


def test_connecting_to_an_uncreatable_location_is_a_controlled_error_without_the_path(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "no-existe" / "x.db"))  # sin initialize(): el directorio no existe
    with pytest.raises(StorageError) as info, db.connect():
        pass
    assert "no-existe" not in str(info.value)


def test_a_file_that_is_not_sqlite_is_a_controlled_error(tmp_path: Path) -> None:
    bad = tmp_path / "roto.db"
    bad.write_bytes(b"esto no es una base de datos sqlite" * 50)
    with pytest.raises(StorageError):
        Database(str(bad)).initialize()


def test_a_newer_schema_is_refused(tmp_path: Path) -> None:
    db, _ = fresh(tmp_path)
    con = sqlite3.connect(db.path)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    con.close()
    with pytest.raises(StorageError, match="esquema mas nuevo"):
        db.initialize()


def test_concurrent_initialization_yields_one_schema_and_no_errors(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "carrera.db"))
    errors: list[BaseException] = []

    def run() -> None:
        try:
            db.initialize()
        except BaseException as exc:  # noqa: BLE001 - se recogen para comprobarlos
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    con = sqlite3.connect(db.path)
    assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'admins'").fetchone()[0] == 1
    con.close()


# ------------------------------------------------------------------------------------------------ integridad del esquema
def test_only_one_admin_can_ever_exist_even_with_raw_sql(tmp_path: Path) -> None:
    db, repo = fresh(tmp_path)
    assert repo.create_if_none("operador", HASH, 1) is True
    assert repo.create_if_none("otro-admin", HASH, 2) is False and repo.count() == 1
    con = sqlite3.connect(db.path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO admins (id, username, password_hash, created_at, updated_at) VALUES (2, 'otro', ?, 1, 1)", (HASH,))  # CHECK (id = 1)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO admins (id, username, password_hash, created_at, updated_at) VALUES (1, 'OPERADOR', ?, 1, 1)", (HASH,))  # PK / UNIQUE
    con.close()


@pytest.mark.parametrize("bad_hash", ["contrasena-en-texto-plano", "", "5f4dcc3b5aa765d61d8327deb882cf99", "$2b$12$abcdefghijklmnopqrstuv", "$argon2i$v=19$m=8,t=1,p=1$a$b",
                                      "$argon2id$" + "x" * 600])
def test_the_database_itself_refuses_anything_that_is_not_an_argon2id_hash(tmp_path: Path, bad_hash: str) -> None:
    db, _ = fresh(tmp_path)
    con = sqlite3.connect(db.path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO admins (id, username, password_hash, created_at, updated_at) VALUES (1, 'operador', ?, 1, 1)", (bad_hash,))
    con.close()


@pytest.mark.parametrize("username", ["ab", "x" * 65, None])
def test_username_length_and_not_null_constraints(tmp_path: Path, username: str | None) -> None:
    db, _ = fresh(tmp_path)
    con = sqlite3.connect(db.path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO admins (id, username, password_hash, created_at, updated_at) VALUES (1, ?, ?, 1, 1)", (username, HASH))
    con.close()


def test_is_active_only_accepts_zero_or_one(tmp_path: Path) -> None:
    db, _ = fresh(tmp_path)
    con = sqlite3.connect(db.path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO admins (id, username, password_hash, is_active, created_at, updated_at) VALUES (1, 'operador', ?, 2, 1, 1)", (HASH,))
    con.close()


# ------------------------------------------------------------------------------------------------ repositorio
def test_repository_lookup_is_case_insensitive_and_parameterized(tmp_path: Path) -> None:
    _, repo = fresh(tmp_path)
    repo.create_if_none("Operador", HASH, 5)
    for name in ("operador", "OPERADOR", "Operador"):
        found = repo.get_by_username(name)
        assert found is not None and found.id == 1 and found.is_active and found.last_login_at is None
    for hostile in ("' OR '1'='1", "operador'; DROP TABLE admins;--", "operador%", "oper_dor", "", "x" * 5000):
        assert repo.get_by_username(hostile) is None
    assert repo.count() == 1  # la inyeccion no hizo nada


def test_the_record_repr_hides_the_hash(tmp_path: Path) -> None:
    _, repo = fresh(tmp_path)
    repo.create_if_none("operador", HASH, 5)
    record = repo.get_by_username("operador")
    assert record is not None and HASH not in repr(record) and "argon2" not in repr(record)


def test_touch_login_records_the_time(tmp_path: Path) -> None:
    _, repo = fresh(tmp_path)
    repo.create_if_none("operador", HASH, 5)
    repo.touch_login(1, 999)
    record = repo.get_by_username("operador")
    assert record is not None and record.last_login_at == 999 and record.created_at == 5


def test_concurrent_creation_inserts_exactly_one_admin(tmp_path: Path) -> None:
    _, repo = fresh(tmp_path)
    results: list[bool] = []
    lock = threading.Lock()

    def run(i: int) -> None:
        created = repo.create_if_none(f"admin{i}", HASH, i)
        with lock:
            results.append(created)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1 and results.count(False) == 11 and repo.count() == 1


def test_a_failed_transaction_rolls_back(tmp_path: Path) -> None:
    db, repo = fresh(tmp_path)
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute("INSERT INTO admins (id, username, password_hash, created_at, updated_at) VALUES (1, 'operador', ?, 1, 1)", (HASH,))
        raise RuntimeError("fallo a mitad")
    assert repo.count() == 0


def test_sql_errors_become_generic_storage_errors(tmp_path: Path) -> None:
    db, _ = fresh(tmp_path)
    with pytest.raises(StorageError) as info, db.connect() as conn:
        conn.execute("SELECT * FROM tabla_inexistente")
    assert "tabla_inexistente" not in str(info.value)


def test_the_application_database_never_holds_secrets_other_than_the_hash(tmp_path: Path) -> None:
    db, _ = fresh(tmp_path)
    con = sqlite3.connect(db.path)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    columns = {c[1] for t in tables for c in con.execute(f"PRAGMA table_info({t})")}
    con.close()
    assert tables == ["admins"]
    assert not {c for c in columns if any(w in c for w in ("key", "nsec", "token", "jwt", "cookie", "secret", "bunker"))}


# ------------------------------------------------------------------------------------------------ archivo de contraseña inicial
def test_password_file_is_read_and_trailing_newlines_are_stripped(tmp_path: Path) -> None:
    for content, expected in (("frase-secreta-1234\n", "frase-secreta-1234"), ("frase-secreta-1234\r\n", "frase-secreta-1234"), ("frase secreta 1234", "frase secreta 1234")):
        path = tmp_path / "pw.txt"
        path.write_text(content, encoding="utf-8", newline="")
        assert read_password_file(str(path)) == expected


def test_password_file_errors_are_generic(tmp_path: Path) -> None:
    missing = tmp_path / "secreto-que-no-existe.txt"
    with pytest.raises(StorageError) as info:
        read_password_file(str(missing))
    assert "secreto-que-no-existe" not in str(info.value)
    big = tmp_path / "grande.txt"
    big.write_bytes(b"a" * (MAX_SECRET_FILE_BYTES + 1))
    with pytest.raises(StorageError):
        read_password_file(str(big))
    binary = tmp_path / "binario.txt"
    binary.write_bytes(b"\xff\xfe\x00\x80")
    with pytest.raises(StorageError):
        read_password_file(str(binary))
    with pytest.raises(StorageError):
        read_password_file(str(tmp_path))  # un directorio

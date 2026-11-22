"""Arranque del administrador inicial y autenticación: base nueva, contraseña ausente o inválida, reinicios y ausencia de texto plano en disco."""
import logging
import sqlite3
import threading
from pathlib import Path

import pytest
from argon2 import PasswordHasher

from app.security.passwords import PasswordService
from app.services.admin_accounts import SETUP_HELP, AdminAccounts, AdminBootstrapError, BootstrapResult
from app.storage.admins import AdminRepository
from app.storage.database import Database
from tests.support import PASSWORD, USERNAME, WRONG_PASSWORD, fast_passwords


def accounts(tmp_path: Path, passwords: PasswordService | None = None, clock: float = 1_800_000_000.0) -> tuple[AdminAccounts, AdminRepository, Database]:
    db = Database(str(tmp_path / "admin.db"))
    repo = AdminRepository(db)
    return AdminAccounts(db, repo, passwords or fast_passwords(), now=lambda: clock), repo, db


def raw_rows(db: Database) -> list[tuple[object, ...]]:
    con = sqlite3.connect(db.path)
    rows = con.execute("SELECT * FROM admins").fetchall()
    con.close()
    return rows


# ------------------------------------------------------------------------------------------------ primer arranque
def test_a_fresh_install_creates_database_schema_and_the_single_admin(tmp_path: Path) -> None:
    acc, repo, db = accounts(tmp_path)
    assert not Path(db.path).exists()
    assert acc.prepare(USERNAME, lambda: PASSWORD) is BootstrapResult.CREATED
    record = repo.get_by_username(USERNAME)
    assert record is not None and record.is_active and record.created_at == 1_800_000_000 and record.last_login_at is None and repo.count() == 1


def test_only_the_argon2id_hash_is_stored_never_the_password(tmp_path: Path) -> None:
    acc, _, db = accounts(tmp_path)
    acc.prepare(USERNAME, lambda: PASSWORD)
    (row,) = raw_rows(db)
    assert row[2].startswith("$argon2id$") and PASSWORD not in str(row) and USERNAME == row[1]
    assert PASSWORD.encode() not in Path(db.path).read_bytes()  # tampoco en el archivo en bruto


def test_with_the_production_parameters_the_stored_hash_is_rfc9106_low_memory(tmp_path: Path) -> None:
    acc, _, db = accounts(tmp_path, PasswordService())
    acc.prepare(USERNAME, lambda: PASSWORD)
    assert raw_rows(db)[0][2].startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert acc.authenticate(USERNAME, PASSWORD) and not acc.authenticate(USERNAME, WRONG_PASSWORD)


@pytest.mark.parametrize("provided", [None, ""])
def test_missing_initial_password_fails_with_instructions_and_creates_no_admin(tmp_path: Path, provided: str | None) -> None:
    acc, repo, _ = accounts(tmp_path)
    with pytest.raises(AdminBootstrapError) as info:
        acc.prepare(USERNAME, lambda: provided)
    message = str(info.value)
    assert message == SETUP_HELP and "ADMIN_PASSWORD" in message and "ADMIN_PASSWORD_FILE" in message and "12" in message
    assert repo.count() == 0  # la base y el esquema existen, pero NO hay cuenta: nunca una cuenta silenciosa o debil


@pytest.mark.parametrize("weak", ["corta", "12345678901", "aaaaaaaaaaaaaaaa", USERNAME, "x" * 129, "con\x00nulo-en-medio", "password"])
def test_weak_or_invalid_initial_password_is_refused_without_echoing_it(tmp_path: Path, weak: str) -> None:
    acc, repo, _ = accounts(tmp_path)
    with pytest.raises(AdminBootstrapError) as info:
        acc.prepare(USERNAME, lambda: weak)
    assert "contrasena inicial no es valida" in str(info.value) and "ADMIN_PASSWORD" in str(info.value)
    assert weak not in str(info.value) or len(weak) < 12
    assert repo.count() == 0


def test_a_failed_first_start_can_be_fixed_by_starting_again_with_a_valid_password(tmp_path: Path) -> None:
    acc, repo, _ = accounts(tmp_path)
    with pytest.raises(AdminBootstrapError):
        acc.prepare(USERNAME, lambda: None)
    assert acc.prepare(USERNAME, lambda: PASSWORD) is BootstrapResult.CREATED and repo.count() == 1


# ------------------------------------------------------------------------------------------------ reinicios
def test_restart_keeps_the_existing_admin_and_never_overwrites_the_password(tmp_path: Path) -> None:
    acc, _, db = accounts(tmp_path)
    acc.prepare(USERNAME, lambda: PASSWORD)
    before = raw_rows(db)
    again, _, _ = accounts(tmp_path, clock=1_900_000_000.0)
    asked: list[str] = []
    assert again.prepare("otro-usuario", lambda: asked.append("leida") or "una-contrasena-distinta-9") is BootstrapResult.EXISTS
    assert raw_rows(db) == before  # misma fila, mismo hash, misma fecha de creacion
    assert asked == []  # la contraseña de entorno ni siquiera se lee (no hace falta que siga configurada)
    assert again.authenticate(USERNAME, PASSWORD) and not again.authenticate("otro-usuario", "una-contrasena-distinta-9")


def test_restart_without_any_initial_password_works_when_the_admin_exists(tmp_path: Path) -> None:
    acc, _, _ = accounts(tmp_path)
    acc.prepare(USERNAME, lambda: PASSWORD)
    again, _, _ = accounts(tmp_path)
    assert again.prepare(USERNAME, lambda: None) is BootstrapResult.EXISTS
    assert again.authenticate(USERNAME, PASSWORD)


def test_simultaneous_first_starts_create_exactly_one_admin(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "carrera.db"))
    results: list[BootstrapResult] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def start() -> None:
        try:
            outcome = AdminAccounts(db, AdminRepository(db), fast_passwords()).prepare(USERNAME, lambda: PASSWORD)
            with lock:
                results.append(outcome)
        except BaseException as exc:  # noqa: BLE001 - se comprueba abajo
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and results.count(BootstrapResult.CREATED) == 1 and results.count(BootstrapResult.EXISTS) == 5
    assert len(raw_rows(db)) == 1


# ------------------------------------------------------------------------------------------------ autenticación
def test_authentication_accepts_only_the_right_password(tmp_path: Path) -> None:
    acc, repo, _ = accounts(tmp_path)
    acc.prepare(USERNAME, lambda: PASSWORD)
    assert acc.authenticate(USERNAME, PASSWORD) is True
    for bad in (WRONG_PASSWORD, PASSWORD + "x", PASSWORD.upper(), "", " ", "' OR '1'='1"):
        assert acc.authenticate(USERNAME, bad) is False
    record = repo.get_by_username(USERNAME)
    assert record is not None and record.last_login_at == 1_800_000_000  # solo el acceso correcto deja marca


def test_unknown_user_is_false_and_costs_a_full_verification(tmp_path: Path) -> None:
    calls: list[str] = []

    class Spy(PasswordHasher):
        def verify(self, hash: str | bytes, password: str | bytes) -> bool:  # noqa: A002 - firma de la clase base
            calls.append("verify")
            return super().verify(hash, password)

    acc, _, _ = accounts(tmp_path, PasswordService(Spy(time_cost=1, memory_cost=8, parallelism=1)))
    acc.prepare(USERNAME, lambda: PASSWORD)
    assert acc.authenticate("no-existe", PASSWORD) is False
    assert acc.authenticate(USERNAME, WRONG_PASSWORD) is False
    assert calls == ["verify", "verify"]  # mismo trabajo con usuario inexistente y con contraseña incorrecta


def test_an_inactive_admin_cannot_log_in_even_with_the_right_password(tmp_path: Path) -> None:
    acc, _, db = accounts(tmp_path)
    acc.prepare(USERNAME, lambda: PASSWORD)
    con = sqlite3.connect(db.path)
    con.execute("UPDATE admins SET is_active = 0")
    con.commit()
    con.close()
    assert acc.authenticate(USERNAME, PASSWORD) is False


def test_bootstrap_logs_the_event_without_credentials(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    acc, _, _ = accounts(tmp_path)
    with caplog.at_level(logging.DEBUG):
        acc.prepare(USERNAME, lambda: PASSWORD)
        acc.prepare(USERNAME, lambda: PASSWORD)
        acc.authenticate(USERNAME, WRONG_PASSWORD)
    assert "event=admin_bootstrap result=created" in caplog.text and "event=admin_bootstrap result=exists" in caplog.text
    assert PASSWORD not in caplog.text and WRONG_PASSWORD not in caplog.text and "$argon2" not in caplog.text

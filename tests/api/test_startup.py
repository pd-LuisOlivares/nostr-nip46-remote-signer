"""Arranque de la aplicación (lifespan): creación de SQLite y del administrador inicial, fallos controlados y persistencia entre reinicios."""
import logging
import sqlite3
from pathlib import Path

import httpx
import pytest

from app.main import create_app
from app.services.admin_accounts import AdminBootstrapError
from app.storage.database import StorageError
from tests.support import PASSWORD, USERNAME, WRONG_PASSWORD, fast_passwords, make_settings

pytestmark = pytest.mark.anyio
BASE = "http://127.0.0.1:8000"


async def login(app, password: str = PASSWORD) -> int:  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
        return (await http.post("/api/auth/login", json={"username": USERNAME, "password": password})).status_code


async def test_building_the_app_does_not_touch_the_disk(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "sub")
    create_app(settings, passwords=fast_passwords())
    assert not (tmp_path / "sub").exists()  # importar o construir no crea la base: solo el arranque (lifespan)


async def test_startup_creates_the_database_and_the_admin_and_login_works(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), passwords=fast_passwords())
    async with app.router.lifespan_context(app):
        assert (tmp_path / "admin.db").is_file()
        assert await login(app) == 200 and await login(app, WRONG_PASSWORD) == 401


async def test_a_second_start_keeps_the_admin_without_needing_the_initial_password(tmp_path: Path) -> None:
    first = create_app(make_settings(tmp_path), passwords=fast_passwords())
    async with first.router.lifespan_context(first):
        pass
    con = sqlite3.connect(tmp_path / "admin.db")
    before = con.execute("SELECT id, username, password_hash, is_active, created_at, updated_at FROM admins").fetchall()
    con.close()
    second = create_app(make_settings(tmp_path, admin_password=None, admin_username="otro"), passwords=fast_passwords())  # ADMIN_PASSWORD ya no esta configurada
    async with second.router.lifespan_context(second):
        assert await login(second) == 200
    con = sqlite3.connect(tmp_path / "admin.db")
    assert con.execute("SELECT id, username, password_hash, is_active, created_at, updated_at FROM admins").fetchall() == before  # misma cuenta y mismo hash
    assert con.execute("SELECT last_login_at FROM admins").fetchone()[0] is not None  # solo cambia la marca del ultimo acceso
    con.close()


async def test_a_changed_password_in_the_environment_does_not_change_the_stored_one(tmp_path: Path) -> None:
    first = create_app(make_settings(tmp_path), passwords=fast_passwords())
    async with first.router.lifespan_context(first):
        pass
    second = create_app(make_settings(tmp_path, admin_password="nueva-contrasena-ficticia-3"), passwords=fast_passwords())
    async with second.router.lifespan_context(second):
        assert await login(second) == 200 and await login(second, "nueva-contrasena-ficticia-3") == 401


@pytest.mark.parametrize("password", [None, "corta", "a" * 20])
async def test_missing_or_invalid_initial_password_aborts_startup_with_clear_instructions(tmp_path: Path, password: str | None,
                                                                                         capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(make_settings(tmp_path, admin_password=password), passwords=fast_passwords())
    with caplog.at_level(logging.INFO), pytest.raises(AdminBootstrapError):
        async with app.router.lifespan_context(app):
            pytest.fail("el arranque no debio completarse")
    err = capsys.readouterr().err
    assert "ADMIN_PASSWORD" in err and "[arranque]" in err
    assert "event=startup_failed" in caplog.text and (password is None or password not in err + caplog.text or len(password) < 12)
    con = sqlite3.connect(tmp_path / "admin.db")
    assert con.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0  # nunca una cuenta silenciosa
    con.close()


async def test_the_initial_password_can_come_from_a_file_and_is_not_needed_afterwards(tmp_path: Path) -> None:
    secret = tmp_path / "pw.txt"
    secret.write_text(PASSWORD + "\n", encoding="utf-8")
    app = create_app(make_settings(tmp_path, admin_password=None, admin_password_file=str(secret)), passwords=fast_passwords())
    async with app.router.lifespan_context(app):
        assert await login(app) == 200
    secret.unlink()
    again = create_app(make_settings(tmp_path, admin_password=None, admin_password_file=str(secret)), passwords=fast_passwords())  # el archivo ya no existe
    async with again.router.lifespan_context(again):
        assert await login(again) == 200


async def test_a_missing_password_file_on_first_start_is_a_controlled_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(make_settings(tmp_path, admin_password=None, admin_password_file=str(tmp_path / "no-esta.txt")), passwords=fast_passwords())
    with pytest.raises(StorageError):
        async with app.router.lifespan_context(app):
            pass
    assert "ADMIN_PASSWORD_FILE" in capsys.readouterr().err


async def test_an_unusable_database_path_aborts_startup_without_leaking_the_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "bloqueo").write_text("archivo, no directorio")
    app = create_app(make_settings(tmp_path, database_path=str(tmp_path / "bloqueo" / "app.db")), passwords=fast_passwords())
    with pytest.raises(StorageError):
        async with app.router.lifespan_context(app):
            pass
    assert "bloqueo" not in capsys.readouterr().err


async def test_a_storage_failure_during_login_is_a_generic_503_and_still_counts_the_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                                            caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(make_settings(tmp_path), passwords=fast_passwords())

    def broken(*_a: object) -> bool:
        raise StorageError("detalle interno con /ruta/secreta")

    async with app.router.lifespan_context(app):
        monkeypatch.setattr(app.state.accounts, "authenticate", broken)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            with caplog.at_level(logging.INFO):
                resp = await http.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert resp.status_code == 503 and resp.json() == {"detail": "servicio no disponible"} and "ruta" not in resp.text and "set-cookie" not in resp.headers
    assert "event=login_error reason=storage" in caplog.text and "secreta" not in caplog.text and PASSWORD not in caplog.text
    assert app.state.auth.login_limited() is False and len(app.state.auth._logins._stamps) == 1  # falla de forma segura: el intento no se perdona

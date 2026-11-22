"""Inicio y cierre de sesión del administrador (usuario y contraseña en SQLite -> JWT), cookie, CSRF, Origin, límites, CSP e interfaz estática."""
import asyncio
import logging
import sqlite3
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.security.operator_auth import MAX_LOGIN_FAILURES, MAX_TOKEN_FAILURES
from tests.support import PASSWORD, USERNAME, WRONG_PASSWORD, FakeRelay, fast_passwords, make_settings

pytestmark = pytest.mark.anyio
BASE = "http://127.0.0.1:8000"
CLAIMS = {"audience": "operator-api", "issuer": "nostr-nip46-remote-signer"}
GOOD = {"username": USERNAME, "password": PASSWORD}


def new_app(tmp_path: Path, **overrides: Any) -> FastAPI:
    return create_app(make_settings(tmp_path, **overrides), relay_factory=lambda _s: FakeRelay(), passwords=fast_passwords())


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = new_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            yield http, app


async def login(http: httpx.AsyncClient, body: dict[str, Any] | None = None, **kw: Any) -> httpx.Response:
    return await http.post("/api/auth/login", json=GOOD if body is None else body, **kw)


# ------------------------------------------------------------------------------------------------ inicio de sesión y emisión del JWT
async def test_login_issues_the_jwt_automatically_in_an_httponly_strict_cookie_and_never_in_the_body(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _app = client
    resp = await login(http)
    assert resp.status_code == 200 and resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert set(body) == {"csrf_token", "expires_in_s"} and body["expires_in_s"] == 900  # el JavaScript de la interfaz NO recibe el JWT
    cookie = resp.headers["set-cookie"]
    lowered = cookie.lower()
    assert "nip46_session=" in lowered and "httponly" in lowered and "samesite=strict" in lowered and "path=/api" in lowered and "secure" not in lowered
    token = cookie.split("nip46_session=")[1].split(";")[0]
    assert token.count(".") == 2 and jwt.get_unverified_header(token)["alg"] == "HS256"
    assert PASSWORD not in resp.text and PASSWORD not in cookie and token not in resp.text


async def test_cli_clients_can_ask_for_the_token_explicitly(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    body = (await login(http, {**GOOD, "return_token": True})).json()
    assert set(body) == {"token", "csrf_token", "expires_in_s"} and body["token"].count(".") == 2


async def test_cookie_is_secure_when_configured(tmp_path: Path) -> None:
    app = new_app(tmp_path, cookie_secure=True)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            assert "secure" in (await login(http)).headers["set-cookie"].lower()


@pytest.mark.parametrize("creds", [
    {"username": USERNAME, "password": WRONG_PASSWORD}, {"username": USERNAME, "password": PASSWORD + "x"}, {"username": USERNAME, "password": PASSWORD[:-1]},
    {"username": USERNAME, "password": "x"}, {"username": USERNAME, "password": PASSWORD.upper()},
    {"username": "no-existe", "password": PASSWORD}, {"username": "no-existe", "password": WRONG_PASSWORD},
])
async def test_wrong_password_or_unknown_user_give_the_same_401_without_cookie_or_echo(client: tuple[httpx.AsyncClient, FastAPI], creds: dict[str, str]) -> None:
    http, _ = client
    resp = await login(http, creds)
    assert resp.status_code == 401 and resp.json() == {"detail": "credenciales invalidas"} and "set-cookie" not in resp.headers
    assert creds["password"] not in resp.text and resp.headers["www-authenticate"] == "Bearer"


async def test_username_is_case_insensitive_but_the_password_is_not(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await login(http, {"username": USERNAME.upper(), "password": PASSWORD})).status_code == 200


@pytest.mark.parametrize("body", [
    {}, {"username": USERNAME}, {"password": PASSWORD}, {"username": 5, "password": PASSWORD}, {"username": USERNAME, "password": 5}, {**GOOD, "extra": 1},
    {"username": "ab", "password": PASSWORD}, {"username": "x" * 65, "password": PASSWORD}, {"username": "con espacio", "password": PASSWORD},
    {"username": "a';--", "password": PASSWORD}, {"username": USERNAME, "password": ""}, {"username": USERNAME, "password": "x" * 129}, [], "texto",
    {**GOOD, "return_token": "si"},
])
async def test_login_validation_does_not_echo_input(client: tuple[httpx.AsyncClient, FastAPI], body: object) -> None:
    http, _ = client
    resp = await http.post("/api/auth/login", json=body)
    assert resp.status_code == 422 and "input" not in resp.text and PASSWORD not in resp.text and "set-cookie" not in resp.headers


async def test_login_from_a_foreign_origin_or_host_is_refused(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await login(http, headers={"Origin": "https://evil.example"})).status_code == 403
    assert (await login(http, headers={"Origin": "http://localhost:9999"})).status_code == 403  # no coincide con Host
    assert (await login(http, headers={"Host": "evil.example"})).status_code == 400
    assert (await login(http, headers={"Origin": BASE})).status_code == 200


async def test_login_updates_last_login_in_sqlite(client: tuple[httpx.AsyncClient, FastAPI], tmp_path: Path) -> None:
    http, _ = client
    db = sqlite3.connect(tmp_path / "admin.db")
    assert db.execute("SELECT last_login_at FROM admins").fetchone() == (None,)
    await login(http)
    assert db.execute("SELECT last_login_at FROM admins").fetchone()[0] >= int(time.time()) - 5
    db.close()


# ------------------------------------------------------------------------------------------------ fuerza bruta (P-35)
async def test_login_is_rate_limited_after_repeated_failures_even_with_the_right_password(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    bad = {"username": USERNAME, "password": WRONG_PASSWORD}
    codes = [(await login(http, bad)).status_code for _ in range(MAX_LOGIN_FAILURES + 3)]
    assert codes[:MAX_LOGIN_FAILURES] == [401] * MAX_LOGIN_FAILURES and codes[MAX_LOGIN_FAILURES:] == [429] * 3
    blocked = await login(http)  # la contraseña correcta tampoco entra mientras dure el bloqueo
    assert blocked.status_code == 429 and 1 <= int(blocked.headers["retry-after"]) <= 300 and "set-cookie" not in blocked.headers


async def test_concurrent_burst_cannot_exceed_the_attempt_limit(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    """Los intentos en vuelo cuentan: 30 simultáneos no pueden obtener más de MAX_LOGIN_FAILURES verificaciones."""
    http, _ = client
    bad = {"username": USERNAME, "password": WRONG_PASSWORD}
    statuses = await asyncio.gather(*[http.post("/api/auth/login", json=bad) for _ in range(30)])
    codes = [r.status_code for r in statuses]
    assert codes.count(401) == MAX_LOGIN_FAILURES and codes.count(429) == 30 - MAX_LOGIN_FAILURES


async def test_the_limit_ignores_client_controlled_headers(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    bad = {"username": USERNAME, "password": WRONG_PASSWORD}
    for i in range(MAX_LOGIN_FAILURES):
        await login(http, bad, headers={"X-Forwarded-For": f"10.0.0.{i}", "X-Real-IP": f"10.0.1.{i}", "User-Agent": f"navegador-{i}"})
    assert (await login(http, bad, headers={"X-Forwarded-For": "203.0.113.77", "Forwarded": "for=198.51.100.9"})).status_code == 429
    assert (await login(http, headers={"X-Forwarded-For": "203.0.113.78"})).status_code == 429


async def test_changing_the_username_does_not_reset_the_limit(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    for i in range(MAX_LOGIN_FAILURES):
        await login(http, {"username": f"intruso{i}", "password": WRONG_PASSWORD})
    assert (await login(http, {"username": "otro-usuario", "password": WRONG_PASSWORD})).status_code == 429


async def test_a_successful_login_does_not_consume_the_attempt_budget(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert [(await login(http)).status_code for _ in range(MAX_LOGIN_FAILURES * 3)] == [200] * (MAX_LOGIN_FAILURES * 3)


async def test_anonymous_probes_and_stale_cookies_never_block_the_login(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    """P-35: la interfaz sondea /api/auth/session sin sesion (y una pestaña vieja envia una cookie ya invalida): nada de eso impide iniciar sesion."""
    http, _ = client
    codes = {(await http.get("/api/auth/session")).status_code for _ in range(60)}
    assert codes == {401}  # 401 siempre, nunca 429
    http.cookies.set("nip46_session", "x" * 60, domain="127.0.0.1", path="/api")
    stale = [(await http.get("/api/status")).status_code for _ in range(MAX_TOKEN_FAILURES + 5)]
    assert stale[0] == 401 and stale[-1] == 429  # el token invalido repetido si se frena...
    http.cookies.clear()
    assert (await login(http)).status_code == 200  # ...pero no afecta al inicio de sesion


async def test_bad_logins_do_not_affect_token_validation_of_an_existing_session(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await login(http)).status_code == 200
    for _ in range(MAX_LOGIN_FAILURES + 2):
        await http.post("/api/auth/login", json={"username": USERNAME, "password": WRONG_PASSWORD})
    assert (await http.get("/api/status")).status_code == 200  # la sesion ya abierta sigue funcionando


async def test_login_limit_expires_with_the_window(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    clock = [1000.0]
    app.state.auth._logins._mono = lambda: clock[0]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            for _ in range(MAX_LOGIN_FAILURES):
                await login(http, {"username": USERNAME, "password": WRONG_PASSWORD})
            assert (await login(http)).status_code == 429
            clock[0] += 301
            assert (await login(http)).status_code == 200


# ------------------------------------------------------------------------------------------------ cookie, CSRF, revocación y logout
async def test_cookie_session_reads_work_but_writes_need_csrf_and_local_origin(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    csrf = (await login(http)).json()["csrf_token"]
    assert (await http.get("/api/status")).status_code == 200  # la cookie viaja sola
    assert (await http.post("/api/identity")).status_code == 403  # sin CSRF
    assert (await http.post("/api/identity", headers={"X-CSRF-Token": "otro"})).status_code == 403
    assert (await http.post("/api/identity", headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"})).status_code == 403
    assert (await http.post("/api/identity", headers={"X-CSRF-Token": csrf, "Origin": "http://127.0.0.1:9999"})).status_code == 403
    assert (await http.post("/api/identity", headers={"X-CSRF-Token": csrf, "Origin": BASE})).status_code == 201
    assert (await http.post("/api/identity", headers={"X-CSRF-Token": csrf})).status_code == 201  # sin Origin: basta el CSRF


async def test_bearer_header_does_not_need_csrf(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    token = (await login(http, {**GOOD, "return_token": True})).json()["token"]
    http.cookies.clear()
    assert (await http.post("/api/identity", headers={"Authorization": f"Bearer {token}"})).status_code == 201


async def test_session_endpoint_and_logout_revoke_the_token(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    issued = (await login(http, {**GOOD, "return_token": True})).json()
    session = await http.get("/api/auth/session")
    assert session.json()["csrf_token"] == issued["csrf_token"] and 0 < session.json()["expires_in_s"] <= 900
    assert (await http.post("/api/auth/logout")).status_code == 403  # sin CSRF
    out = await http.post("/api/auth/logout", headers={"X-CSRF-Token": issued["csrf_token"]})
    assert out.status_code == 204 and "nip46_session=" in out.headers["set-cookie"]
    http.cookies.clear()
    assert (await http.get("/api/status", headers={"Authorization": f"Bearer {issued['token']}"})).status_code == 401  # revocado en el servidor
    assert (await http.get("/api/auth/session")).status_code == 401


async def test_expired_unsigned_and_foreign_tokens_are_401(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, app = client
    auth = app.state.auth
    issued = (await login(http, {**GOOD, "return_token": True})).json()
    claims = jwt.decode(issued["token"], auth._key, algorithms=["HS256"], **CLAIMS)
    http.cookies.clear()
    expired = jwt.encode({**claims, "exp": int(time.time()) - 10}, auth._key, algorithm="HS256")
    unsigned = jwt.encode(claims, key="", algorithm="none")
    foreign = jwt.encode(claims, b"z" * 48, algorithm="HS256")
    for token in (expired, unsigned, foreign):
        assert (await http.get("/api/status", headers={"Authorization": f"Bearer {token}"})).status_code == 401
        http.cookies.set("nip46_session", token, domain="127.0.0.1", path="/api")
        assert (await http.get("/api/status")).status_code == 401
        http.cookies.clear()


async def test_the_signing_key_is_random_per_process_and_independent_of_the_password(tmp_path: Path) -> None:
    a, b = new_app(tmp_path), new_app(tmp_path)
    assert a.state.auth._key != b.state.auth._key and len(a.state.auth._key) == 48
    assert PASSWORD.encode() not in a.state.auth._key and USERNAME.encode() not in a.state.auth._key


async def test_restart_invalidates_previous_sessions(client: tuple[httpx.AsyncClient, FastAPI], tmp_path: Path) -> None:
    http, _ = client
    token = (await login(http, {**GOOD, "return_token": True})).json()["token"]
    other = new_app(tmp_path)  # "reinicio": clave de firma y memoria nuevas (la base y el administrador se conservan)
    async with other.router.lifespan_context(other):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=other), base_url=BASE) as http2:
            assert (await http2.get("/api/status", headers={"Authorization": f"Bearer {token}"})).status_code == 401
            assert (await login(http2)).status_code == 200  # el administrador persiste en SQLite


async def test_shutdown_revokes_sessions(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            assert (await login(http)).status_code == 200
    assert app.state.auth._sessions == {}


async def test_the_password_is_never_a_valid_bearer_token(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await http.get("/api/status", headers={"Authorization": f"Bearer {PASSWORD}"})).status_code == 401


async def test_connections_list_requires_auth_and_hides_secrets(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await http.get("/api/connections")).status_code == 401
    token = (await login(http, {**GOOD, "return_token": True})).json()["token"]
    http.cookies.clear()
    resp = await http.get("/api/connections", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200 and resp.json() == []


# ------------------------------------------------------------------------------------------------ registro operacional (sin datos sensibles)
async def test_authentication_events_are_logged_without_sensitive_data(client: tuple[httpx.AsyncClient, FastAPI], caplog: pytest.LogCaptureFixture) -> None:
    http, _ = client
    with caplog.at_level(logging.DEBUG):
        assert (await login(http, {"username": "intruso-secreto", "password": WRONG_PASSWORD})).status_code == 401
        issued = (await login(http, {**GOOD, "return_token": True})).json()
        csrf = issued["csrf_token"]
        assert (await http.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})).status_code == 204
        for _ in range(MAX_LOGIN_FAILURES):
            await login(http, {"username": USERNAME, "password": WRONG_PASSWORD})
        assert (await login(http)).status_code == 429
    text = caplog.text
    for event in ("event=login_failed", "event=login_ok", "event=logout", "event=login_blocked"):
        assert event in text, event
    sensitive = [PASSWORD, WRONG_PASSWORD, USERNAME, "intruso-secreto", issued["token"], csrf, "$argon2", "nip46_session"]
    assert not [s for s in sensitive if s in text]


# ------------------------------------------------------------------------------------------------ interfaz estática y cabeceras
async def test_ui_is_served_publicly_with_a_strict_csp(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    page = await http.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    csp = page.headers["content-security-policy"]
    for directive in ("default-src 'none'", "script-src 'self'", "style-src 'self'", "base-uri 'none'", "frame-ancestors 'none'", "connect-src 'self'"):
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp and "http" not in csp
    for header in ("x-content-type-options", "referrer-policy", "x-frame-options", "cross-origin-opener-policy", "permissions-policy"):
        assert header in page.headers


async def test_the_login_form_asks_for_username_and_password_not_a_terminal_code(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    html = (await http.get("/")).text
    for expected in ('id="login-username"', 'autocomplete="username"', 'id="login-password"', 'type="password"', 'autocomplete="current-password"',
                     'id="login-btn"', "Iniciar sesión", 'role="alert"'):
        assert expected in html, expected
    assert "login-code" not in html and "código de acceso" not in html.lower()


async def test_docs_and_openapi_are_disabled_and_api_is_never_cached(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await http.get(path)).status_code == 404
    assert (await http.get("/api/status")).headers["cache-control"] == "no-store"
    assert (await http.post("/api/signer/start")).status_code == 401


async def test_connection_revocation_needs_the_jwt_and_with_the_cookie_also_the_csrf_token(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    path = "/api/connections/ZZZZZZZZZZZZ"
    assert (await http.delete(path)).status_code == 401  # sin credenciales
    issued = (await login(http, {**GOOD, "return_token": True})).json()
    csrf = issued["csrf_token"]
    assert (await http.delete(path)).status_code == 403  # cookie sin CSRF
    assert (await http.delete(path, headers={"X-CSRF-Token": "otro"})).status_code == 403
    assert (await http.delete(path, headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"})).status_code == 403
    assert (await http.delete(path, headers={"X-CSRF-Token": csrf})).status_code == 404  # supera la guardia: el id no existe
    http.cookies.clear()
    assert (await http.delete(path, headers={"Authorization": f"Bearer {issued['token']}"})).status_code == 404  # con Authorization no hace falta CSRF
    assert (await http.delete(path, headers={"Authorization": "Bearer " + "x" * 43})).status_code == 401  # un token inválido no pasa

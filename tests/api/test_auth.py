"""Inicio y cierre de sesión del operador (JWT), cookie, CSRF, Origin, CSP e interfaz estática."""
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app
from tests.support import FakeRelay

pytestmark = pytest.mark.anyio
CODE = "c" * 43
BASE = "http://127.0.0.1:8000"
CLAIMS = {"audience": "operator-api", "issuer": "nostr-nip46-remote-signer"}


@pytest.fixture
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    app = create_app(Settings(), access_code=CODE, relay_factory=lambda _s: FakeRelay(), announce_code=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            yield http, app


async def login(http: httpx.AsyncClient, **kw: Any) -> httpx.Response:
    return await http.post("/api/auth/login", json={"code": CODE}, **kw)


async def test_login_sets_an_httponly_strict_cookie_and_returns_csrf(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _app = client
    resp = await login(http)
    assert resp.status_code == 200 and resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert set(body) == {"token", "csrf_token", "expires_in_s"} and body["expires_in_s"] == 900
    cookie = resp.headers["set-cookie"].lower()
    assert "nip46_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie and "secure" not in cookie
    assert body["token"] in resp.headers["set-cookie"] and CODE not in resp.text


async def test_cookie_is_secure_when_configured() -> None:
    app = create_app(Settings(cookie_secure=True), access_code=CODE, announce_code=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
        assert "secure" in (await login(http)).headers["set-cookie"].lower()


@pytest.mark.parametrize("code", ["x" * 43, "mal-codigo-1234", CODE + "x", CODE[:-1]])
async def test_wrong_code_is_401_without_cookie_or_echo(client: tuple[httpx.AsyncClient, FastAPI], code: str) -> None:
    http, _ = client
    resp = await http.post("/api/auth/login", json={"code": code})
    assert resp.status_code == 401 and "set-cookie" not in resp.headers and code not in resp.text


@pytest.mark.parametrize("body", [{}, {"code": 5}, {"code": CODE, "extra": 1}, {"code": "x" * 201}, {"code": "corto"}, [], "texto"])
async def test_login_validation_does_not_echo_input(client: tuple[httpx.AsyncClient, FastAPI], body: object) -> None:
    http, _ = client
    resp = await http.post("/api/auth/login", json=body)
    assert resp.status_code == 422 and "input" not in resp.text and CODE not in resp.text


async def test_login_from_a_foreign_origin_or_host_is_refused(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await login(http, headers={"Origin": "https://evil.example"})).status_code == 403
    assert (await login(http, headers={"Origin": "http://localhost:9999"})).status_code == 403  # no coincide con Host
    assert (await login(http, headers={"Host": "evil.example"})).status_code == 400
    assert (await login(http, headers={"Origin": BASE})).status_code == 200


async def test_login_is_rate_limited_after_repeated_failures(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    codes = [(await http.post("/api/auth/login", json={"code": "mal" * 4})).status_code for _ in range(13)]
    assert codes[0] == 401 and codes[-1] == 429
    assert (await login(http)).status_code == 429


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
    token = (await login(http)).json()["token"]
    http.cookies.clear()
    assert (await http.post("/api/identity", headers={"Authorization": f"Bearer {token}"})).status_code == 201


async def test_session_endpoint_and_logout_revoke_the_token(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    issued = (await login(http)).json()
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
    issued = (await login(http)).json()
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


async def test_restart_invalidates_previous_sessions(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    token = (await login(http)).json()["token"]
    other = create_app(Settings(), access_code=CODE, announce_code=False)  # "reinicio": clave de firma y memoria nuevas
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=other), base_url=BASE) as http2:
        assert (await http2.get("/api/status", headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_shutdown_revokes_sessions() -> None:
    app = create_app(Settings(), access_code=CODE, announce_code=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            assert (await login(http)).status_code == 200
    assert app.state.auth._sessions == {}


async def test_login_code_is_never_a_valid_bearer_token(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await http.get("/api/status", headers={"Authorization": f"Bearer {CODE}"})).status_code == 401


async def test_connections_list_requires_auth_and_hides_secrets(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    assert (await http.get("/api/connections")).status_code == 401
    token = (await login(http)).json()["token"]
    http.cookies.clear()
    resp = await http.get("/api/connections", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200 and resp.json() == []


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


async def test_docs_and_openapi_are_disabled_and_api_is_never_cached(client: tuple[httpx.AsyncClient, FastAPI]) -> None:
    http, _ = client
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await http.get(path)).status_code == 404
    assert (await http.get("/api/status")).headers["cache-control"] == "no-store"
    assert (await http.post("/api/signer/start")).status_code == 401

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.nostr.keys import Keypair
from app.nostr.nip46 import parse_bunker_uri
from app.nostr.relay import RelayEvent
from tests.support import FakeRelay, NdkLikeClient, login_template

pytestmark = pytest.mark.anyio
CODE = "c" * 43


async def login(http: httpx.AsyncClient) -> dict[str, str]:
    resp = await http.post("/api/auth/login", json={"code": CODE})
    assert resp.status_code == 200
    http.cookies.clear()  # estos tests usan el token por cabecera; la cookie se prueba en test_auth.py y en el E2E de navegador
    return {"Authorization": "Bearer " + resp.json()["token"]}
NSEC_HEX = "11" * 32


@dataclass
class Env:
    http: httpx.AsyncClient
    auth: dict[str, str]
    relays: list[FakeRelay]
    app_state: object

    async def api(self, method: str, path: str, **kw: object) -> httpx.Response:
        return await self.http.request(method, path, headers=self.auth, **kw)  # type: ignore[arg-type]

    @property
    def relay(self) -> FakeRelay:
        return self.relays[-1]

    async def wait_for(self, predicate, timeout: float = 3.0) -> None:  # type: ignore[no-untyped-def]
        async def poll() -> None:
            while not predicate():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(poll(), timeout)


@pytest.fixture
async def env() -> AsyncIterator[Env]:
    relays: list[FakeRelay] = []

    def factory(_settings: Settings) -> FakeRelay:
        relays.append(FakeRelay())
        return relays[-1]

    app = create_app(Settings(approval_ttl_s=5), access_code=CODE, relay_factory=factory, announce_code=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
            yield Env(http, await login(http), relays, app.state.runtime)


async def start_signer(env: Env) -> str:
    assert (await env.api("POST", "/api/identity")).status_code == 201
    assert (await env.api("POST", "/api/signer/start")).status_code == 200
    return str((await env.api("GET", "/api/identity")).json()["public_key"])


# ------------------------------------------------------------------------------------------------ autenticación y Host
ENDPOINTS = [("GET", "/api/status"), ("GET", "/api/identity"), ("POST", "/api/identity"), ("PUT", "/api/identity"), ("GET", "/api/signer"),
             ("POST", "/api/signer/start"), ("POST", "/api/signer/stop"), ("POST", "/api/connections"), ("GET", "/api/requests"),
             ("POST", "/api/requests/abc/approve"), ("POST", "/api/requests/abc/deny"), ("GET", "/api/audit")]


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer " + "x" * 43}, {"Authorization": CODE}, {"Authorization": "Basic abc"},
                                     {"Authorization": f"Bearer {CODE} "}, {"Authorization": f"bearer {CODE}"}])
async def test_every_endpoint_denies_by_default(env: Env, method: str, path: str, headers: dict[str, str]) -> None:
    resp = await env.http.request(method, path, headers=headers)
    assert resp.status_code in (401, 429) and "Bearer" not in resp.text and CODE not in resp.text


async def test_repeated_failures_are_rate_limited_but_a_valid_token_still_works(env: Env) -> None:
    codes = [(await env.http.get("/api/status")).status_code for _ in range(12)]
    assert codes[0] == 401 and codes[-1] == 429
    resp = await env.http.get("/api/status", headers=env.auth)
    assert resp.status_code == 200 and (await env.http.get("/api/status")).status_code == 429


async def test_foreign_host_header_is_rejected_even_with_a_valid_token(env: Env) -> None:
    for host in ("evil.example", "127.0.0.1.evil.example", "", "10.0.0.5:8000"):
        resp = await env.http.get("/api/status", headers={**env.auth, "Host": host})
        assert resp.status_code == 400
    for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000", "LOCALHOST"):
        assert (await env.http.get("/api/status", headers={**env.auth, "Host": host})).status_code == 200


async def test_security_headers_and_no_store_on_api(env: Env) -> None:
    resp = await env.api("GET", "/api/status")
    assert resp.headers["cache-control"] == "no-store" and resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY" and resp.headers["referrer-policy"] == "no-referrer"
    assert "access-control-allow-origin" not in (await env.http.get("/health", headers={"Origin": "https://evil.example"})).headers


async def test_health_stays_public_and_minimal(env: Env) -> None:
    resp = await env.http.get("/health")
    assert resp.status_code == 200 and CODE not in resp.text


# ------------------------------------------------------------------------------------------------ identidad
async def test_status_without_identity(env: Env) -> None:
    body = (await env.api("GET", "/api/status")).json()
    assert body["identity"] == {"present": False, "public_key": None} and body["signer"]["state"] == "idle"
    assert (await env.api("GET", "/api/identity")).status_code == 404


async def test_create_identity_returns_only_the_public_key(env: Env) -> None:
    resp = await env.api("POST", "/api/identity")
    assert resp.status_code == 201 and set(resp.json()) == {"public_key"} and len(resp.json()["public_key"]) == 64
    assert (await env.api("GET", "/api/identity")).json() == resp.json()


async def test_import_identity_never_echoes_the_secret(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    expected = Keypair.from_hex(NSEC_HEX).public_hex
    with caplog.at_level(logging.DEBUG):
        resp = await env.api("PUT", "/api/identity", json={"secret": NSEC_HEX})
    assert resp.status_code == 200 and resp.json() == {"public_key": expected}
    assert NSEC_HEX not in resp.text and NSEC_HEX not in caplog.text
    assert NSEC_HEX not in (await env.api("GET", "/api/status")).text


@pytest.mark.parametrize("body", [{"secret": "zz" * 32}, {"secret": "nsec1" + "q" * 58}, {"secret": "0" * 64}, {"secret": "short"}])
async def test_invalid_key_is_a_generic_400_or_422_without_echo(env: Env, body: dict[str, str]) -> None:
    resp = await env.api("PUT", "/api/identity", json=body)
    assert resp.status_code in (400, 422) and body["secret"] not in resp.text


@pytest.mark.parametrize("body", [{}, {"secret": 5}, {"secret": NSEC_HEX, "extra": 1}, {"secret": "x" * 201}, [], "text"])
async def test_validation_errors_do_not_echo_input(env: Env, body: object) -> None:
    resp = await env.api("PUT", "/api/identity", json=body)
    assert resp.status_code == 422 and resp.json()["detail"] == "solicitud invalida" and "input" not in resp.text and NSEC_HEX not in resp.text


async def test_secret_is_not_leaked_when_the_body_is_not_json(env: Env) -> None:
    resp = await env.http.put("/api/identity", content=NSEC_HEX, headers={**env.auth, "Content-Type": "application/json"})
    assert resp.status_code == 422 and NSEC_HEX not in resp.text


async def test_identity_cannot_change_while_running(env: Env) -> None:
    await start_signer(env)
    assert (await env.api("POST", "/api/identity")).status_code == 409
    assert (await env.api("PUT", "/api/identity", json={"secret": NSEC_HEX})).status_code == 409


# ------------------------------------------------------------------------------------------------ firmante
async def test_start_requires_identity_and_stop_requires_running(env: Env) -> None:
    assert (await env.api("POST", "/api/signer/start")).status_code == 409
    assert (await env.api("POST", "/api/signer/stop")).status_code == 409
    assert (await env.api("POST", "/api/connections")).status_code == 409


async def test_start_stop_cycle_and_double_start(env: Env) -> None:
    await start_signer(env)
    assert (await env.api("GET", "/api/signer")).json()["state"] == "ready"
    assert (await env.api("POST", "/api/signer/start")).status_code == 409
    stopped = await env.api("POST", "/api/signer/stop")
    assert stopped.status_code == 200 and stopped.json()["state"] == "stopped" and stopped.json()["end_reason"] == "detenido_por_el_operador"
    assert (await env.api("POST", "/api/connections")).status_code == 409
    await start_signer_again(env)


async def start_signer_again(env: Env) -> None:
    assert (await env.api("POST", "/api/signer/start")).status_code == 200 and len(env.relays) == 2  # un relay NUEVO por sesión
    assert (await env.api("POST", "/api/signer/stop")).status_code == 200


async def test_start_failure_is_a_generic_502() -> None:
    app = create_app(Settings(), access_code=CODE, relay_factory=lambda _s: FakeRelay(fail_connect=True), announce_code=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
            auth = await login(http)
            await http.post("/api/identity", headers=auth)
            resp = await http.post("/api/signer/start", headers=auth)
    assert resp.status_code == 502 and "relay.test" not in resp.text


# ------------------------------------------------------------------------------------------------ conexiones, solicitudes y flujo completo
async def test_bunker_uri_is_returned_once_with_no_store_and_never_logged(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    await start_signer(env)
    with caplog.at_level(logging.DEBUG):
        resp = await env.api("POST", "/api/connections")
    body = resp.json()
    assert resp.status_code == 201 and resp.headers["cache-control"] == "no-store" and set(body) == {"uri", "expires_in_s", "relay"}
    uri = parse_bunker_uri(body["uri"])
    assert uri.relays == ("wss://relay.primal.net",) and uri.signer_pubkey != (await env.api("GET", "/api/identity")).json()["public_key"]
    secret = body["uri"].split("secret=")[1]
    assert secret not in caplog.text and secret not in (await env.api("GET", "/api/audit")).text
    assert secret not in (await env.api("GET", "/api/status")).text and body["uri"] not in (await env.api("GET", "/api/signer")).text


async def test_unused_uri_limit_is_429(env: Env) -> None:
    await start_signer(env)
    codes = [(await env.api("POST", "/api/connections")).status_code for _ in range(4)]
    assert codes == [201, 201, 201, 429]


@pytest.mark.parametrize("path", ["/api/requests/%20/approve", "/api/requests/a b/approve", "/api/requests/" + "a" * 33 + "/approve",
                                  "/api/requests/..%2f/approve", "/api/requests/a;b/deny"])
async def test_request_ids_are_validated(env: Env, path: str) -> None:
    await start_signer(env)
    assert (await env.api("POST", path)).status_code in (404, 405, 422)  # 405: la ruta normalizada cae en la interfaz estatica (solo GET)


async def test_unknown_request_is_404_and_scope_is_validated(env: Env) -> None:
    assert (await env.api("POST", "/api/requests/nope/approve")).status_code == 404  # sin firmante
    await start_signer(env)
    assert (await env.api("POST", "/api/requests/nope/approve")).status_code == 404
    assert (await env.api("POST", "/api/requests/nope/deny")).status_code == 404
    assert (await env.api("GET", "/api/requests", params={"scope": "x"})).status_code == 422
    assert (await env.api("GET", "/api/requests")).json() == []


async def test_full_login_through_the_api_with_an_ndk_like_client(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    identity_pub = await start_signer(env)
    runtime = env.app_state
    with caplog.at_level(logging.DEBUG):
        uri = (await env.api("POST", "/api/connections")).json()["uri"]
        parsed = parse_bunker_uri(uri)
        secret = uri.split("secret=")[1]
        client = NdkLikeClient(parsed.signer_pubkey, runtime.now)  # type: ignore[attr-defined]
        env.relay.inject(RelayEvent(client.request("connect", ["", secret], scheme="nip04", created_at=int(runtime.now()))))  # type: ignore[attr-defined]
        await env.wait_for(lambda: runtime.service.approvals.pending() != [])  # type: ignore[attr-defined]
        pending = (await env.api("GET", "/api/requests")).json()
        assert len(pending) == 1 and pending[0]["kind"] == "connect" and pending[0]["status"] == "pending" and 0 < pending[0]["expires_in_s"] <= 5
        assert (await env.api("POST", f"/api/requests/{pending[0]['id']}/approve")).json()["status"] == "approved"
        assert (await env.api("POST", f"/api/requests/{pending[0]['id']}/approve")).status_code == 409
        await env.wait_for(lambda: len(env.relay.published) == 1)
        assert client.decode(env.relay.published[0]).result == "ack"

        now = int(runtime.now())  # type: ignore[attr-defined]
        env.relay.inject(RelayEvent(client.request("sign_event", [login_template(identity_pub, now=now)], created_at=now)))
        await env.wait_for(lambda: runtime.service.approvals.pending() != [])  # type: ignore[attr-defined]
        sign_req = (await env.api("GET", "/api/requests")).json()[0]
        assert sign_req["kind"] == "sign_event" and all(c["ok"] for c in sign_req["checks"]) and len(sign_req["checks"]) == 11
        assert (await env.api("POST", f"/api/requests/{sign_req['id']}/approve")).status_code == 200
        await env.wait_for(lambda: len(env.relay.published) == 2)
        signed = json.loads(client.decode(env.relay.published[1]).result)
        assert signed["pubkey"] == identity_pub and signed["kind"] == 27235

    status = (await env.api("GET", "/api/status")).json()["signer"]
    assert status["signatures"] == 1 and status["connections_active"] == 1
    recent = (await env.api("GET", "/api/requests", params={"scope": "recent"})).json()
    assert [r["status"] for r in recent] == ["approved", "approved"]
    everything = (await env.api("GET", "/api/requests", params={"scope": "all"})).text
    blob = caplog.text + (await env.api("GET", "/api/audit")).text + everything + json.dumps(status)
    assert all(x not in blob for x in (secret, "ab" * 32, signed["sig"], client.key.public_hex)) and "bunker://" not in blob


async def test_audit_limit_and_content(env: Env) -> None:
    await start_signer(env)
    entries = (await env.api("GET", "/api/audit")).json()["entries"]
    assert [e["event"] for e in entries][:2] == ["session_start", "relay_ready"]
    assert len((await env.api("GET", "/api/audit", params={"limit": 1})).json()["entries"]) == 1
    for bad in (0, 501, "x"):
        assert (await env.api("GET", "/api/audit", params={"limit": bad})).status_code == 422


async def test_app_shutdown_records_session_end() -> None:
    relays: list[FakeRelay] = []

    def factory(_s: Settings) -> FakeRelay:
        relays.append(FakeRelay())
        return relays[-1]

    app = create_app(Settings(), access_code=CODE, relay_factory=factory, announce_code=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
            auth = await login(http)
            await http.post("/api/identity", headers=auth)
            await http.post("/api/signer/start", headers=auth)
    runtime = app.state.runtime
    last = runtime.audit.entries()[-1]
    assert last["event"] == "session_end" and last["reason"] == "apagado_de_la_aplicacion" and relays[0].closed


async def test_token_is_announced_once_on_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(Settings(), access_code=CODE)
    async with app.router.lifespan_context(app):
        pass
    out = capsys.readouterr().out
    assert out.count(CODE) == 1 and "Codigo de acceso" in out

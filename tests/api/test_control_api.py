import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.nostr.keys import Keypair
from app.nostr.nip46 import parse_bunker_uri
from app.nostr.relay import RelayEvent
from app.security.operator_auth import MAX_TOKEN_FAILURES
from tests.support import PASSWORD, USERNAME, FakeRelay, NdkLikeClient, fast_passwords, login_template, make_settings

pytestmark = pytest.mark.anyio
CODE = PASSWORD  # la contraseña (ficticia) nunca debe aparecer en las respuestas


async def login(http: httpx.AsyncClient) -> dict[str, str]:
    resp = await http.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD, "return_token": True})
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
async def env(tmp_path: Path) -> AsyncIterator[Env]:
    relays: list[FakeRelay] = []

    def factory(_settings: Settings) -> FakeRelay:
        relays.append(FakeRelay())
        return relays[-1]

    app = create_app(make_settings(tmp_path, approval_ttl_s=5), relay_factory=factory, passwords=fast_passwords())
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
             ("POST", "/api/requests/abc/approve"), ("POST", "/api/requests/abc/deny"), ("GET", "/api/audit"), ("DELETE", "/api/connections/abcdefghijkl")]


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer " + "x" * 43}, {"Authorization": CODE}, {"Authorization": "Basic abc"},
                                     {"Authorization": f"Bearer {CODE} "}, {"Authorization": f"bearer {CODE}"}])
async def test_every_endpoint_denies_by_default(env: Env, method: str, path: str, headers: dict[str, str]) -> None:
    resp = await env.http.request(method, path, headers=headers)
    assert resp.status_code in (401, 429) and "Bearer" not in resp.text and CODE not in resp.text


async def test_repeated_invalid_tokens_are_rate_limited_but_a_valid_token_still_works(env: Env) -> None:
    bad = {"Authorization": "Bearer " + "x" * 43}
    codes = [(await env.http.get("/api/status", headers=bad)).status_code for _ in range(MAX_TOKEN_FAILURES + 2)]
    assert codes[0] == 401 and codes[-1] == 429
    assert (await env.http.get("/api/status", headers=env.auth)).status_code == 200  # un token valido nunca se frena
    assert (await env.http.get("/api/status", headers=bad)).status_code == 429


async def test_anonymous_requests_are_never_rate_limited(env: Env) -> None:
    """P-35: la sonda normal de la interfaz (sin credenciales) devuelve 401 siempre; no cuenta como fallo ni produce 429."""
    codes = {(await env.http.get(path)).status_code for path in ("/api/status", "/api/auth/session", "/api/requests", "/api/audit") for _ in range(15)}
    assert codes == {401}
    assert (await env.http.get("/api/status", headers=env.auth)).status_code == 200


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


async def test_start_failure_is_a_generic_502(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), relay_factory=lambda _s: FakeRelay(fail_connect=True), passwords=fast_passwords())
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


@pytest.mark.parametrize("violation", [{"origin": "https://evil.example"}, {"kind": 1}, {"content": "otro texto"}, {"age": 500}])
async def test_a_policy_violating_request_never_exists_so_it_cannot_be_approved_through_the_api(env: Env, violation: dict[str, object]) -> None:
    """P-37 (backend): una solicitud que incumple la politica ni siquiera llega a la cola del operador; aprobar por la API es imposible y no se firma."""
    identity_pub = await start_signer(env)
    runtime = env.app_state
    uri = (await env.api("POST", "/api/connections")).json()["uri"]
    client = NdkLikeClient(parse_bunker_uri(uri).signer_pubkey, runtime.now)  # type: ignore[attr-defined]
    now = int(runtime.now())  # type: ignore[attr-defined]
    env.relay.inject(RelayEvent(client.request("connect", ["", uri.split("secret=")[1]], scheme="nip04", created_at=now)))
    await env.wait_for(lambda: runtime.service.approvals.pending() != [])  # type: ignore[attr-defined]
    connect_id = (await env.api("GET", "/api/requests")).json()[0]["id"]
    assert (await env.api("POST", f"/api/requests/{connect_id}/approve")).status_code == 200
    await env.wait_for(lambda: len(env.relay.published) == 1)

    env.relay.inject(RelayEvent(client.request("sign_event", [login_template(identity_pub, now=now, **violation)], created_at=now)))  # type: ignore[arg-type]
    await env.wait_for(lambda: len(env.relay.published) == 2)
    assert client.decode(env.relay.published[1]).error == "unauthorized"
    listing = (await env.api("GET", "/api/requests", params={"scope": "all"})).json()
    assert [r["kind"] for r in listing] == ["connect"]  # la firma incumplida jamas aparecio como solicitud
    for fake_id in ("x" * 12, connect_id, "sign_event", "0" * 12):
        assert (await env.api("POST", f"/api/requests/{fake_id}/approve")).status_code in (404, 409)
    status = (await env.api("GET", "/api/status")).json()["signer"]
    assert status["signatures"] == 0 and status["pending"] == 0
    assert not [e for e in (await env.api("GET", "/api/audit")).json()["entries"] if e["event"] == "sign_ok"]
    assert len(env.relay.published) == 2  # nada mas se publico


@pytest.fixture
async def short_window_env(tmp_path: Path) -> AsyncIterator[Env]:
    """Como `env`, pero con SIGNER_WINDOW_S = 1: una aprobacion de mas de 2 s llega con la plantilla ya fuera de la ventana."""
    relays: list[FakeRelay] = []

    def factory(_settings: Settings) -> FakeRelay:
        relays.append(FakeRelay())
        return relays[-1]

    app = create_app(make_settings(tmp_path, approval_ttl_s=10, window_s=1), relay_factory=factory, passwords=fast_passwords())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
            yield Env(http, await login(http), relays, app.state.runtime)


async def _connected_client(env: Env) -> tuple[str, NdkLikeClient]:
    identity_pub = await start_signer(env)
    runtime = env.app_state
    uri = (await env.api("POST", "/api/connections")).json()["uri"]
    client = NdkLikeClient(parse_bunker_uri(uri, allow_insecure_relays=True).signer_pubkey, runtime.now)  # type: ignore[attr-defined]
    env.relay.inject(RelayEvent(client.request("connect", ["", uri.split("secret=")[1]], scheme="nip04", created_at=int(runtime.now()))))  # type: ignore[attr-defined]
    await env.wait_for(lambda: runtime.service.approvals.pending() != [])  # type: ignore[attr-defined]
    assert (await env.api("POST", f"/api/requests/{(await env.api('GET', '/api/requests')).json()[0]['id']}/approve")).status_code == 200
    await env.wait_for(lambda: len(env.relay.published) == 1)
    return identity_pub, client


async def test_requests_endpoint_reports_the_real_signing_outcome_signed(env: Env) -> None:
    """P-42: aprobada -> sin resultado -> firmada, tal como lo consume la interfaz."""
    identity_pub, client = await _connected_client(env)
    runtime = env.app_state
    now = int(runtime.now())  # type: ignore[attr-defined]
    env.relay.inject(RelayEvent(client.request("sign_event", [login_template(identity_pub, now=now)], created_at=now)))
    await env.wait_for(lambda: runtime.service.approvals.pending() != [])  # type: ignore[attr-defined]
    pending = (await env.api("GET", "/api/requests")).json()[0]
    assert pending["status"] == "pending" and pending["outcome"] is None and pending["outcome_reason"] is None
    assert isinstance(pending["sign_expires_in_s"], int) and 100 < pending["sign_expires_in_s"] <= 121 and pending["expires_in_s"] <= 5  # plazo de firma (politica) != TTL de aprobacion
    approved = await env.api("POST", f"/api/requests/{pending['id']}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"  # la respuesta inmediata NO afirma que haya firma
    await env.wait_for(lambda: len(env.relay.published) == 2)
    final = next(r for r in (await env.api("GET", "/api/requests", params={"scope": "recent"})).json() if r["kind"] == "sign_event")
    assert (final["status"], final["outcome"], final["outcome_reason"]) == ("approved", "signed", None)
    connect = next(r for r in (await env.api("GET", "/api/requests", params={"scope": "recent"})).json() if r["kind"] == "connect")
    assert connect["status"] == "approved" and connect["outcome"] is None  # connect: sin cambios


async def test_requests_endpoint_reports_a_revalidation_refusal_as_refused_not_as_a_signature(short_window_env: Env) -> None:
    env = short_window_env
    identity_pub, client = await _connected_client(env)
    now = int(time.time())
    # El reloj del firmante es el real (`runtime.now`): la plantilla nace con la hora actual y el operador tarda mas que la ventana de 1 s.
    env.relay.inject(RelayEvent(client.request("sign_event", [login_template(identity_pub, now=now)], created_at=now)))
    await env.wait_for(lambda: env.app_state.service.approvals.pending() != [])  # type: ignore[attr-defined]
    request_id = (await env.api("GET", "/api/requests")).json()[0]["id"]
    await asyncio.sleep(2.3)
    assert (await env.api("POST", f"/api/requests/{request_id}/approve")).status_code == 200  # el operador SI aprobo...
    await env.wait_for(lambda: len(env.relay.published) == 2)
    assert client.decode(env.relay.published[1]).error == "unauthorized"
    final = next(r for r in (await env.api("GET", "/api/requests", params={"scope": "recent"})).json() if r["kind"] == "sign_event")
    assert (final["status"], final["outcome"], final["outcome_reason"]) == ("approved", "refused", "politica_incumplida")  # ...pero NO hubo firma
    status = (await env.api("GET", "/api/status")).json()["signer"]
    assert status["signatures"] == 0
    text = json.dumps(final)
    assert "ab" * 32 not in text and identity_pub not in text and "sig" not in final  # sin reto, claves ni plantilla
    assert not [e for e in (await env.api("GET", "/api/audit")).json()["entries"] if e["event"] == "sign_ok"]


async def test_audit_limit_and_content(env: Env) -> None:
    await start_signer(env)
    entries = (await env.api("GET", "/api/audit")).json()["entries"]
    assert [e["event"] for e in entries][:2] == ["session_start", "relay_ready"]
    assert len((await env.api("GET", "/api/audit", params={"limit": 1})).json()["entries"]) == 1
    for bad in (0, 501, "x"):
        assert (await env.api("GET", "/api/audit", params={"limit": bad})).status_code == 422


async def test_app_shutdown_records_session_end(tmp_path: Path) -> None:
    relays: list[FakeRelay] = []

    def factory(_s: Settings) -> FakeRelay:
        relays.append(FakeRelay())
        return relays[-1]

    app = create_app(make_settings(tmp_path), relay_factory=factory, passwords=fast_passwords())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
            auth = await login(http)
            await http.post("/api/identity", headers=auth)
            await http.post("/api/signer/start", headers=auth)
    runtime = app.state.runtime
    last = runtime.audit.entries()[-1]
    assert last["event"] == "session_end" and last["reason"] == "apagado_de_la_aplicacion" and relays[0].closed


async def test_startup_prints_no_credential_and_no_access_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """D-9: ya no existe el código de acceso de la terminal; ninguna credencial se imprime al arrancar."""
    app = create_app(make_settings(tmp_path), passwords=fast_passwords())
    async with app.router.lifespan_context(app):
        pass
    captured = capsys.readouterr()
    assert PASSWORD not in captured.out + captured.err and "Codigo de acceso" not in captured.out + captured.err


# ------------------------------------------------------------------------------------------------ D-17, componente 1: revocación individual
async def pair_client(env: Env) -> NdkLikeClient:
    """Empareja un cliente por la API: URI, `connect` NIP-04 y aprobación humana (aquí, la llamada autenticada a /approve)."""
    runtime = env.app_state
    uri = (await env.api("POST", "/api/connections")).json()["uri"]
    client = NdkLikeClient(parse_bunker_uri(uri).signer_pubkey, runtime.now)  # type: ignore[attr-defined]
    before = len(env.relay.published)
    env.relay.inject(RelayEvent(client.request("connect", ["", uri.split("secret=")[1]], scheme="nip04", created_at=int(runtime.now()))))  # type: ignore[attr-defined]
    await env.wait_for(lambda: runtime.service.approvals.pending() != [])  # type: ignore[attr-defined]
    pending = (await env.api("GET", "/api/requests")).json()
    assert (await env.api("POST", f"/api/requests/{pending[0]['id']}/approve")).status_code == 200
    await env.wait_for(lambda: len(env.relay.published) > before)
    return client


async def call_client(env: Env, client: NdkLikeClient, method: str, params: list[str] | None = None) -> object:
    before = len(env.relay.published)
    env.relay.inject(RelayEvent(client.request(method, params or [], created_at=int(env.app_state.now()))))  # type: ignore[attr-defined]
    await env.wait_for(lambda: len(env.relay.published) > before)
    return client.decode(env.relay.published[-1])


def connection_of(listing: list[dict[str, object]], client: NdkLikeClient) -> dict[str, object]:
    return next(c for c in listing if c["client"] == client.key.public_hex[:8])


async def test_the_connections_listing_exposes_only_opaque_ids_and_truncated_clients(env: Env) -> None:
    await start_signer(env)
    a, b = await pair_client(env), await pair_client(env)
    listing = (await env.api("GET", "/api/connections")).json()
    assert len(listing) == 2 and {c["state"] for c in listing} == {"active"}
    ids = [str(c["id"]) for c in listing]
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{12}", i) for i in ids) and len(set(ids)) == 2
    blob = json.dumps(listing)
    assert a.key.public_hex not in blob and b.key.public_hex not in blob and all(len(str(c["client"])) == 8 for c in listing)
    assert not any(str(c["id"]) in str(c["client"]) or str(c["client"]) in str(c["id"]) for c in listing)  # el id no deriva de la clave


async def test_revoking_through_the_api_is_immediate_isolated_and_a_repeat_is_409(env: Env) -> None:
    await start_signer(env)
    a, b = await pair_client(env), await pair_client(env)
    listing = (await env.api("GET", "/api/connections")).json()
    id_a = str(connection_of(listing, a)["id"])
    out = await env.api("DELETE", f"/api/connections/{id_a}")
    assert out.status_code == 200 and out.json() == {"id": id_a, "client": a.key.public_hex[:8], "state": "revoked", "expires_in_s": 0}
    again = await env.api("DELETE", f"/api/connections/{id_a}")
    assert again.status_code == 409 and again.json() == {"detail": "la conexion ya no esta activa"}  # revocación repetida
    states = {c["client"]: c["state"] for c in (await env.api("GET", "/api/connections")).json()}
    assert states == {a.key.public_hex[:8]: "revoked", b.key.public_hex[:8]: "active"}
    assert getattr(await call_client(env, a, "get_public_key"), "error") == "unauthorized"  # el revocado, rechazado al instante
    assert getattr(await call_client(env, b, "get_public_key"), "error") is None  # la otra conexión sigue activa
    assert (await env.api("GET", "/api/status")).json()["signer"]["connections_active"] == 1


@pytest.mark.parametrize("bad", ["a" * 33, "a.b", "con espacio", "id$malo"])
async def test_a_malformed_connection_id_is_a_422_and_an_unknown_one_a_404(env: Env, bad: str) -> None:
    await start_signer(env)
    assert (await env.api("DELETE", f"/api/connections/{bad}")).status_code == 422
    unknown = await env.api("DELETE", "/api/connections/ZZZZZZZZZZZZ")
    assert unknown.status_code == 404 and unknown.json() == {"detail": "conexion desconocida"}


async def test_revoking_without_a_signer_session_is_a_404_and_an_id_from_a_previous_session_is_not_valid(env: Env) -> None:
    assert (await env.api("DELETE", "/api/connections/ZZZZZZZZZZZZ")).status_code == 404  # sin firmante: no hay conexiones
    await start_signer(env)
    a = await pair_client(env)
    id_a = str(connection_of((await env.api("GET", "/api/connections")).json(), a)["id"])
    assert (await env.api("POST", "/api/signer/stop")).status_code == 200  # la detención manual revoca todo
    assert (await env.api("DELETE", f"/api/connections/{id_a}")).status_code == 409
    assert (await env.api("POST", "/api/signer/start")).status_code == 200
    assert (await env.api("DELETE", f"/api/connections/{id_a}")).status_code == 404  # tras reiniciar, el id de la sesión anterior ya no existe


async def test_revoking_cancels_the_pending_signature_of_that_connection_only(env: Env) -> None:
    identity_pub = await start_signer(env)
    runtime = env.app_state
    a, b = await pair_client(env), await pair_client(env)
    now = int(runtime.now())  # type: ignore[attr-defined]
    env.relay.inject(RelayEvent(a.request("sign_event", [login_template(identity_pub, now=now)], created_at=now)))
    env.relay.inject(RelayEvent(b.request("sign_event", [login_template(identity_pub, now=now, challenge="cd" * 32)], created_at=now)))
    await env.wait_for(lambda: len(runtime.service.approvals.pending()) == 2)  # type: ignore[attr-defined]
    listing = (await env.api("GET", "/api/connections")).json()
    assert (await env.api("DELETE", f"/api/connections/{connection_of(listing, a)['id']}")).status_code == 200
    requests = {r["client"]: r for r in (await env.api("GET", "/api/requests", params={"scope": "all"})).json() if r["kind"] == "sign_event"}
    assert requests[a.key.public_hex[:8]]["status"] == "cancelled" and requests[b.key.public_hex[:8]]["status"] == "pending"
    b_req = requests[b.key.public_hex[:8]]
    assert (await env.api("POST", f"/api/requests/{b_req['id']}/approve")).status_code == 200  # la de B sigue necesitando (y recibe) su aprobación humana
    await env.wait_for(lambda: runtime.service.signatures == 1)  # type: ignore[attr-defined]


async def test_the_revocation_is_audited_through_the_api_without_secrets(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    await start_signer(env)
    a = await pair_client(env)
    id_a = str(connection_of((await env.api("GET", "/api/connections")).json(), a)["id"])
    with caplog.at_level(logging.DEBUG):
        await env.api("DELETE", f"/api/connections/{id_a}")
        audit = (await env.api("GET", "/api/audit")).text
    entry = [e for e in json.loads(audit)["entries"] if e["event"] == "connection_revoked"]
    assert len(entry) == 1 and entry[0]["conn8"] == id_a[:8] and entry[0]["cancelled"] == 0
    app_logs = "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))  # el cliente httpx de la prueba registra la ruta HTTP (el id es opaco y solo sirve con JWT y CSRF)
    assert id_a not in audit and a.key.public_hex not in audit and id_a not in app_logs and a.key.public_hex not in caplog.text


async def test_the_status_reports_no_total_signature_cap_in_continuous_mode(env: Env) -> None:
    status = (await env.api("GET", "/api/status")).json()["signer"]
    assert status["max_signatures"] is None  # el modo continuo es el predeterminado: sin tope total de firmas (cada firma exige aprobación humana)
    await start_signer(env)
    assert (await env.api("GET", "/api/status")).json()["signer"]["max_signatures"] is None

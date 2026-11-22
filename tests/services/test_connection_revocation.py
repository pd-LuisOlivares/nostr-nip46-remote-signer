"""D-17, Componente 1: revocación individual de conexiones (identificadores opacos, aislamiento, cancelación de pendientes, repetición y concurrencia).

Con `FakeRelay` y reloj inyectado: sin red. Cada `connect` y cada `sign_event` siguen exigiendo la aprobación humana individual.
"""
import asyncio
import json
import re
from typing import Any

import pytest

from app.config import Settings
from app.services.approvals import PendingRequest, RequestStatus
from app.services.connections import ClientState, ConnectionManager, ConnectionNotActive, UnknownConnection
from tests.services.test_continuous_lifecycle import Harness
from tests.support import CHALLENGE, Clock, NdkLikeClient, Rig, login_template, make_rig

pytestmark = pytest.mark.anyio

OTHER = "cd" * 32
ID_FORMAT = re.compile(r"[A-Za-z0-9_-]{12}")


def conn_id(rig: Rig, client: NdkLikeClient) -> str:
    cid = rig.connections.id_of(client.key.public_hex)
    assert cid is not None
    return cid


async def send_sign(rig: Rig, client: NdkLikeClient, challenge: str = CHALLENGE) -> PendingRequest:
    """Envía un `sign_event` y devuelve LA solicitud pendiente nueva (aún sin decidir)."""
    known = {r.id for r in rig.approvals.pending()}
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=challenge)]))
    await rig.wait_for(lambda: any(r.id not in known for r in rig.approvals.pending()))
    return next(r for r in rig.approvals.pending() if r.id not in known)


async def two_clients(rig: Rig) -> tuple[NdkLikeClient, NdkLikeClient]:
    return await rig.connect_client(), await rig.connect_client()


# ------------------------------------------------------------------------------------------------ identificadores opacos
async def test_connection_ids_are_random_opaque_unique_and_unrelated_to_the_client_key() -> None:
    clock = Clock()
    first, second = ConnectionManager(now=clock, secret_ttl_s=300, connection_ttl_s=60), ConnectionManager(now=clock, secret_ttl_s=300, connection_ttl_s=60)
    clients = [f"{n:02x}" * 32 for n in range(1, 40)]
    for client in clients:
        first.begin(client)
        second.begin(client)
    ids = [first.id_of(c) for c in clients]
    assert all(i is not None and ID_FORMAT.fullmatch(i) for i in ids) and len(set(ids)) == len(clients)
    assert [first.id_of(c) for c in clients] != [second.id_of(c) for c in clients]  # aleatorios: el mismo cliente recibe otro id en otro estado
    assert not any(c[:12] in str(first.id_of(c)) or str(first.id_of(c)) in c for c in clients)  # sin relación con la clave
    assert first.id_of("ff" * 32) is None


async def test_a_new_pairing_gets_a_new_id_and_forgotten_pending_clients_lose_theirs() -> None:
    manager = ConnectionManager(now=Clock(), secret_ttl_s=300, connection_ttl_s=60)
    manager.begin("aa" * 32)
    old = manager.id_of("aa" * 32)
    manager.begin("aa" * 32)
    assert manager.id_of("aa" * 32) != old and old is not None
    with pytest.raises(UnknownConnection):
        manager.revoke(old)  # el id anterior ya no es válido
    manager.forget_pending()
    assert manager.id_of("aa" * 32) is None


# ------------------------------------------------------------------------------------------------ revocar: efecto inmediato y aislamiento
async def test_a_revoked_connection_is_rejected_immediately_and_the_others_are_not_affected() -> None:
    rig = await make_rig()
    a, b = await two_clients(rig)
    rig.service.revoke_connection(conn_id(rig, a))
    assert rig.connections.state_of(a.key.public_hex) is ClientState.REVOKED
    assert (await rig.exchange(a, "get_public_key", [])).error == "unauthorized"
    assert (await rig.exchange(a, "ping", [])).error == "unauthorized"
    resp = await rig.exchange(a, "sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()))])
    assert resp.error == "unauthorized" and rig.approvals.pending() == [] and rig.service.signatures == 0  # ni siquiera se ofrece a una persona
    assert (await rig.exchange(b, "get_public_key", [])).result == rig.identity.public_hex  # la otra conexión sigue activa
    assert rig.connections.is_active(b.key.public_hex)
    await rig.stop()


async def test_the_surviving_connection_still_needs_a_human_approval_for_each_signature() -> None:
    rig = await make_rig()
    a, b = await two_clients(rig)
    rig.service.revoke_connection(conn_id(rig, a))
    req = await send_sign(rig, b)
    before = len(rig.relay.published)
    await asyncio.sleep(0.05)
    assert len(rig.relay.published) == before and req.status is RequestStatus.PENDING and rig.service.signatures == 0  # nada se firma sin decisión humana
    rig.approvals.resolve(req.id, True)
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    assert b.decode(rig.relay.published[-1]).error is None and rig.service.signatures == 1
    await rig.stop()


async def test_a_revoked_client_cannot_pair_again_with_the_same_key_until_p47_is_approved() -> None:
    """P-47 NO está aprobada: un cliente revocado queda bloqueado (comportamiento anterior). Un cliente NUEVO sí puede emparejarse, con aprobación humana."""
    rig = await make_rig(signer_mode="continuous")
    a = await rig.connect_client()
    rig.service.revoke_connection(conn_id(rig, a))
    secret = rig.service.issue_bunker_uri().split("secret=")[1]
    before = len(rig.relay.published)
    await rig.send(a.request("connect", ["", secret], scheme="nip04"))
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    assert a.decode(rig.relay.published[-1]).error == "unauthorized" and rig.approvals.pending() == []  # no se ofrece ninguna tarjeta
    fresh = await rig.connect_client()  # una clave de cliente nueva se empareja con la aprobación humana de siempre
    assert rig.connections.is_active(fresh.key.public_hex) and not rig.connections.is_active(a.key.public_hex)
    await rig.stop()


# ------------------------------------------------------------------------------------------------ cancelación de pendientes
async def test_revoking_cancels_only_the_pending_requests_of_that_connection() -> None:
    rig = await make_rig()
    a, b = await two_clients(rig)
    req_a = await send_sign(rig, a, CHALLENGE)
    req_b = await send_sign(rig, b, OTHER)
    before = len(rig.relay.published)
    rig.service.revoke_connection(conn_id(rig, a))
    assert req_a.status is RequestStatus.CANCELLED and req_a.reason == "conexion_revocada" and req_b.status is RequestStatus.PENDING
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    assert a.decode(rig.relay.published[-1]).error == "unauthorized"  # el cliente revocado recibe la denegación de su solicitud cancelada
    rig.approvals.resolve(req_b.id, True)
    await rig.wait_for(lambda: len(rig.relay.published) > before + 1)
    assert b.decode(rig.relay.published[-1]).error is None and rig.service.signatures == 1  # la solicitud de la otra conexión sigue su curso
    await rig.stop()


async def test_an_approval_given_just_before_the_revocation_signs_nothing() -> None:
    rig = await make_rig()
    a = await rig.connect_client()
    req = await send_sign(rig, a)
    rig.approvals.resolve(req.id, True)  # la persona aprobó...
    rig.service.revoke_connection(conn_id(rig, a))  # ...y la conexión se revoca ANTES de que se use la aprobación (sin ceder el control entre ambas)
    await rig.wait_for(lambda: req.outcome is not None)
    assert (req.outcome, req.outcome_reason) == ("refused", "cliente_no_activo") and rig.service.signatures == 0
    assert not [e for e in rig.audit.entries() if e["event"] == "sign_ok"]
    await rig.stop()


# ------------------------------------------------------------------------------------------------ errores: desconocida, repetida, no activa
async def test_unknown_repeated_pending_expired_and_stopped_connections_cannot_be_revoked() -> None:
    rig = await make_rig()
    a, b = await two_clients(rig)
    with pytest.raises(UnknownConnection):
        rig.service.revoke_connection("AAAAAAAAAAAA")
    id_a = conn_id(rig, a)
    rig.service.revoke_connection(id_a)
    with pytest.raises(ConnectionNotActive):
        rig.service.revoke_connection(id_a)  # revocación repetida: ya no está activa
    rig.connections.begin("ee" * 32)
    with pytest.raises(ConnectionNotActive):
        rig.service.revoke_connection(str(rig.connections.id_of("ee" * 32)))  # pendiente: se decide desde su tarjeta, no se «revoca»
    rig.clock.advance(1801)  # vence la conexión de B (CONNECTION_TTL_S del arnés supervisado)
    with pytest.raises(ConnectionNotActive):
        rig.service.revoke_connection(conn_id(rig, b))
    audit = [e for e in rig.audit.entries() if e["event"] == "connection_revoked"]
    assert len(audit) == 1  # solo la revocación efectiva deja evidencia
    await rig.stop()


async def test_the_audit_event_has_only_the_truncated_id_and_the_cancelled_count_and_no_secrets() -> None:
    rig = await make_rig()
    a = await rig.connect_client()
    req = await send_sign(rig, a)
    cid = conn_id(rig, a)
    rig.service.revoke_connection(cid)
    entry = next(e for e in rig.audit.entries() if e["event"] == "connection_revoked")
    assert set(entry) == {"seq", "ts", "event", "conn8", "cancelled"} and entry["conn8"] == cid[:8] and entry["cancelled"] == 1
    blob = json.dumps(rig.audit.entries())
    assert cid not in blob and a.key.public_hex not in blob  # ni el id completo ni la clave del cliente aparecen en NINGUNA entrada de la auditoría
    assert req.id not in json.dumps(entry)  # y la entrada de revocación no revela el identificador de la solicitud cancelada (el de `pending_created` ya existía)
    await rig.stop()


# ------------------------------------------------------------------------------------------------ concurrencia
async def test_concurrent_revocations_of_the_same_connection_succeed_exactly_once() -> None:
    rig = await make_rig()
    a, b = await two_clients(rig)
    cid = conn_id(rig, a)

    async def attempt() -> str:
        await asyncio.sleep(0)
        rig.service.revoke_connection(cid)
        return "revocada"

    results: list[Any] = await asyncio.gather(*(attempt() for _ in range(20)), return_exceptions=True)
    assert results.count("revocada") == 1 and sum(isinstance(r, ConnectionNotActive) for r in results) == 19
    assert len([e for e in rig.audit.entries() if e["event"] == "connection_revoked"]) == 1 and rig.connections.is_active(b.key.public_hex)
    await rig.stop()


async def test_revocations_of_different_connections_run_concurrently_without_interfering() -> None:
    rig = await make_rig()
    clients = [await rig.connect_client() for _ in range(3)]
    survivors = clients[2:]
    ids = [conn_id(rig, c) for c in clients[:2]]

    async def revoke(cid: str) -> None:
        await asyncio.sleep(0)
        rig.service.revoke_connection(cid)

    await asyncio.gather(*(revoke(i) for i in ids))
    assert [rig.connections.is_active(c.key.public_hex) for c in clients] == [False, False, True]
    assert (await rig.exchange(survivors[0], "get_public_key", [])).error is None
    await rig.stop()


async def test_a_revocation_racing_with_a_new_request_never_lets_it_through() -> None:
    rig = await make_rig()
    a = await rig.connect_client()
    cid = conn_id(rig, a)
    before = len(rig.relay.published)
    await rig.send(a.request("get_public_key", []))  # la solicitud ya está en la cola del relay...
    rig.service.revoke_connection(cid)  # ...y la revocación llega antes de que se procese
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    assert a.decode(rig.relay.published[-1]).error == "unauthorized"
    await rig.stop()


# ------------------------------------------------------------------------------------------------ runtime: revocar con el firmante caído o detenido
async def test_a_connection_kept_after_a_relay_failure_can_still_be_revoked() -> None:
    h = Harness("continuous")
    rig = await h.start()
    a, b = await two_clients(rig)
    await h.drop_relay(rig)
    assert not h.runtime.running
    h.runtime.revoke_connection(conn_id(rig, a))  # el firmante cayó, pero sus conexiones conservadas siguen siendo revocables
    resumed = await h.start()
    assert not resumed.connections.is_active(a.key.public_hex) and resumed.connections.is_active(b.key.public_hex)
    await h.runtime.stop()


async def test_after_a_manual_stop_everything_is_already_revoked_and_an_unknown_runtime_has_no_connections() -> None:
    h = Harness("continuous")
    rig = await h.start()
    a = await rig.connect_client()
    cid = conn_id(rig, a)
    await h.runtime.stop()
    with pytest.raises(ConnectionNotActive):
        h.runtime.revoke_connection(cid)
    other = Harness("continuous")  # un runtime que nunca arrancó
    with pytest.raises(UnknownConnection):
        other.runtime.revoke_connection(cid)
    with pytest.raises(UnknownConnection):
        h.runtime.revoke_connection("ZZZZZZZZZZZZ")  # el id de otro estado/runtime no existe aquí


def test_settings_default_is_not_used_by_these_tests() -> None:
    assert Settings().signer_mode == "continuous"  # los arneses fijan el modo de forma explícita

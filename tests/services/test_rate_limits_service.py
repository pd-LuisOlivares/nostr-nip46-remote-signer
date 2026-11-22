"""D-17, Componente 3: límites de frecuencia del firmante en modo `continuous` (30 por minuto y conexión, 120 globales), continuidad sin topes totales y modo `supervised` intacto.

Con `FakeRelay` y reloj inyectado: sin red. Un mensaje que supera un límite se DESCARTA (sin respuesta) y no detiene el firmante ni revoca nada. Cada `connect` y cada `sign_event`
siguen exigiendo la aprobación humana individual.
"""
import asyncio
import json
from typing import Any

import pytest

from app.services.approvals import RequestStatus
from app.services.connections import ClientState
from app.services.ratelimit import GLOBAL_REQUESTS_PER_MIN
from app.services.runtime import RECONNECT_BACKOFF_S
from app.services.signer import SignerState
from tests.services.test_continuous_lifecycle import Harness
from tests.services.test_reconnection import FakeSleep, drop, ready_again, wait_until
from tests.support import CHALLENGE, NdkLikeClient, Rig, login_template, make_rig

pytestmark = pytest.mark.anyio

CHUNK = 40  # el firmante atiende como mucho 64 manejadores a la vez: las ráfagas se envían por tandas para no mezclar ese otro límite


async def settle(rig: Rig) -> None:
    """Espera a que el relay falso entregue todo y los manejadores terminen."""
    calm = 0
    while calm < 3:
        await asyncio.sleep(0.003)
        calm = calm + 1 if rig.relay._queue.empty() and not rig.service._tasks else 0


async def burst(rig: Rig, client: NdkLikeClient, count: int, method: str = "ping") -> int:
    """Envía `count` solicitudes DISTINTAS de `client` y devuelve cuántas respuestas se publicaron."""
    before = len(rig.relay.published)
    for sent in range(count):
        await rig.send(client.request(method, []))
        if (sent + 1) % CHUNK == 0:
            await settle(rig)
    await settle(rig)
    return len(rig.relay.published) - before


def limited_events(rig: Rig) -> list[dict[str, Any]]:
    return [e for e in rig.audit.entries() if e["event"] == "rate_limited"]


async def continuous_rig(**overrides: Any) -> Rig:
    return await make_rig(signer_mode="continuous", **overrides)


# ------------------------------------------------------------------------------------------------ por conexión: 30 por minuto
async def test_a_connection_is_limited_to_30_requests_per_minute_without_stopping_the_signer_or_revoking() -> None:
    rig = await continuous_rig()
    client = await rig.connect_client()
    assert await burst(rig, client, 35) == 30  # las 30 primeras se responden; las 5 restantes se descartan
    events = limited_events(rig)
    assert len(events) == 1 and events[0]["scope"] == "conexion" and events[0]["limit"] == 30 and events[0]["client8"] == client.key.public_hex[:8]  # UNA auditoría
    assert rig.service.state is SignerState.READY and rig.connections.is_active(client.key.public_hex) and rig.service.signatures == 0
    assert not [e for e in rig.audit.entries() if e["event"] == "session_end"]
    assert client.key.public_hex not in json.dumps(rig.audit.entries())  # la auditoría solo tiene el prefijo de 8 caracteres
    await rig.stop()


async def test_the_quota_returns_when_the_window_moves_and_the_reset_is_exact() -> None:
    rig = await continuous_rig()
    client = await rig.connect_client()
    assert await burst(rig, client, 30) == 30 and await burst(rig, client, 1) == 0
    rig.clock.advance(59)
    assert await burst(rig, client, 1) == 0  # a los 59 s sigue limitada
    rig.clock.advance(1)  # 60 s desde las primeras: la ventana se «reinicia» para ellas
    assert await burst(rig, client, 31) == 30  # otra vez 30 y el 31.º se descarta
    await rig.stop()


async def test_the_window_slides_a_partial_return_of_quota() -> None:
    rig = await continuous_rig()
    client = await rig.connect_client()
    assert await burst(rig, client, 15) == 15  # t = 0
    rig.clock.advance(30)
    assert await burst(rig, client, 15) == 15  # t = 30: 30 en la ventana
    rig.clock.advance(29)
    assert await burst(rig, client, 1) == 0  # t = 59: limitada
    rig.clock.advance(1)  # t = 60: salen las 15 de t = 0 y solo esas
    assert await burst(rig, client, 16) == 15
    await rig.stop()


async def test_the_limit_of_one_connection_does_not_affect_the_others() -> None:
    rig = await continuous_rig()
    a, b = await rig.connect_client(), await rig.connect_client()
    assert await burst(rig, a, 31) == 30 and await burst(rig, a, 1) == 0
    assert await burst(rig, b, 10) == 10  # B no se ve afectada
    assert rig.connections.is_active(a.key.public_hex) and rig.connections.is_active(b.key.public_hex)
    await rig.stop()


async def test_the_per_connection_limit_follows_the_configuration() -> None:
    rig = await continuous_rig(requests_per_min=3)
    client = await rig.connect_client()
    assert await burst(rig, client, 5) == 3 and limited_events(rig)[0]["limit"] == 3
    await rig.stop()


async def test_duplicate_events_do_not_consume_the_connection_quota() -> None:
    rig = await continuous_rig()
    client = await rig.connect_client()
    event = client.request("ping", [])
    before = len(rig.relay.published)
    for _ in range(50):  # el relay reentrega el MISMO evento: se descarta como repetido, no cuenta como solicitud de la conexión
        await rig.send(event)
    await settle(rig)
    assert len(rig.relay.published) - before == 1
    assert await burst(rig, client, 30) == 29  # le quedaban 29 de 30
    await rig.stop()


# ------------------------------------------------------------------------------------------------ global: 120 por minuto, antes de descifrar
async def test_the_global_limit_is_120_per_minute_and_drops_the_excess_before_decrypting() -> None:
    assert GLOBAL_REQUESTS_PER_MIN == 120
    rig = await continuous_rig()
    before = len(rig.relay.published)
    for sent in range(130):  # 130 remitentes DISTINTOS y desconocidos: cada uno recibe `unauthorized`... hasta agotar el cupo global
        await rig.send(NdkLikeClient(rig.service.transport.public_hex, rig.clock).request("ping", []))
        if (sent + 1) % CHUNK == 0:
            await settle(rig)
    await settle(rig)
    assert len(rig.relay.published) - before == 120  # los 10 últimos se descartaron sin ser procesados
    events = limited_events(rig)
    assert len(events) == 1 and events[0]["scope"] == "global" and events[0]["limit"] == 120 and "client8" not in events[0]
    assert rig.service.state is SignerState.READY  # no se detiene
    rig.clock.advance(60)
    stranger = NdkLikeClient(rig.service.transport.public_hex, rig.clock)
    assert await burst(rig, stranger, 1) == 1  # y el cupo vuelve a los 60 s
    await rig.stop()


async def test_invalid_messages_also_count_against_the_global_limit_and_never_stop_the_signer() -> None:
    rig = await continuous_rig()
    for sent in range(100):  # mensajes inválidos: ni siquiera son eventos Nostr
        await rig.send({"id": "x", "garbage": sent})
        if (sent + 1) % CHUNK == 0:
            await settle(rig)
    await settle(rig)
    errors = [e for e in rig.audit.entries() if e["event"] == "error" and e["error_type"] == "evento_descartado"]
    assert len(errors) == 100 and not limited_events(rig)
    stranger_responses = 0
    for sent in range(30):
        stranger_responses += await burst(rig, NdkLikeClient(rig.service.transport.public_hex, rig.clock), 1)
    assert stranger_responses == 20  # 100 inválidos + 20 válidos = 120: el resto se descarta
    assert limited_events(rig)[0]["scope"] == "global" and rig.service.state is SignerState.READY
    await rig.stop()


async def test_a_flood_of_invalid_messages_can_starve_valid_clients_until_the_window_passes_without_any_revocation() -> None:
    """Riesgo conocido (P-48 pendiente): sin un límite propio para remitentes no autorizados, el tope global es compartido. Aquí se documenta que el efecto es solo
    retrasar al cliente legítimo hasta que la ventana avance: nunca se revoca ni se detiene nada."""
    rig = await continuous_rig()
    client = await rig.connect_client()
    for sent in range(120):
        await rig.send({"basura": sent})
        if (sent + 1) % CHUNK == 0:
            await settle(rig)
    await settle(rig)
    assert await burst(rig, client, 1) == 0  # el cupo global lo agotó la basura
    assert rig.connections.is_active(client.key.public_hex) and rig.service.state is SignerState.READY
    rig.clock.advance(60)
    assert await burst(rig, client, 1) == 1
    await rig.stop()


# ------------------------------------------------------------------------------------------------ continuidad: sin topes totales
async def test_no_total_request_cap_ends_the_session_in_continuous_mode() -> None:
    rig = await continuous_rig(max_requests=2)
    client = await rig.connect_client()
    for _ in range(3):  # 90 solicitudes en tres minutos, con MAX_REQUESTS=2
        assert await burst(rig, client, 30) == 30
        rig.clock.advance(61)
    assert rig.service.state is SignerState.READY and rig.service.requests > 2 and not [e for e in rig.audit.entries() if e["event"] == "session_end"]
    await rig.stop()


async def test_several_valid_signatures_on_one_connection_each_need_their_own_human_approval() -> None:
    rig = await continuous_rig(max_signatures=1)
    client = await rig.connect_client()
    for number, challenge in enumerate((CHALLENGE, "cd" * 32, "ef" * 32, "12" * 32), start=1):
        await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=challenge)]))
        req = await rig.pending_request("sign_event")
        before = len(rig.relay.published)
        await asyncio.sleep(0.03)
        assert req.status is RequestStatus.PENDING and len(rig.relay.published) == before and rig.service.signatures == number - 1  # no se firma sin una persona
        rig.approvals.resolve(req.id, True)
        await rig.wait_for(lambda: len(rig.relay.published) > before)
        assert client.decode(rig.relay.published[-1]).error is None
    assert rig.service.signatures == 4
    decisions = [(e["approved"], e["reason"]) for e in rig.audit.entries() if e["event"] == "decision" and e["kind"] == "sign_event"]
    assert decisions == [(True, "humano")] * 4  # cuatro decisiones humanas individuales
    assert rig.service.status()["max_signatures"] is None
    await rig.stop()


async def test_a_denied_signature_is_refused_and_does_not_leave_an_implicit_approval_behind() -> None:
    rig = await continuous_rig()
    client = await rig.connect_client()
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=CHALLENGE)]))
    req = await rig.pending_request("sign_event")
    before = len(rig.relay.published)
    rig.approvals.resolve(req.id, False)
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    assert client.decode(rig.relay.published[-1]).error == "unauthorized" and rig.service.signatures == 0
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=CHALLENGE)]))  # el mismo reto, de nuevo
    again = await rig.pending_request("sign_event")
    assert again.id != req.id and again.status is RequestStatus.PENDING and rig.service.signatures == 0  # una aprobación anterior (o un rechazo) no se reutiliza
    await rig.stop()


async def test_the_pending_request_limit_still_applies() -> None:
    rig = await continuous_rig(max_pending=2)
    client = await rig.connect_client()
    for number in range(3):
        await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=f"{number:02x}" * 32)]))
        await rig.wait_for(lambda: rig.relay._queue.empty())
        await asyncio.sleep(0.05)  # las firmas pendientes siguen esperando a una persona: no hay que esperar a que terminen sus manejadores
    assert len(rig.approvals.pending()) == 2  # la tercera se rechaza: demasiadas pendientes
    assert [e["reason"] for e in rig.audit.entries() if e["event"] == "decision" and not e["approved"]][-1] == "demasiadas_pendientes"
    await rig.stop()


# ------------------------------------------------------------------------------------------------ los contadores sobreviven a una reconexión
async def test_the_counters_survive_a_relay_reconnection() -> None:
    sleep = FakeSleep()
    h = Harness("continuous", backoff=RECONNECT_BACKOFF_S, sleep=sleep, requests_per_min=5)
    first = await h.start()
    client = await first.connect_client()
    assert await burst(first, client, 6) == 5
    drop(first)
    await wait_until(h, lambda: ready_again(h, first.service))
    second = h.current_rig()
    assert await burst(second, client, 1) == 0  # tras reconectar sigue limitada: el estado (y los contadores) se conservan
    h.clock.advance(60)
    assert await burst(second, client, 1) == 1
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ supervisado: intacto
async def test_supervised_mode_applies_neither_rate_limit_and_keeps_its_total_caps() -> None:
    rig = await make_rig(max_requests=1000, max_signatures=1)  # supervisado (arnés por defecto)
    client = await rig.connect_client()
    assert await burst(rig, client, 60) == 60  # sin límite de frecuencia: se responden todas
    assert not limited_events(rig) and rig.service.service_state.connection_limiter.tracked_keys() == 0 and rig.service.service_state.global_limiter.tracked_keys() == 0
    assert rig.service.status()["max_signatures"] == 1  # y el tope de firmas sigue visible
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=CHALLENGE)]))
    req = await rig.pending_request("sign_event")
    rig.approvals.resolve(req.id, True)
    await rig.wait_for(lambda: rig.service.signatures == 1)
    resp = await rig.exchange(client, "sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge="cd" * 32)])
    assert resp.error == "unauthorized" and rig.approvals.pending() == []  # MAX_SIGNATURES=1 sigue vigente en supervisado
    await rig.stop()


async def test_supervised_mode_still_ends_the_session_at_the_total_request_cap_and_revokes() -> None:
    rig = await make_rig(max_requests=3)
    client = await rig.connect_client()
    for _ in range(4):
        await rig.send(client.request("ping", []))
    assert await asyncio.wait_for(rig.task, 5) == "tope_de_solicitudes" and rig.service.state is SignerState.STOPPED
    assert rig.connections.state_of(client.key.public_hex) is ClientState.REVOKED


async def test_the_session_start_audit_reports_no_total_signature_cap_only_in_continuous_mode() -> None:
    continuous, supervised = await continuous_rig(), await make_rig(max_signatures=2)
    assert [e["max_signatures"] for e in continuous.audit.entries() if e["event"] == "session_start"] == [None]
    assert [e["max_signatures"] for e in supervised.audit.entries() if e["event"] == "session_start"] == [2]
    await continuous.stop()
    await supervised.stop()


async def test_a_validly_signed_event_from_a_stranger_is_answered_unauthorized_and_takes_no_connection_quota() -> None:
    """Remitentes no autorizados: sin límite propio (P-48 pendiente); solo cuenta el global. No obtienen nada y no ocupan el cupo de ninguna conexión."""
    rig = await continuous_rig()
    client = await rig.connect_client()
    stranger = NdkLikeClient(rig.service.transport.public_hex, rig.clock)
    assert await burst(rig, stranger, 40) == 40  # todas respondidas (con error): sin límite propio
    assert {stranger.decode(event).error for event in rig.relay.published[-40:]} == {"unauthorized"}
    assert rig.service.service_state.connection_limiter.tracked_keys() == 0  # el extraño no tiene cubo por conexión (solo los clientes ACTIVOS lo tienen)
    assert await burst(rig, client, 30) == 30  # y el cliente emparejado conserva su cupo completo
    assert rig.service.service_state.connection_limiter.tracked_keys() == 1
    await rig.stop()

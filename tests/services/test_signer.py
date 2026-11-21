import asyncio
import json
import logging

import pytest

from app.nostr.event import parse_and_verify_event
from app.nostr.relay import RelayAuth, RelayEose, RelayNotice, RelayOk
from app.services.approvals import RequestStatus
from app.services.connections import TooManySecrets
from app.services.signer import NotReady, SignerState
from tests.support import CHALLENGE, NOW, FakeRelay, Rig, login_template, make_rig, nip04_encrypt

pytestmark = pytest.mark.anyio


async def approve_next(rig: Rig, kind: str, approve: bool = True) -> None:
    req = await rig.pending_request(kind)
    rig.approvals.resolve(req.id, approve)


async def sign(rig: Rig, client, template: str, *, approve: bool = True):  # type: ignore[no-untyped-def]
    before = len(rig.relay.published)
    await rig.send(client.request("sign_event", [template]))
    if approve is not None:
        await approve_next(rig, "sign_event", approve)
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    return client.decode(rig.relay.published[-1])


# ------------------------------------------------------------------------------------------------ arranque y URI
async def test_start_subscribes_with_window_and_becomes_ready() -> None:
    rig = await make_rig()
    assert rig.relay.subscription == (rig.service.transport.public_hex, NOW - 120)
    assert rig.service.transport.public_hex != rig.identity.public_hex
    assert any(e["event"] == "relay_ready" for e in rig.audit.entries())
    await rig.stop()


async def test_bunker_uri_only_when_ready_and_never_audited(caplog: pytest.LogCaptureFixture) -> None:
    rig = await make_rig(start=False)
    with pytest.raises(NotReady):
        rig.service.issue_bunker_uri()
    await rig.service.wait_started(3)
    with caplog.at_level(logging.DEBUG):
        uri = rig.service.issue_bunker_uri()
    secret = uri.split("secret=")[1]
    assert uri.startswith(f"bunker://{rig.service.transport.public_hex}?") and "relay=" in uri
    assert secret not in caplog.text and uri not in caplog.text
    assert secret not in json.dumps(rig.audit.entries())
    await rig.stop()


async def test_unused_uri_limit_surfaces() -> None:
    rig = await make_rig()
    for _ in range(3):
        rig.service.issue_bunker_uri()
    with pytest.raises(TooManySecrets):
        rig.service.issue_bunker_uri()
    await rig.stop()


# ------------------------------------------------------------------------------------------------ connect
async def test_connect_nip04_inbound_is_answered_in_nip44_after_approval() -> None:
    rig = await make_rig()
    client = await rig.connect_client()  # connect_client comprueba ack y NIP-44
    assert rig.connections.is_active(client.key.public_hex)
    assert rig.service.status()["connections_active"] == 1
    await rig.stop()


async def test_connect_with_wrong_secret_is_unauthorized_and_never_reaches_the_operator() -> None:
    rig = await make_rig()
    rig.service.issue_bunker_uri()
    client = rig.client()
    resp = await rig.exchange(client, "connect", ["", "x" * 22], scheme="nip04")
    assert resp.error == "unauthorized" and rig.approvals.pending() == []
    await rig.stop()


async def test_secret_cannot_be_reused_by_another_client() -> None:
    rig = await make_rig()
    secret = rig.service.issue_bunker_uri().split("secret=")[1]
    first = rig.client()
    await rig.send(first.request("connect", ["", secret], scheme="nip04"))
    await approve_next(rig, "connect")
    await rig.wait_for(lambda: len(rig.relay.published) == 1)
    second = rig.client()
    resp = await rig.exchange(second, "connect", ["", secret], scheme="nip04")
    assert resp.error == "unauthorized" and not rig.connections.is_active(second.key.public_hex)
    await rig.stop()


async def test_secret_expires() -> None:
    rig = await make_rig()
    secret = rig.service.issue_bunker_uri().split("secret=")[1]
    rig.clock.advance(601)
    resp = await rig.exchange(rig.client(), "connect", ["", secret], scheme="nip04", created_at=int(rig.clock()))
    assert resp.error == "unauthorized"
    await rig.stop()


async def test_connect_denied_by_the_operator_leaves_the_client_denied() -> None:
    rig = await make_rig()
    secret = rig.service.issue_bunker_uri().split("secret=")[1]
    client = rig.client()
    await rig.send(client.request("connect", ["", secret], scheme="nip04"))
    await approve_next(rig, "connect", False)
    await rig.wait_for(lambda: rig.relay.published)
    assert client.decode(rig.relay.published[-1]).error == "unauthorized"
    again = await rig.exchange(client, "connect", ["", secret], scheme="nip04")
    assert again.error == "unauthorized"
    await rig.stop()


async def test_connect_repeat_by_active_client_is_acked() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    assert (await rig.exchange(client, "connect", ["", "whatever"])).result == "ack"
    await rig.stop()


async def test_connect_without_params_is_unauthorized() -> None:
    rig = await make_rig()
    assert (await rig.exchange(rig.client(), "connect", [])).error == "unauthorized"
    await rig.stop()


async def test_connect_expires_after_the_connection_ttl() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    rig.clock.advance(1801)
    resp = await rig.exchange(client, "get_public_key", [], created_at=int(rig.clock()))
    assert resp.error == "unauthorized"
    await rig.stop()


# ------------------------------------------------------------------------------------------------ métodos
async def test_methods_before_connect_are_unauthorized() -> None:
    rig = await make_rig()
    client = rig.client()
    for method, params in (("get_public_key", []), ("ping", []), ("sign_event", [login_template(rig.identity.public_hex)])):
        assert (await rig.exchange(client, method, params)).error == "unauthorized"
    assert rig.approvals.pending() == [] and rig.service.signatures == 0
    await rig.stop()


async def test_get_public_key_returns_the_identity_not_the_transport_key() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    assert (await rig.exchange(client, "get_public_key", [])).result == rig.identity.public_hex
    await rig.stop()


async def test_ping_and_unsupported_methods() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    assert (await rig.exchange(client, "ping", [])).result == "pong"
    for method in ("nip44_encrypt", "nip04_decrypt", "switch_relays", "anything"):
        assert (await rig.exchange(client, method, ["x"])).error == "unsupported method"
    await rig.stop()


# ------------------------------------------------------------------------------------------------ sign_event
async def test_approved_login_event_is_signed_verified_and_unmodified() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    template = login_template(rig.identity.public_hex)
    resp = await sign(rig, client, template)
    assert resp.error is None and resp.result
    signed = parse_and_verify_event(json.loads(resp.result))
    original = json.loads(template)
    assert signed.pubkey == rig.identity.public_hex and signed.kind == 27235
    assert signed.created_at == original["created_at"] and signed.content == original["content"]
    assert [list(t) for t in signed.tags] == original["tags"] and signed.id == original["id"]
    assert rig.service.signatures == 1
    await rig.stop()


async def test_denied_or_expired_signature_does_not_sign() -> None:
    rig = await make_rig(approval_ttl_s=1)
    client = await rig.connect_client()
    resp = await sign(rig, client, login_template(rig.identity.public_hex), approve=False)
    assert resp.error == "unauthorized" and rig.service.signatures == 0
    before = len(rig.relay.published)
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, challenge="cd" * 32)]))
    await rig.wait_for(lambda: len(rig.relay.published) > before, timeout=4)  # sin decisión: caduca
    assert client.decode(rig.relay.published[-1]).error == "unauthorized"
    assert rig.service.signatures == 0 and rig.approvals.recent()[-1].status is RequestStatus.EXPIRED
    await rig.stop()


@pytest.mark.parametrize("kwargs", [
    {"kind": 1}, {"origin": "https://evil.example"}, {"method": "POST"}, {"content": "otro"}, {"age": 500}, {"challenge": "zz"},
])
async def test_policy_violations_never_reach_the_operator_nor_sign(kwargs: dict[str, object]) -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    resp = await rig.exchange(client, "sign_event", [login_template(rig.identity.public_hex, **kwargs)])  # type: ignore[arg-type]
    assert resp.error == "unauthorized" and rig.approvals.pending() == [] and rig.service.signatures == 0
    assert any(e["event"] == "policy" and e["ok"] is False for e in rig.audit.entries())
    await rig.stop()


async def test_wrong_param_count_is_invalid_params() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    assert (await rig.exchange(client, "sign_event", [])).error == "invalid params"
    assert (await rig.exchange(client, "sign_event", ["{}", "{}"])).error == "invalid params"
    await rig.stop()


async def test_a_challenge_is_signed_once_and_the_cap_is_enforced() -> None:
    rig = await make_rig(max_signatures=2)
    client = await rig.connect_client()
    assert (await sign(rig, client, login_template(rig.identity.public_hex))).error is None
    replay = await rig.exchange(client, "sign_event", [login_template(rig.identity.public_hex)])
    assert replay.error == "unauthorized" and rig.approvals.pending() == []
    assert (await sign(rig, client, login_template(rig.identity.public_hex, challenge="cd" * 32))).error is None
    capped = await rig.exchange(client, "sign_event", [login_template(rig.identity.public_hex, challenge="ef" * 32)])
    assert capped.error == "unauthorized" and rig.service.signatures == 2
    await rig.stop()


async def test_two_simultaneous_requests_with_the_same_challenge_yield_a_single_signature() -> None:
    rig = await make_rig(max_signatures=2)
    c1, c2 = rig.client(), rig.client()
    await rig.connect_client(c1)
    await rig.connect_client(c2)
    template = login_template(rig.identity.public_hex)
    await rig.send(c1.request("sign_event", [template]))
    await rig.send(c2.request("sign_event", [template]))
    await rig.wait_for(lambda: len(rig.approvals.pending()) == 2)  # ambas pasaron la política antes de que se consumiera el reto
    for req in rig.approvals.pending():
        rig.approvals.resolve(req.id, True)
    await rig.wait_for(lambda: len(rig.relay.published) >= 4)  # 2 acks de connect + 2 respuestas de sign_event
    results = [(c.decode(e)) for c, e in ((c1, next(e for e in rig.relay.published[2:] if ["p", c1.key.public_hex] in [list(t) for t in e.tags])),
                                           (c2, next(e for e in rig.relay.published[2:] if ["p", c2.key.public_hex] in [list(t) for t in e.tags])))]
    assert rig.service.signatures == 1 and sorted(r.error is None for r in results) == [False, True]
    await rig.stop()


async def test_signature_cap_of_one_blocks_the_second_login() -> None:
    rig = await make_rig(max_signatures=1)
    client = await rig.connect_client()
    assert (await sign(rig, client, login_template(rig.identity.public_hex))).error is None
    resp = await rig.exchange(client, "sign_event", [login_template(rig.identity.public_hex, challenge="cd" * 32)])
    assert resp.error == "unauthorized"
    await rig.stop()


# ------------------------------------------------------------------------------------------------ transporte hostil
async def test_hostile_transport_events_get_no_response() -> None:
    rig = await make_rig()
    client = rig.client()
    good = client.request("ping", [])
    tampered = dict(good, content=good["content"][:-2] + "AA")  # firma/id ya no coinciden
    wrong_p = client.request("ping", [], p="a" * 64)
    old = client.request("ping", [], created_at=NOW - 500)
    future = client.request("ping", [], created_at=NOW + 500)
    for raw in (tampered, wrong_p, old, future, {"kind": 24133}, {}, "x", {**good, "kind": 1}):
        await rig.send(raw)  # type: ignore[arg-type]
    await asyncio.sleep(0.2)
    assert rig.relay.published == []
    assert all(e["event"] != "request" for e in rig.audit.entries())
    await rig.stop()


async def test_replayed_transport_event_and_repeated_request_id_get_one_answer() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    raw = client.request("ping", [], req_id="same")
    await rig.send(raw)
    await rig.wait_for(lambda: len(rig.relay.published) == 2)
    await rig.send(raw)
    await rig.send(client.request("ping", [], req_id="same"))  # mismo id de solicitud, evento distinto
    await asyncio.sleep(0.2)
    assert len(rig.relay.published) == 2
    await rig.stop()


async def test_undecryptable_or_malformed_requests_are_silent_and_audited_by_type_only() -> None:
    rig = await make_rig()
    client = rig.client()
    garbage = nip04_encrypt(client.key, rig.service.transport.public_hex, "no json")
    from app.nostr.event import sign_event
    for content in (garbage, "####", "AAAA?iv=AAAA"):
        await rig.send(sign_event(client.key, 24133, [["p", rig.service.transport.public_hex]], content, NOW).to_dict())
    await asyncio.sleep(0.2)
    assert rig.relay.published == [] and any(e["event"] == "error" and e["where"] == "solicitud" for e in rig.audit.entries())
    await rig.stop()


async def test_request_cap_ends_the_session() -> None:
    rig = await make_rig(max_requests=2)
    client = rig.client()
    for _ in range(3):
        await rig.send(client.request("ping", []))
    assert await asyncio.wait_for(rig.task, 5) == "tope_de_solicitudes"
    assert rig.service.state is SignerState.STOPPED


# ------------------------------------------------------------------------------------------------ cierre y fallos
async def test_stop_by_operator_cancels_pending_revokes_and_records_session_end() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex)]))
    pending = await rig.pending_request("sign_event")
    await rig.stop()
    assert pending.status is RequestStatus.CANCELLED and not rig.connections.is_active(client.key.public_hex)
    end = rig.audit.entries()[-1]
    assert end == {**end, "event": "session_end", "reason": "detenido_por_el_operador", "signatures": 0}
    assert rig.service.state is SignerState.STOPPED and rig.relay.closed


async def test_stop_is_idempotent() -> None:
    rig = await make_rig()
    await rig.service.stop()
    await rig.service.stop()
    await asyncio.wait_for(rig.task, 5)
    assert sum(1 for e in rig.audit.entries() if e["event"] == "session_end") == 1


async def test_cancellation_still_records_session_end() -> None:
    rig = await make_rig()
    rig.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await rig.task
    assert rig.audit.entries()[-1]["event"] == "session_end" and rig.audit.entries()[-1]["reason"] == "cancelado"


async def test_relay_connect_failure_ends_failed() -> None:
    rig = await make_rig(relay=FakeRelay(fail_connect=True), start=False)
    assert not await rig.service.wait_started(2)
    assert await asyncio.wait_for(rig.task, 5) == "relay_no_disponible" and rig.service.state is SignerState.FAILED


async def test_relay_closing_the_connection_ends_the_session() -> None:
    rig = await make_rig()
    await rig.relay.close()
    assert await asyncio.wait_for(rig.task, 5) == "el_relay_cerro_la_conexion"


@pytest.mark.parametrize(("message", "reason"), [
    (RelayAuth(), "el_relay_exige_auth"), (RelayNotice("CLOSED", "bye"), "el_relay_cerro_la_suscripcion")])
async def test_auth_challenge_and_closed_end_the_session_without_answering(message: object, reason: str) -> None:
    rig = await make_rig()
    rig.relay.inject(message)  # type: ignore[arg-type]
    assert await asyncio.wait_for(rig.task, 5) == reason
    assert rig.relay.published == []


async def test_notice_and_ok_are_audited_without_ending() -> None:
    rig = await make_rig()
    client = await rig.connect_client()
    rig.relay.inject(RelayNotice("NOTICE", "hola"))
    rig.relay.inject(RelayEose("s1"))
    rig.relay.inject(RelayOk("0" * 64, True, ""))  # OK de un evento que no es nuestro: se ignora
    await rig.exchange(client, "ping", [])
    await rig.wait_for(lambda: any(e["event"] == "response_published" for e in rig.audit.entries()))
    assert rig.service.state is SignerState.READY
    await rig.stop()


async def test_publish_failure_ends_the_session() -> None:
    from app.nostr.errors import RelayError

    rig = await make_rig()
    client = rig.client()

    async def boom(event: object) -> None:
        raise RelayError("x")

    rig.relay.publish = boom  # type: ignore[method-assign]
    await rig.send(client.request("ping", []))
    assert await asyncio.wait_for(rig.task, 5) == "relay_no_disponible"


async def test_session_ttl_watchdog_stops_the_service() -> None:
    rig = await make_rig(session_ttl_s=0)  # type: ignore[arg-type]
    assert await asyncio.wait_for(rig.task, 5) == "vida_maxima_de_sesion" and rig.service.state is SignerState.STOPPED


async def test_no_secret_material_is_logged_or_audited_end_to_end(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        rig = await make_rig()
        secret = rig.service.issue_bunker_uri().split("secret=")[1]
        client = rig.client()
        await rig.send(client.request("connect", ["", secret], scheme="nip04"))
        await approve_next(rig, "connect")
        await rig.wait_for(lambda: rig.relay.published)
        template = login_template(rig.identity.public_hex)
        resp = await sign(rig, client, template)
        await rig.stop()
    blob = caplog.text + json.dumps(rig.audit.entries())
    forbidden = [secret, rig.identity.public_hex, CHALLENGE, rig.service.transport.public_hex, client.key.public_hex, json.loads(resp.result or "{}")["sig"]]
    assert all(item not in blob for item in forbidden)
    assert "bunker://" not in blob and "nsec1" not in blob


# ------------------------------------------------------------------------------------------------ rutas de defensa adicionales
async def test_self_verification_failure_never_returns_a_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.nostr.errors import InvalidEventError

    rig = await make_rig()
    client = await rig.connect_client()

    def broken(_event: object) -> None:
        raise InvalidEventError("firma invalida")

    monkeypatch.setattr("app.services.signer.verify_event", broken)
    resp = await sign(rig, client, login_template(rig.identity.public_hex))
    assert resp.error == "internal error" and "sig" not in (resp.result or "")
    assert any(e["event"] == "error" and e["where"] == "firma" for e in rig.audit.entries())
    assert not any(e["event"] == "sign_ok" for e in rig.audit.entries())
    await rig.stop()


async def test_signing_error_is_reported_as_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.nostr.errors import SigningError

    rig = await make_rig()
    client = await rig.connect_client()

    def broken(*_a: object, **_k: object) -> None:
        raise SigningError("x")

    monkeypatch.setattr("app.services.signer.sign_event", broken)
    before = len(rig.relay.published)
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex)]))
    await approve_next(rig, "sign_event")
    await rig.wait_for(lambda: rig.service.signatures == 1)
    await asyncio.sleep(0.1)
    assert len(rig.relay.published) == before  # la respuesta también usa sign_event: al romperse, no se publica nada y no se filtra firma alguna
    await rig.stop()


async def test_too_many_pending_requests_are_denied_without_blocking() -> None:
    rig = await make_rig(max_pending=1)
    c1, c2 = rig.client(), rig.client()
    s1, s2 = (rig.service.issue_bunker_uri().split("secret=")[1] for _ in range(2))
    await rig.send(c1.request("connect", ["", s1], scheme="nip04"))
    await rig.pending_request("connect")
    resp = await rig.exchange(c2, "connect", ["", s2], scheme="nip04")
    assert resp.error == "unauthorized" and len(rig.approvals.pending()) == 1
    assert any(e["event"] == "decision" and e["reason"] == "demasiadas_pendientes" for e in rig.audit.entries())
    await rig.stop()


async def test_handler_saturation_drops_new_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.signer.MAX_CONCURRENT_HANDLERS", 0)
    rig = await make_rig()
    await rig.send(rig.client().request("ping", []))
    await rig.wait_for(lambda: any(e["event"] == "error" and e["error_type"] == "saturado" for e in rig.audit.entries()))
    assert rig.relay.published == []
    await rig.stop()


async def test_unexpected_handler_exception_is_contained_and_audited_by_type(monkeypatch: pytest.MonkeyPatch) -> None:
    rig = await make_rig()

    async def boom(_raw: object) -> None:
        raise ValueError("detalle sensible")

    monkeypatch.setattr(rig.service, "handle_event", boom)
    await rig.send(rig.client().request("ping", []))
    await rig.wait_for(lambda: any(e["event"] == "error" and e["where"] == "manejador" for e in rig.audit.entries()))
    assert "detalle sensible" not in json.dumps(rig.audit.entries()) and rig.service.state is SignerState.READY
    await rig.stop()

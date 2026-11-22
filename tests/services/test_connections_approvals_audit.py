import asyncio
import logging
import re

import pytest

from app.services.approvals import AlreadyResolved, ApprovalRegistry, RequestKind, RequestStatus, TooManyPending, UnknownRequest
from app.services.audit import AuditLog, AuditViolation
from app.services.connections import MAX_CLIENTS, ClientState, ConnectionManager, TooManyClients, TooManySecrets
from tests.support import Clock

CLIENT = "c" * 64


def manager(clock: Clock) -> ConnectionManager:
    return ConnectionManager(now=clock, secret_ttl_s=60, connection_ttl_s=100)


# ------------------------------------------------------------------------------------------------ conexiones
def test_secret_is_single_use_and_stored_hashed() -> None:
    m = manager(Clock())
    secret = m.issue_secret()
    assert all(secret not in k for k in m._secrets)
    assert m.consume_secret(secret) and not m.consume_secret(secret)


def test_secret_expires_and_unknown_or_non_string_is_rejected() -> None:
    clock = Clock()
    m = manager(clock)
    secret = m.issue_secret()
    assert not m.consume_secret("x" * 22) and not m.consume_secret(None) and not m.consume_secret(5)
    clock.advance(61)
    assert not m.consume_secret(secret)


def test_unused_secrets_are_capped_and_expired_ones_are_purged() -> None:
    clock = Clock()
    m = manager(clock)
    for _ in range(3):
        m.issue_secret()
    with pytest.raises(TooManySecrets):
        m.issue_secret()
    clock.advance(61)
    m.issue_secret()


def test_client_lifecycle_and_expiry_of_an_active_connection() -> None:
    clock = Clock()
    m = manager(clock)
    assert m.state_of(CLIENT) is None and not m.is_active(CLIENT)
    m.begin(CLIENT)
    assert m.state_of(CLIENT) is ClientState.PENDING and m.counts()["pending"] == 1
    m.activate(CLIENT)
    assert m.is_active(CLIENT) and m.counts()["active"] == 1
    clock.advance(101)
    assert m.state_of(CLIENT) is ClientState.REVOKED and not m.is_active(CLIENT)


def test_deny_and_revoke_all() -> None:
    m = manager(Clock())
    m.begin(CLIENT)
    m.deny(CLIENT)
    assert m.state_of(CLIENT) is ClientState.DENIED
    secret = m.issue_secret()
    m.activate("d" * 64)
    m.revoke_all()
    assert not m.is_active("d" * 64) and not m.consume_secret(secret)


def test_number_of_distinct_clients_is_capped() -> None:
    m = manager(Clock())
    for i in range(MAX_CLIENTS):
        m.begin(f"{i:064x}")
    with pytest.raises(TooManyClients):
        m.begin("f" * 64)
    m.begin(f"{0:064x}")  # un cliente ya conocido puede reiniciar sin consumir un cupo nuevo


# ------------------------------------------------------------------------------------------------ aprobaciones
@pytest.mark.anyio
async def test_approve_resolves_the_waiter_once() -> None:
    reg = ApprovalRegistry(now=Clock())
    req = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {"k": 1}, [], 5)
    waiter = asyncio.create_task(reg.wait(req, 5))
    await asyncio.sleep(0)
    assert reg.pending() == [req] and reg.get(req.id) is req
    reg.resolve(req.id, True)
    assert await waiter == (True, "humano") and req.status is RequestStatus.APPROVED
    with pytest.raises(AlreadyResolved):
        reg.resolve(req.id, False)
    assert reg.pending() == [] and reg.recent() == [req] and reg.get(req.id) is req


@pytest.mark.anyio
async def test_consume_spends_a_valid_human_approval_exactly_once() -> None:
    reg = ApprovalRegistry(now=Clock())
    req = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60, "b" * 64)
    assert req.binding == "b" * 64 and req.consumed is False
    reg.resolve(req.id, True)
    assert reg.consume(req) is None and req.consumed is True
    assert reg.consume(req) == "aprobacion_consumida"  # no se puede gastar dos veces


@pytest.mark.anyio
async def test_consume_refuses_anything_that_is_not_a_live_human_approval() -> None:
    clock = Clock()
    reg = ApprovalRegistry(now=clock)
    pending = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    assert reg.consume(pending) == "aprobacion_no_vigente" and pending.consumed is True  # nunca decidida; igualmente queda gastada
    denied = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    reg.resolve(denied.id, False)
    assert reg.consume(denied) == "aprobacion_no_vigente"
    cancelled = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    reg.cancel_all("cancelada")
    assert reg.consume(cancelled) == "aprobacion_no_vigente"
    forged = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    reg.resolve(forged.id, True)
    forged.reason = "automatica"  # una aprobacion que no fue decision humana no sirve
    assert reg.consume(forged) == "aprobacion_no_vigente"


@pytest.mark.anyio
async def test_consume_refuses_an_approval_whose_lifetime_ended_even_if_it_was_granted_in_time() -> None:
    clock = Clock()
    reg = ApprovalRegistry(now=clock)
    req = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 10)
    reg.resolve(req.id, True)
    clock.advance(10)  # exactamente en el limite: ya no vale (igual criterio que `resolve`)
    assert reg.consume(req) == "aprobacion_caducada"
    other = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 10)
    reg.resolve(other.id, True)
    clock.advance(9)
    assert reg.consume(other) is None


@pytest.mark.anyio
async def test_outcome_is_set_once_and_shown_in_the_public_view() -> None:
    reg = ApprovalRegistry(now=Clock())
    req = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    assert req.outcome is None
    reg.resolve(req.id, True)
    assert req.public(0)["outcome"] is None  # aprobada por el operador, AUN sin resultado de la firma
    reg.set_outcome(req, "refused", "politica_incumplida")
    reg.set_outcome(req, "signed")  # un resultado ya fijado no se sobrescribe
    assert (req.outcome, req.outcome_reason) == ("refused", "politica_incumplida")
    assert req.public(0)["outcome"] == "refused" and req.public(0)["outcome_reason"] == "politica_incumplida"


@pytest.mark.anyio
async def test_finalize_unresolved_fails_only_approved_signatures_without_outcome() -> None:
    reg = ApprovalRegistry(now=Clock())
    unresolved = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    done = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    denied = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 60)
    connect = reg.create(RequestKind.CONNECT, "abcd1234", {}, [], 60)
    for req, ok in ((unresolved, True), (done, True), (denied, False), (connect, True)):
        reg.resolve(req.id, ok)
    reg.set_outcome(done, "signed")
    assert reg.finalize_unresolved("sesion_terminada") == 1
    assert (unresolved.outcome, unresolved.outcome_reason) == ("failed", "sesion_terminada")
    assert done.outcome == "signed" and denied.outcome is None and connect.outcome is None  # nada mas cambia


@pytest.mark.anyio
async def test_deny_and_unknown_id() -> None:
    reg = ApprovalRegistry(now=Clock())
    req = reg.create(RequestKind.CONNECT, "abcd1234", {}, [], 5)
    waiter = asyncio.create_task(reg.wait(req, 5))
    await asyncio.sleep(0)
    reg.resolve(req.id, False)
    assert await waiter == (False, "humano")
    with pytest.raises(UnknownRequest):
        reg.resolve("nope", True)
    assert reg.get("nope") is None


@pytest.mark.anyio
async def test_timeout_denies_and_a_late_approval_is_refused() -> None:
    clock = Clock()
    reg = ApprovalRegistry(now=clock)
    req = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 0.05)
    assert await reg.wait(req, 0.05) == (False, "timeout")
    assert req.status is RequestStatus.EXPIRED
    with pytest.raises(AlreadyResolved):
        reg.resolve(req.id, True)


@pytest.mark.anyio
async def test_resolve_after_logical_expiry_marks_expired_and_refuses() -> None:
    clock = Clock()
    reg = ApprovalRegistry(now=clock)
    req = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 10)
    clock.advance(11)
    with pytest.raises(AlreadyResolved):
        reg.resolve(req.id, True)
    assert req.status is RequestStatus.EXPIRED


@pytest.mark.anyio
async def test_cancel_all_releases_waiters_as_denied() -> None:
    reg = ApprovalRegistry(now=Clock())
    reqs = [reg.create(RequestKind.SIGN_EVENT, "abcd1234", {}, [], 5) for _ in range(2)]
    waiters = [asyncio.create_task(reg.wait(r, 5)) for r in reqs]
    await asyncio.sleep(0)
    assert reg.cancel_all("cancelada") == 2
    assert [await w for w in waiters] == [(False, "cancelada")] * 2 and all(r.status is RequestStatus.CANCELLED for r in reqs)


@pytest.mark.anyio
async def test_pending_requests_are_capped_and_public_view_is_sanitized() -> None:
    clock = Clock()
    reg = ApprovalRegistry(now=clock, max_pending=1)
    req = reg.create(RequestKind.SIGN_EVENT, "abcd1234", {"u": "x"}, [{"name": "kind", "ok": True, "detail": ""}], 30)
    with pytest.raises(TooManyPending):
        reg.create(RequestKind.CONNECT, "abcd1234", {}, [], 30)
    clock.advance(10)
    view = req.public(clock())
    assert view["expires_in_s"] == 20 and view["client"] == "abcd1234" and set(view) == {
        "id", "kind", "status", "client", "reason", "expires_in_s", "summary", "checks", "outcome", "outcome_reason", "sign_expires_in_s"}  # campos NUEVOS, ninguno retirado
    assert view["outcome"] is None and view["outcome_reason"] is None
    reg.cancel_all("x")
    assert req.public(clock())["expires_in_s"] == 0


# ------------------------------------------------------------------------------------------------ auditoría
def test_audit_accepts_whitelisted_events_and_logs_them(caplog: pytest.LogCaptureFixture) -> None:
    log = AuditLog(now=Clock())
    with caplog.at_level(logging.INFO, logger="app.audit"):
        log.emit("request", method="connect", scheme="nip44", client8="abcd1234")
    assert log.entries()[0]["method"] == "connect" and '"event": "request"' in caplog.text


@pytest.mark.parametrize("call", [
    ("nope", {}),
    ("request", {"method": "x", "scheme": "y", "client8": "z", "extra": 1}),
    ("request", {"method": "a" * 64, "scheme": "nip44", "client8": "z"}),
    ("request", {"method": "bunker://x", "scheme": "nip44", "client8": "z"}),
    ("request", {"method": "secret=abc", "scheme": "nip44", "client8": "z"}),
    ("request", {"method": "nsec1abc", "scheme": "nip44", "client8": "z"}),
])
def test_audit_refuses_anything_outside_the_whitelist_or_secret_shaped(call: tuple[str, dict[str, object]]) -> None:
    with pytest.raises(AuditViolation):
        AuditLog(now=Clock()).emit(call[0], **call[1])


def test_audit_is_bounded_and_limit_is_clamped() -> None:
    log = AuditLog(max_entries=3, now=Clock())
    for _ in range(5):
        log.emit("relay_ready")
    assert [e["seq"] for e in log.entries(100)] == [3, 4, 5] and len(log.entries(1)) == 1 and AuditLog().entries() == []


def test_snapshot_shows_truncated_clients_states_and_remaining_time() -> None:
    clock = Clock()
    m = manager(clock)
    assert m.snapshot() == []
    m.begin("a" * 64)
    m.activate("b" * 64)
    m.deny("c" * 64)
    clock.advance(40)
    view = {c["client"]: c for c in m.snapshot()}
    without_id = {name: {k: v for k, v in item.items() if k != "id"} for name, item in view.items()}  # el `id` opaco se comprueba aparte (contrato de la API, D-17)
    assert without_id["aaaaaaaa"] == {"client": "aaaaaaaa", "state": "pending", "expires_in_s": 0}
    assert without_id["bbbbbbbb"] == {"client": "bbbbbbbb", "state": "active", "expires_in_s": 60}
    assert without_id["cccccccc"]["state"] == "denied"
    ids = [item["id"] for item in view.values()]
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{12}", str(i)) for i in ids) and len(set(ids)) == 3  # todos tienen id (también los activados o denegados sin `begin`), único y URL-safe
    assert not any(str(i).startswith(("aaaa", "bbbb", "cccc")) or "a" * 6 in str(i) for i in ids)  # sin relación con la clave del cliente
    clock.advance(61)
    assert {c["client"]: c["state"] for c in m.snapshot()}["bbbbbbbb"] == "revoked"
    assert all(len(str(v)) < 64 for c in m.snapshot() for v in c.values())

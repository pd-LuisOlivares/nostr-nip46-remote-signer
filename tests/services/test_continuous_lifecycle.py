"""D-17, paso 2: ciclo de vida del firmante en modo `continuous` y sin regresiones en `supervised`.

Con `FakeRelay` y reloj inyectado: sin red ni relays reales. Cada `connect` y cada `sign_event` siguen exigiendo la aprobación humana individual (no hay firma
automática en ningún modo). Los límites `MAX_REQUESTS` y `MAX_SIGNATURES` siguen aplicándose en AMBOS modos hasta el paso en que se sustituyan por sus controles.
"""
import asyncio
from typing import Any

import pytest

from app.config import Settings
from app.nostr.keys import Keypair
from app.services.approvals import RequestStatus
from app.services.connections import ClientState
from app.services.runtime import NoIdentity, SignerRuntime, StartFailed
from app.services.signer import SignerState
from tests.support import CHALLENGE, SUPERVISED_TTLS, Clock, FakeRelay, NdkLikeClient, Rig, login_template

pytestmark = pytest.mark.anyio

OTHER_CHALLENGE = "cd" * 32


class Harness:
    """Un `SignerRuntime` real con un relay falso nuevo en cada arranque y el mismo reloj para todo."""

    def __init__(self, mode: str, *, backoff: tuple[float, ...] = (), sleep: Any = None, **overrides: Any) -> None:
        self.clock, self.identity = Clock(), Keypair.generate()
        self.relays: list[FakeRelay] = []
        self.relay_kwargs: dict[str, Any] = {}
        # Plan por intento (test_reconnection.py): cada elemento se consume en orden al crear un relay. dict = argumentos de FakeRelay; Exception = la fábrica la lanza;
        # callable = devuelve el relay ya preparado. Si el plan se acaba, se usa `relay_kwargs`.
        self.relay_plan: list[Any] = []
        base: dict[str, Any] = dict(SUPERVISED_TTLS) if mode == "supervised" else {"signer_mode": "continuous"}
        self.settings = Settings(**{**base, "approval_ttl_s": 5, **overrides})
        # Sin esperas de reconexión (`backoff=()`): tras la caída del relay el supervisor agota los intentos al instante y el firmante queda FAILED con las conexiones
        # conservadas (el escenario del Paso 2: un «Iniciar» manual las reanuda). La reconexión automática se prueba en test_reconnection.py.
        extra: dict[str, Any] = {} if sleep is None else {"sleep": sleep}
        self.runtime = SignerRuntime(self.settings, relay_factory=self._factory, now=self.clock, start_timeout_s=3, backoff=backoff, **extra)
        self.runtime.set_identity(self.identity)

    def _factory(self, _settings: Settings) -> FakeRelay:
        step = self.relay_plan.pop(0) if self.relay_plan else self.relay_kwargs
        if isinstance(step, Exception):
            raise step
        relay = step() if callable(step) else FakeRelay(**step)
        self.relays.append(relay)
        return relay

    def current_rig(self) -> Rig:
        """Rig sobre el firmante que el runtime tiene AHORA (tras una reconexión es otro servicio y otro relay)."""
        service, task = self.runtime.service, self.runtime._task
        assert service is not None and task is not None
        return Rig(service, self.relays[-1], self.runtime.audit, service.approvals, service.connections, self.clock, self.identity_of(), task)

    async def start(self) -> Rig:
        service = await self.runtime.start()
        task = self.runtime._task
        assert task is not None
        return Rig(service, self.relays[-1], self.runtime.audit, service.approvals, service.connections, self.clock, self.identity_of(), task)

    def identity_of(self) -> Keypair:
        identity = self.runtime._identity
        assert identity is not None
        return identity

    async def drop_relay(self, rig: Rig) -> None:
        """El relay corta la conexión (fallo recuperable): el flujo de mensajes termina y la sesión acaba sin que nadie la detenga."""
        rig.relay._queue.put_nowait(None)
        await rig.wait_for(lambda: not self.runtime.running)
        await asyncio.wait_for(rig.task, 3)


async def sign_request(rig: Rig, client: NdkLikeClient, challenge: str = CHALLENGE) -> Any:
    await rig.send(client.request("sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=challenge)]))
    return await rig.pending_request("sign_event")


async def approved_signature(rig: Rig, client: NdkLikeClient, challenge: str = CHALLENGE) -> None:
    req = await sign_request(rig, client, challenge)
    before = len(rig.relay.published)
    rig.approvals.resolve(req.id, True)
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    assert client.decode(rig.relay.published[-1]).error is None


def last_policy(rig: Rig) -> dict[str, Any]:
    return next(e for e in reversed(rig.audit.entries()) if e["event"] == "policy")


# ------------------------------------------------------------------------------------------------ 1. sin parada por SESSION_TTL_S
async def test_continuous_mode_is_not_stopped_by_the_session_ttl() -> None:
    h = Harness("continuous", session_ttl_s=0)  # en supervisado esto detendría el firmante de inmediato (ver el vigilante de la sesión)
    rig = await h.start()
    client = await rig.connect_client()
    await asyncio.sleep(0.3)  # tiempo real de sobra para que un vigilante con TTL 0 ya hubiera actuado
    rig.clock.advance(2 * 3600)  # y tiempo simulado muy por encima de SESSION_TTL_S por defecto (3600 s), dentro de la vida de la conexión (8 h)
    resp = await rig.exchange(client, "get_public_key", [])
    assert resp.result == rig.identity.public_hex and h.runtime.running and rig.service.state is SignerState.READY
    assert not [e for e in rig.audit.entries() if e["event"] == "session_end"]
    await h.runtime.stop()


async def test_supervised_mode_is_still_stopped_by_the_session_ttl() -> None:
    h = Harness("supervised", session_ttl_s=0)
    try:
        await h.runtime.start()
    except StartFailed:
        pass  # con TTL 0 el vigilante puede ganar la carrera al arranque; el resultado observable es el mismo
    task = h.runtime._task
    assert task is not None
    assert await asyncio.wait_for(task, 5) == "vida_maxima_de_sesion" and not h.runtime.running


# ------------------------------------------------------------------------------------------------ 2 y 4. fallo recuperable: se conserva todo
async def test_a_recoverable_relay_failure_keeps_the_pairing_the_transport_key_and_the_state() -> None:
    h = Harness("continuous")
    first = await h.start()
    client = await first.connect_client()
    transport, manager, state = first.service.transport.public_hex, first.connections, first.service.service_state
    await h.drop_relay(first)
    assert first.service.state is SignerState.FAILED and first.service.end_reason == "el_relay_cerro_la_conexion"
    assert manager.is_active(client.key.public_hex) and not state.stale  # nada se revocó

    second = await h.start()  # «Iniciar» tras la caída: reanuda
    assert second.service is not first.service and second.relay is not first.relay
    assert second.service.transport.public_hex == transport  # la clave de transporte NO cambia: las URI y los clientes emparejados siguen valiendo
    assert second.connections is manager and second.service.service_state is state
    resp = await second.exchange(client, "get_public_key", [])  # el cliente ya emparejado sigue autorizado SIN repetir `connect`
    assert resp.result == second.identity.public_hex and resp.error is None
    assert [e["event"] for e in second.audit.entries()].count("session_start") == 2
    await h.runtime.stop()


async def test_a_failed_resume_attempt_does_not_destroy_the_pairing() -> None:
    h = Harness("continuous")
    first = await h.start()
    client = await first.connect_client()
    manager = first.connections
    await h.drop_relay(first)
    h.relay_kwargs = {"fail_connect": True}  # el relay sigue caído al volver a pulsar «Iniciar»
    with pytest.raises(StartFailed):
        await h.runtime.start()
    assert manager.is_active(client.key.public_hex) and not first.service.service_state.stale
    h.relay_kwargs = {}
    third = await h.start()  # cuando el relay vuelve, se reanuda con el mismo emparejamiento
    assert third.connections is manager and (await third.exchange(client, "get_public_key", [])).error is None
    await h.runtime.stop()


async def test_a_publish_failure_is_recoverable_too() -> None:
    h = Harness("continuous")
    first = await h.start()
    client = await first.connect_client()

    async def broken_publish(_event: Any) -> None:
        from app.nostr.errors import RelayError
        raise RelayError("no se pudo enviar al relay")

    first.relay.publish = broken_publish  # type: ignore[method-assign]
    await first.send(client.request("ping", []))
    await first.wait_for(lambda: not h.runtime.running)
    assert first.service.end_reason == "relay_no_disponible" and first.connections.is_active(client.key.public_hex)
    assert not first.service.service_state.stale and not h.runtime.running


async def test_a_pending_connect_cut_by_the_failure_is_forgotten_not_left_half_done_or_denied_forever() -> None:
    h = Harness("continuous")
    first = await h.start()
    client = first.client()
    secret = first.service.issue_bunker_uri().split("secret=")[1]
    await first.send(client.request("connect", ["", secret], scheme="nip04"))
    pending = await first.pending_request("connect")
    await h.drop_relay(first)
    assert pending.status is RequestStatus.CANCELLED and first.connections.state_of(client.key.public_hex) is None  # ni activo, ni pendiente, ni denegado
    second = await h.start()
    assert (await second.connect_client(client)).key is client.key  # con una URI nueva, la misma clave de cliente puede emparejarse
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ 3. detención manual: revoca y limpia
async def test_a_manual_stop_cancels_pending_revokes_connections_and_resets_the_state() -> None:
    h = Harness("continuous", max_signatures=2)
    first = await h.start()
    client = await first.connect_client()
    await approved_signature(first, client)  # un reto firmado en esta sesión
    unused_uri = first.service.issue_bunker_uri()  # y una URI emitida sin usar
    pending = await sign_request(first, client, OTHER_CHALLENGE)  # y una firma pendiente de aprobación
    old_transport, old_manager, old_state = first.service.transport.public_hex, first.connections, first.service.service_state
    await h.runtime.stop()
    assert unused_uri and pending.status is RequestStatus.CANCELLED and first.approvals.pending() == []
    assert old_manager.state_of(client.key.public_hex) is ClientState.REVOKED and old_manager.counts()["unused_secrets"] == 0
    assert old_state.stale is True and [e for e in first.audit.entries() if e["event"] == "session_end"][-1]["reason"] == "detenido_por_el_operador"

    second = await h.start()  # el siguiente arranque crea todo de nuevo
    assert second.service.transport.public_hex != old_transport and second.connections is not old_manager and second.service.service_state is not old_state
    assert second.connections.state_of(client.key.public_hex) is None  # el cliente anterior ya no existe: hay que emparejar de nuevo
    assert (len(second.service.service_state.seen_events), len(second.service.service_state.seen_requests)) == (0, 0)
    await h.runtime.stop()


@pytest.mark.parametrize("reason_setup", ["auth", "closed"])
async def test_other_session_endings_are_not_recoverable_and_revoke_the_pairing(reason_setup: str) -> None:
    from app.nostr.relay import RelayAuth, RelayNotice
    h = Harness("continuous")
    first = await h.start()
    client = await first.connect_client()
    first.relay.inject(RelayAuth() if reason_setup == "auth" else RelayNotice("CLOSED", "cerrada"))
    await first.wait_for(lambda: not h.runtime.running)
    await asyncio.wait_for(first.task, 3)
    assert first.connections.state_of(client.key.public_hex) is ClientState.REVOKED and first.service.service_state.stale
    assert (await h.start()).service.transport.public_hex != first.service.transport.public_hex
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ 5. anti-replay: se conserva y está acotado
async def test_replay_registers_survive_a_recoverable_failure() -> None:
    h = Harness("continuous")
    first = await h.start()
    client = await first.connect_client()
    event = client.request("get_public_key", [], req_id="repetida")
    await first.send(event)
    await first.wait_for(lambda: len(first.relay.published) >= 2)  # respuesta al connect + a esta solicitud
    await approved_signature(first, client)  # reto CHALLENGE firmado
    await h.drop_relay(first)

    second = await h.start()
    errors_before = len([e for e in second.audit.entries() if e["event"] == "error"])
    await second.send(event)  # el MISMO evento (mismo id) reenviado por el relay tras reanudar
    await second.send(client.request("get_public_key", [], req_id="repetida"))  # y OTRO evento con el mismo id de solicitud
    await second.wait_for(lambda: len([e for e in second.audit.entries() if e["event"] == "error"]) >= errors_before + 2)
    assert second.relay.published == []  # ninguno de los dos se procesó ni se respondió
    kinds = [e["error_type"] for e in second.audit.entries() if e["event"] == "error"][-2:]
    assert sorted(kinds) == ["evento_descartado", "id_repetido"]

    resp = await second.exchange(client, "sign_event", [login_template(second.identity.public_hex, now=int(second.clock()), challenge=CHALLENGE)])
    assert resp.error == "unauthorized" and second.approvals.pending() == [] and "replay" in last_policy(second)["failed"]  # el reto ya firmado no se ofrece de nuevo
    await h.runtime.stop()


async def test_signed_challenges_are_remembered_after_a_manual_stop_but_not_after_changing_identity() -> None:
    h = Harness("continuous")
    first = await h.start()
    await approved_signature(first, await first.connect_client())
    registry = first.service.service_state.seen_challenges
    await h.runtime.stop()

    second = await h.start()  # estado nuevo, pero los retos ya firmados se recuerdan (acotados) mientras la identidad sea la misma
    assert second.service.service_state.seen_challenges is registry and len(registry) == 1
    client = await second.connect_client()
    resp = await second.exchange(client, "sign_event", [login_template(second.identity.public_hex, now=int(second.clock()), challenge=CHALLENGE)])
    assert resp.error == "unauthorized" and "replay" in last_policy(second)["failed"]
    await h.runtime.stop()

    h.runtime.set_identity(Keypair.generate())  # otra identidad: no se arrastra nada de la anterior
    third = await h.start()
    assert third.service.service_state.seen_challenges is not registry and len(third.service.service_state.seen_challenges) == 0
    assert third.service.transport.public_hex != second.service.transport.public_hex
    await sign_request(third, await third.connect_client(), CHALLENGE)  # el mismo reto se ofrece (pendiente de aprobación humana) para la nueva identidad
    await h.runtime.stop()


async def test_the_registries_in_a_running_service_are_bounded_in_size_and_lifetime() -> None:
    h = Harness("continuous")
    rig = await h.start()
    state = rig.service.service_state
    assert (state.seen_events.max_entries, state.seen_requests.max_entries, state.seen_challenges.max_entries) == (4096, 4096, 4096)
    client = await rig.connect_client()
    assert (len(state.seen_events), len(state.seen_requests)) == (1, 1)  # el evento de transporte del `connect` y su solicitud
    rig.clock.advance(120 + 60 + 1)
    assert (len(state.seen_events), len(state.seen_requests)) == (0, 1)  # el id del evento caduca al salir de la ventana (+ margen); el id de solicitud se recuerda 24 h
    assert (await rig.exchange(client, "get_public_key", [])).error is None  # y el firmante sigue operativo
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ 6. aprobación humana de cada firma
async def test_every_sign_event_still_needs_an_individual_human_approval_in_continuous_mode() -> None:
    h = Harness("continuous", max_signatures=2)
    rig = await h.start()
    client = await rig.connect_client()  # el connect también exigió aprobación humana (connect_client la resuelve a mano)
    for challenge in (CHALLENGE, OTHER_CHALLENGE):
        req = await sign_request(rig, client, challenge)
        before = len(rig.relay.published)
        await asyncio.sleep(0.05)
        assert len(rig.relay.published) == before and req.status is RequestStatus.PENDING  # nada se firma sin una decisión humana
        assert rig.service.signatures == len([e for e in rig.audit.entries() if e["event"] == "sign_ok"])
        rig.approvals.resolve(req.id, True)
        await rig.wait_for(lambda: len(rig.relay.published) > before)
        assert client.decode(rig.relay.published[-1]).error is None
    assert rig.service.signatures == 2
    decisions = [(e["approved"], e["reason"]) for e in rig.audit.entries() if e["event"] == "decision" and e["kind"] == "sign_event"]
    assert decisions == [(True, "humano"), (True, "humano")]  # cada firma tuvo su decision humana individual
    await h.runtime.stop()


async def test_a_denied_sign_event_is_refused_and_an_unpaired_client_cannot_even_ask() -> None:
    h = Harness("continuous")
    rig = await h.start()
    client = await rig.connect_client()
    req = await sign_request(rig, client)
    before = len(rig.relay.published)
    rig.approvals.resolve(req.id, False)
    await rig.wait_for(lambda: len(rig.relay.published) > before)
    assert client.decode(rig.relay.published[-1]).error == "unauthorized" and rig.service.signatures == 0
    stranger = rig.client()  # clave de cliente desconocida: sin conexión, sin tarjeta
    resp = await rig.exchange(stranger, "sign_event", [login_template(rig.identity.public_hex, now=int(rig.clock()), challenge=OTHER_CHALLENGE)])
    assert resp.error == "unauthorized" and rig.approvals.pending() == [] and rig.service.signatures == 0
    await h.runtime.stop()


async def test_the_total_request_and_signature_caps_do_not_apply_in_continuous_mode_but_each_signature_still_needs_a_human() -> None:
    """Componente 3 (D-17.6): ya existen los límites de frecuencia que sustituyen a MAX_REQUESTS y MAX_SIGNATURES, que dejan de aplicarse SOLO en modo continuo."""
    h = Harness("continuous", max_signatures=1, max_requests=2)
    rig = await h.start()
    client = await rig.connect_client()
    for _ in range(10):  # muy por encima de MAX_REQUESTS=2: todas se responden y la sesión sigue
        assert (await rig.exchange(client, "ping", [])).result == "pong"
    for challenge in (CHALLENGE, OTHER_CHALLENGE, "ef" * 32):  # tres firmas con MAX_SIGNATURES=1, cada una con SU aprobación humana
        req = await sign_request(rig, client, challenge)
        before = len(rig.relay.published)
        await asyncio.sleep(0.03)
        assert req.status is RequestStatus.PENDING and len(rig.relay.published) == before  # nada se firma sin decisión humana
        rig.approvals.resolve(req.id, True)
        await rig.wait_for(lambda: len(rig.relay.published) > before)
        assert client.decode(rig.relay.published[-1]).error is None
    assert rig.service.signatures == 3 and h.runtime.running and rig.service.state is SignerState.READY
    assert h.runtime.status()["signer"]["max_signatures"] is None  # sin tope total
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ 7. supervisado: sin regresiones
async def test_supervised_mode_keeps_its_previous_behavior_revokes_on_failure_and_starts_clean_each_time() -> None:
    h = Harness("supervised")
    first = await h.start()
    client = await first.connect_client()
    await approved_signature(first, client)
    await h.drop_relay(first)
    assert first.connections.state_of(client.key.public_hex) is ClientState.REVOKED  # antes y ahora: toda caída revoca
    assert h.runtime._state is None  # el supervisado no conserva estado en el runtime

    second = await h.start()
    assert second.service.transport.public_hex != first.service.transport.public_hex and second.connections is not first.connections
    assert second.service.service_state is not first.service.service_state and len(second.service.service_state.seen_challenges) == 0
    again = await second.connect_client()
    req = await sign_request(second, again, CHALLENGE)  # el mismo reto se ofrece de nuevo: en supervisado el registro es de UNA sesión, como antes
    assert req.status is RequestStatus.PENDING
    await h.runtime.stop()
    assert h.runtime._state is None


async def test_supervised_manual_stop_still_revokes_and_the_limits_are_unchanged() -> None:
    h = Harness("supervised")
    rig = await h.start()
    client = await rig.connect_client()
    await h.runtime.stop()
    assert rig.connections.state_of(client.key.public_hex) is ClientState.REVOKED and not h.runtime.running
    assert (h.settings.max_signatures, h.settings.max_requests, h.settings.session_ttl_s) == (1, 60, 3600)


# ------------------------------------------------------------------------------------------------ reinicio del proceso y construcción
async def test_restarting_the_process_recovers_neither_identity_nor_connections() -> None:
    h = Harness("continuous")
    rig = await h.start()
    await rig.connect_client()
    await h.runtime.stop()
    fresh = SignerRuntime(h.settings, relay_factory=h._factory, now=h.clock)  # «proceso nuevo»: no existe persistencia de ningún tipo
    assert fresh.public_key is None and fresh._state is None and fresh.status()["identity"] == {"present": False, "public_key": None}
    with pytest.raises(NoIdentity):
        await fresh.start()


async def test_the_service_rejects_a_state_that_does_not_match_its_connection_manager() -> None:
    from app.services.approvals import ApprovalRegistry
    from app.services.audit import AuditLog
    from app.services.connections import ConnectionManager
    from app.services.session_state import ServiceState
    from app.services.signer import SignerService
    clock, cfg = Clock(), Settings()
    state = ServiceState.create(cfg, clock)
    other = ConnectionManager(now=clock, secret_ttl_s=300, connection_ttl_s=60)
    with pytest.raises(ValueError):
        SignerService(identity=Keypair.generate(), relay=FakeRelay(), settings=cfg, approvals=ApprovalRegistry(now=clock, max_pending=4), connections=other,
                      audit=AuditLog(now=clock), now=clock, service_state=state)


async def test_audit_and_state_never_expose_private_keys_in_continuous_mode(caplog: pytest.LogCaptureFixture) -> None:
    h = Harness("continuous")
    rig = await h.start()
    client = await rig.connect_client()
    await approved_signature(rig, client)
    await h.drop_relay(rig)
    second = await h.start()
    secrets_ = [rig.identity._secret.hex(), second.service.transport._secret.hex(), client.key._secret.hex()]  # type: ignore[attr-defined]
    haystack = repr(second.audit.entries()) + repr(second.service.service_state) + caplog.text + repr(h.runtime.status())
    assert not [s for s in secrets_ if s in haystack]
    await h.runtime.stop()

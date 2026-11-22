"""D-17, Componente 2: reconexión automática acotada al relay (solo modo `continuous`) y sus carreras con la parada manual y el cierre de la aplicación.

Con `FakeRelay`, reloj inyectado y una espera simulada (`FakeSleep`): sin red y sin esperar los segundos reales. Cada `connect` y cada `sign_event` siguen exigiendo la
aprobación humana individual; ninguna aprobación anterior se reutiliza tras reconectar.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.nostr.errors import RelayError
from app.nostr.relay import RelayAuth, RelayNotice
from app.services.approvals import RequestStatus
from app.services.connections import ClientState
from app.services.runtime import RECONNECT_BACKOFF_S, RECONNECT_STABLE_S, AlreadyRunning, NotRunning, SignerRuntime
from app.services.signer import SignerState
from tests.services.test_continuous_lifecycle import Harness, approved_signature, sign_request
from tests.support import CHALLENGE, FakeRelay, Rig, login_template

pytestmark = pytest.mark.anyio

OTHER = "cd" * 32


class FakeSleep:
    """Sustituye a `asyncio.sleep` en el supervisor: registra las esperas pedidas y, si `hold`, no avanza hasta `release`."""

    def __init__(self, hold: bool = False) -> None:
        self.delays: list[float] = []
        self.release = asyncio.Event()
        if not hold:
            self.release.set()

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        await self.release.wait()
        await asyncio.sleep(0)


@dataclass
class HangingRelay(FakeRelay):
    """Un relay cuya conexión no termina hasta que se le cierra (un intento de reconexión «en vuelo»)."""

    gate: "asyncio.Event" = field(default_factory=asyncio.Event)

    async def connect(self) -> None:
        self.connects += 1
        await self.gate.wait()
        raise RelayError("no se pudo conectar al relay")

    async def close(self) -> None:
        self.closed = True
        self.gate.set()
        self._queue.put_nowait(None)


def drop(rig: Rig) -> None:
    """El relay corta la conexión sin que nadie lo pida."""
    rig.relay._queue.put_nowait(None)


def recon(sleep: FakeSleep, **overrides: Any) -> Harness:
    return Harness("continuous", backoff=RECONNECT_BACKOFF_S, sleep=sleep, **overrides)


async def wait_until(h: Harness, predicate: Any, timeout: float = 3.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(poll(), timeout)


def ready_again(h: Harness, previous: Any) -> bool:
    return h.runtime.service is not previous and h.runtime.service is not None and h.runtime.service.state is SignerState.READY


# ------------------------------------------------------------------------------------------------ reconexión tras una caída transitoria
async def test_a_transient_drop_reconnects_with_a_new_transport_keeping_pairing_transport_key_and_replay_state() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    first = await h.start()
    client = await first.connect_client()
    event = client.request("get_public_key", [], req_id="repetida")
    await first.send(event)
    await first.wait_for(lambda: len(first.relay.published) >= 2)
    transport, manager, state = first.service.transport.public_hex, first.connections, first.service.service_state
    drop(first)
    await wait_until(h, lambda: ready_again(h, first.service))
    second = h.current_rig()
    assert sleep.delays == [2.0] and second.relay is not first.relay and second.service is not first.service  # transporte NUEVO en cada intento
    assert second.service.transport.public_hex == transport and second.connections is manager and second.service.service_state is state  # nada cambió
    assert second.relay.subscription == (transport, int(h.clock()) - h.settings.window_s)  # la suscripción se restablece con since = ahora - SIGNER_WINDOW_S
    assert h.runtime.running and h.runtime.status()["signer"]["state"] == "ready" and h.runtime.status()["signer"]["end_reason"] is None
    resp = await second.exchange(client, "get_public_key", [])  # el cliente emparejado sigue autorizado SIN repetir `connect`
    assert resp.result == second.identity.public_hex
    await second.send(event)  # el relay vuelve a entregar un evento ya procesado antes de la caída
    await asyncio.sleep(0.05)
    assert len(second.relay.published) == 1  # solo la respuesta anterior: el duplicado se rechazó
    events = [e for e in second.audit.entries() if e["event"] == "relay_reconnect"]
    assert events == [{**events[0], "attempt": 1, "max_attempts": 5, "delay_s": 2}]
    await h.runtime.stop()


async def test_the_backoff_is_2_5_10_20_40_seconds_and_a_late_recovery_stops_counting() -> None:
    assert RECONNECT_BACKOFF_S == (2.0, 5.0, 10.0, 20.0, 40.0) and RECONNECT_STABLE_S == 60.0
    sleep = FakeSleep()
    h = recon(sleep)
    first = await h.start()
    h.relay_plan = [{"fail_connect": True}, {"fail_connect": True}, {}]  # dos intentos fallan y el tercero conecta
    drop(first)
    await wait_until(h, lambda: ready_again(h, first.service))
    assert sleep.delays == [2.0, 5.0, 10.0]
    await h.runtime.stop()


async def test_five_failed_attempts_leave_the_signer_failed_with_the_connections_kept_and_a_manual_start_resumes() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    first = await h.start()
    client = await first.connect_client()
    transport, manager = first.service.transport.public_hex, first.connections
    h.relay_plan = [{"fail_connect": True}] * 5
    drop(first)
    await wait_until(h, lambda: sleep.delays == [2.0, 5.0, 10.0, 20.0, 40.0] and not h.runtime.running)
    assert len(h.relays) == 6  # el original y cinco intentos: ni uno más
    status = h.runtime.status()["signer"]
    assert status["state"] == "failed" and status["end_reason"] == "reconexion_agotada" and status["connections_active"] == 1
    assert manager.is_active(client.key.public_hex) and not first.service.service_state.stale  # las conexiones conservadas siguen ahí
    assert [e["attempts"] for e in h.runtime.audit.entries() if e["event"] == "reconnect_exhausted"] == [5]
    assert h.runtime._supervisor is not None and h.runtime._supervisor.done()
    resumed = await h.start()  # recuperación manual: sin un nuevo emparejamiento
    assert resumed.service.transport.public_hex == transport and resumed.connections is manager
    assert (await resumed.exchange(client, "get_public_key", [])).result == resumed.identity.public_hex
    assert h.runtime.status()["signer"]["end_reason"] is None
    await h.runtime.stop()


async def test_the_attempt_counter_is_not_reset_by_a_relay_that_keeps_dropping_but_is_after_a_stable_minute() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    first = await h.start()
    drop(first)
    await wait_until(h, lambda: ready_again(h, first.service))
    second = h.current_rig()
    drop(second)  # cae de nuevo enseguida: no estuvo estable, así que sigue la cuenta (5 s)
    await wait_until(h, lambda: ready_again(h, second.service))
    third = h.current_rig()
    await asyncio.sleep(0.05)  # el supervisor anota el instante en que este servicio quedó listo (unas vueltas del bucle después de que el estado pase a READY)
    h.clock.advance(RECONNECT_STABLE_S + 1)  # esta vez estuvo listo más de un minuto
    drop(third)
    await wait_until(h, lambda: ready_again(h, third.service))
    assert sleep.delays == [2.0, 5.0, 2.0]
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ aprobaciones pendientes y repeticiones
async def test_pending_approvals_are_cancelled_when_the_relay_is_lost_and_nothing_is_reused_after_reconnecting() -> None:
    h = recon(FakeSleep(), max_signatures=2)
    first = await h.start()
    client = await first.connect_client()
    await approved_signature(first, client)  # un reto firmado
    pending = await sign_request(first, client, OTHER)  # y una firma pendiente de aprobación
    drop(first)
    await wait_until(h, lambda: ready_again(h, first.service))
    second = h.current_rig()
    assert pending.status is RequestStatus.CANCELLED and second.approvals.pending() == []  # no pasa a la nueva sesión ni se aprueba sola
    assert second.service.signatures == 0
    # el mismo reto ya firmado no se ofrece de nuevo (anti-replay conservado)...
    resp = await second.exchange(client, "sign_event", [login_template(second.identity.public_hex, now=int(h.clock()), challenge=CHALLENGE)])
    assert resp.error == "unauthorized" and second.approvals.pending() == []
    # ...y la solicitud cancelada solo avanza si el cliente la repite y una persona la aprueba de nuevo
    again = await sign_request(second, client, OTHER)
    assert again.status is RequestStatus.PENDING and again.id != pending.id
    await asyncio.sleep(0.05)
    assert second.service.signatures == 0
    await h.runtime.stop()


async def test_a_pending_connect_cut_by_the_loss_is_forgotten_and_needs_a_new_uri_and_a_new_human_approval() -> None:
    h = recon(FakeSleep())
    first = await h.start()
    client = first.client()
    secret = first.service.issue_bunker_uri().split("secret=")[1]
    await first.send(client.request("connect", ["", secret], scheme="nip04"))
    pending = await first.pending_request("connect")
    drop(first)
    await wait_until(h, lambda: ready_again(h, first.service))
    second = h.current_rig()
    assert pending.status is RequestStatus.CANCELLED and second.connections.state_of(client.key.public_hex) is None
    assert (await second.connect_client(client)).key is client.key  # URI nueva y aprobación humana nueva
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ cuándo NO se reconecta
async def test_no_reconnection_after_a_manual_stop() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    rig = await h.start()
    client = await rig.connect_client()
    await h.runtime.stop()
    await asyncio.sleep(0.05)
    assert sleep.delays == [] and len(h.relays) == 1 and not h.runtime.running
    assert rig.connections.state_of(client.key.public_hex) is ClientState.REVOKED and h.runtime._supervisor is None


async def test_a_manual_stop_during_the_wait_cancels_the_reconnection_and_revokes_everything() -> None:
    sleep = FakeSleep(hold=True)
    h = recon(sleep)
    first = await h.start()
    client = await first.connect_client()
    transport = first.service.transport.public_hex
    drop(first)
    await wait_until(h, lambda: sleep.delays == [2.0])
    assert h.runtime.running and h.runtime.status()["signer"]["state"] == "reconnecting"  # esperando: sigue «en marcha» y se puede detener
    with pytest.raises(AlreadyRunning):
        await h.runtime.start()  # ni un segundo arranque ni un cambio de identidad mientras se reconecta
    with pytest.raises(AlreadyRunning):
        h.runtime.set_identity(h.identity_of())
    await h.runtime.stop()
    sleep.release.set()
    await asyncio.sleep(0.05)
    assert sleep.delays == [2.0] and len(h.relays) == 1 and not h.runtime.running  # no hubo ningún intento más
    assert first.connections.state_of(client.key.public_hex) is ClientState.REVOKED and first.service.service_state.stale
    assert h.runtime._supervisor is None and h.runtime.status()["signer"]["state"] != "reconnecting"
    again = await h.start()
    assert again.service.transport.public_hex != transport  # estado nuevo: la parada manual no conserva nada
    await h.runtime.stop()


async def test_a_manual_stop_while_an_attempt_is_in_flight_ends_cleanly_without_orphans() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    first = await h.start()
    client = await first.connect_client()
    hanging = HangingRelay()
    h.relay_plan = [lambda: hanging]
    drop(first)
    await wait_until(h, lambda: hanging.connects == 1)  # el intento está intentando conectar
    await asyncio.wait_for(h.runtime.stop(), 3)  # detener no espera a que el relay conteste
    assert hanging.closed and not h.runtime.running and h.runtime._supervisor is None
    assert h.runtime._task is not None and h.runtime._task.done()
    assert h.runtime.service is not None and h.runtime.service.state in (SignerState.STOPPED, SignerState.FAILED)
    assert first.connections.state_of(client.key.public_hex) is ClientState.REVOKED
    assert sleep.delays == [2.0] and len(h.relays) == 2  # ningún intento posterior


async def test_app_shutdown_during_the_wait_stops_everything() -> None:
    sleep = FakeSleep(hold=True)
    h = recon(sleep)
    first = await h.start()
    await first.connect_client()
    drop(first)
    await wait_until(h, lambda: sleep.delays == [2.0])
    await asyncio.wait_for(h.runtime.shutdown(), 3)
    assert not h.runtime.running and h.runtime._supervisor is None
    assert [e["reason"] for e in h.runtime.audit.entries() if e["event"] == "session_end"][-1] in ("el_relay_cerro_la_conexion", "apagado_de_la_aplicacion")
    with pytest.raises(NotRunning):
        await h.runtime.stop() if h.runtime.service is None else (_ for _ in ()).throw(NotRunning())


@pytest.mark.parametrize("message, reason", [(RelayAuth(), "el_relay_exige_auth"), (RelayNotice("CLOSED", "cerrada"), "el_relay_cerro_la_suscripcion")])
async def test_permanent_errors_are_not_retried_neither_while_running_nor_during_a_reconnection(message: Any, reason: str) -> None:
    # 1) mientras el firmante corre: AUTH o suscripción cerrada terminan la sesión sin reconectar y revocan las conexiones
    sleep = FakeSleep()
    h = recon(sleep)
    rig = await h.start()
    client = await rig.connect_client()
    rig.relay.inject(message)
    await wait_until(h, lambda: not h.runtime.running)
    assert sleep.delays == [] and rig.service.end_reason == reason and rig.connections.state_of(client.key.public_hex) is ClientState.REVOKED
    # 2) durante una reconexión: el relay vuelve, pero exige AUTH o cierra la suscripción: no se sigue intentando
    sleep2 = FakeSleep()
    h2 = recon(sleep2)
    first = await h2.start()
    client2 = await first.connect_client()

    def broken_relay() -> FakeRelay:
        relay = FakeRelay(auto_eose=False)
        relay.inject(message)
        return relay

    h2.relay_plan = [broken_relay]
    drop(first)
    await wait_until(h2, lambda: not h2.runtime.running and len(h2.relays) == 2)
    assert sleep2.delays == [2.0] and h2.runtime.service is not None and h2.runtime.service.end_reason == reason  # un único intento y se paró
    assert first.connections.state_of(client2.key.public_hex) is ClientState.REVOKED  # un fin no recuperable revoca, como siempre


async def test_a_tls_or_relay_configuration_error_is_not_retried() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    first = await h.start()
    client = await first.connect_client()
    h.relay_plan = [RelayError("grupo tls invalido")]  # la fábrica del relay falla: configuración, no red
    drop(first)
    await wait_until(h, lambda: sleep.delays == [2.0] and not h.runtime.running)
    await asyncio.sleep(0.05)
    assert sleep.delays == [2.0] and len(h.relays) == 1  # ni un segundo intento
    assert [e["error_type"] for e in h.runtime.audit.entries() if e["event"] == "error"][-1] == "configuracion_relay"
    assert h.runtime.status()["signer"]["state"] == "failed" and first.connections.is_active(client.key.public_hex)  # FAILED, conexiones conservadas


async def test_a_failure_at_the_very_first_start_is_not_retried_automatically() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    h.relay_kwargs = {"fail_connect": True}
    from app.services.runtime import StartFailed
    with pytest.raises(StartFailed):
        await h.runtime.start()
    await asyncio.sleep(0.05)
    assert sleep.delays == [] and h.runtime._supervisor is None and not h.runtime.running  # quien pulsó «Iniciar» recibe el error (502): no hay reintento escondido


# ------------------------------------------------------------------------------------------------ una sola tarea, sin carreras de arranque
async def test_there_is_a_single_supervisor_across_reconnections_and_no_tasks_are_left_after_stopping() -> None:
    sleep = FakeSleep()
    h = recon(sleep)
    rig = await h.start()
    supervisor = h.runtime._supervisor
    assert supervisor is not None
    tasks_before = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()}
    for _ in range(3):
        previous = h.runtime.service
        drop(h.current_rig())
        await wait_until(h, lambda: ready_again(h, previous))
        assert h.runtime._supervisor is supervisor  # el MISMO supervisor atiende todas las reconexiones
    await h.runtime.stop()
    await asyncio.sleep(0.05)
    leftover = {t for t in asyncio.all_tasks() if t is not asyncio.current_task()} - tasks_before
    assert supervisor.done() and not [t for t in leftover if not t.done()]  # nada huérfano
    assert rig.service is not h.runtime.service and h.runtime._task is not None and h.runtime._task.done()


async def test_two_simultaneous_starts_create_a_single_signer() -> None:
    h = recon(FakeSleep())
    results = await asyncio.gather(h.runtime.start(), h.runtime.start(), return_exceptions=True)
    assert sum(isinstance(r, AlreadyRunning) for r in results) == 1 and len(h.relays) == 1
    await h.runtime.stop()


# ------------------------------------------------------------------------------------------------ supervisado: sin cambios
async def test_supervised_mode_never_reconnects_and_keeps_revoking() -> None:
    sleep = FakeSleep()
    h = Harness("supervised", backoff=RECONNECT_BACKOFF_S, sleep=sleep)  # aunque se le pasen esperas, supervisado no reconecta
    rig = await h.start()
    client = await rig.connect_client()
    drop(rig)
    await wait_until(h, lambda: not h.runtime.running)
    await asyncio.sleep(0.05)
    assert sleep.delays == [] and h.runtime._supervisor is None and len(h.relays) == 1
    assert rig.connections.state_of(client.key.public_hex) is ClientState.REVOKED and rig.service.end_reason == "el_relay_cerro_la_conexion"
    assert h.runtime.status()["signer"]["state"] == "failed" and h.runtime.status()["signer"]["end_reason"] == "el_relay_cerro_la_conexion"


async def test_the_default_backoff_of_the_runtime_is_the_approved_one() -> None:
    runtime = SignerRuntime(Harness("continuous").settings)
    assert runtime._backoff == (2.0, 5.0, 10.0, 20.0, 40.0)

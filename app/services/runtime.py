"""Control de la instancia: identidad en memoria y ciclo de vida del firmante (lo que usa la API local de B3).

La clave privada vive SOLO en memoria (D-3): nunca se escribe en disco ni se devuelve. Cada `start()` crea un firmante y un registro de solicitudes
nuevos (las aprobaciones de una sesión no sirven en la siguiente). La auditoría es común.

Modo `supervised` (B6.2): cada `start()` crea también conexiones, clave de transporte y registros anti-replay nuevos (los secretos de una sesión no sirven en
la siguiente) y NO hay reconexión. Modo `continuous` (D-17): el runtime conserva ese estado (`ServiceState`) entre arranques mientras el proceso viva, así que tras
un fallo RECUPERABLE del relay las mismas conexiones siguen vigentes con la misma clave de transporte; una detención manual (o cualquier otro fin no recuperable)
revoca las conexiones, invalida el estado y el siguiente arranque crea uno nuevo (conservando solo los retos ya firmados, mientras no cambie la identidad). No hay
persistencia: reiniciar el proceso descarta identidad y conexiones.

Reconexión (solo `continuous`): un único supervisor por arranque vuelve a conectar con esperas de 2, 5, 10, 20 y 40 s ante una pérdida recuperable del relay (la
conexión se cerró o no se pudo abrir), con un transporte NUEVO en cada intento. No reconecta tras una detención manual, ni ante errores permanentes (el relay exige
AUTH, cierra la suscripción o la configuración TLS/relay es inválida). Agotados los intentos el firmante queda FAILED (`reconexion_agotada`) SIN perder las
conexiones: un «Iniciar» manual las reanuda. Detener y reconectar no se pisan: `stop()` fija la parada manual, cancela al supervisor y solo después detiene el servicio.
"""
import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final, Literal

from app.config import Settings
from app.nostr.errors import RelayError
from app.nostr.keys import Keypair
from app.nostr.relay import RelayTransport, WebsocketRelay
from app.services.approvals import ApprovalRegistry, PendingRequest
from app.services.audit import AuditLog
from app.services.connections import UnknownConnection
from app.services.session_state import RECOVERABLE_END_REASONS, ServiceState
from app.services.signer import SignerService, SignerState

STOP_WAIT_S = 10.0  # espera maxima a que `run()` termine tras pedir la parada; despues se cancela
RECONNECT_BACKOFF_S: Final = (2.0, 5.0, 10.0, 20.0, 40.0)  # esperas previas a cada intento: cinco intentos como máximo
RECONNECT_STABLE_S: Final = 60.0  # un firmante listo al menos este tiempo reinicia la cuenta de intentos (un relay que cae y vuelve sin parar no reconecta eternamente)
RECONNECTABLE_REASONS: Final = frozenset({"el_relay_cerro_la_conexion", "relay_no_disponible"})  # pérdidas recuperables del relay
RelayFactory = Callable[[Settings], RelayTransport]
Sleep = Callable[[float], Awaitable[None]]
AttemptOutcome = Literal["ready", "retry", "permanent"]


def default_relay_factory(settings: Settings) -> RelayTransport:
    return WebsocketRelay(settings.relay_url, tls_groups=settings.relay_tls_groups, allow_insecure=settings.relay_allow_insecure)


class NoIdentity(Exception):
    """No hay identidad cargada."""


class AlreadyRunning(Exception):
    """El firmante ya está en marcha."""


class NotRunning(Exception):
    """El firmante no está en marcha."""


class StartFailed(Exception):
    """El firmante no llegó a estar listo (sin detalles de red)."""


class SignerRuntime:
    def __init__(self, settings: Settings, *, relay_factory: RelayFactory = default_relay_factory, now: Callable[[], float] = time.time,
                 start_timeout_s: float = 15.0, sleep: Sleep = asyncio.sleep, backoff: Sequence[float] = RECONNECT_BACKOFF_S) -> None:
        self.settings, self._factory, self._now, self._start_timeout = settings, relay_factory, now, start_timeout_s
        self._sleep, self._backoff = sleep, tuple(backoff)  # inyectables SOLO para las pruebas; por defecto, las esperas aprobadas
        self.audit = AuditLog(now=now)
        self._identity: Keypair | None = None
        self.service: SignerService | None = None
        self._task: asyncio.Task[str] | None = None
        self._state: ServiceState | None = None  # solo modo continuo: estado que sobrevive a un fallo recuperable del relay
        self._lock = asyncio.Lock()  # serializa arranques y paradas (dos «Iniciar» simultáneos no crean dos firmantes)
        self._supervisor: asyncio.Task[None] | None = None  # una SOLA tarea de reconexión por arranque (solo modo continuo)
        self._manual_stop = False
        self._exhausted = False

    def now(self) -> float:
        return self._now()

    # ----------------------------------------------------------------------------------------- identidad
    @property
    def running(self) -> bool:
        """True mientras el firmante esté en marcha O el supervisor de reconexión siga vivo (esperando o reintentando)."""
        return (self.service is not None and self.service.running) or self._supervisor_alive

    @property
    def _supervisor_alive(self) -> bool:
        return self._supervisor is not None and not self._supervisor.done()

    @property
    def public_key(self) -> str | None:
        return self._identity.public_hex if self._identity else None

    def set_identity(self, keypair: Keypair) -> str:
        """Carga una identidad (creada o importada). Solo con el firmante detenido."""
        if self.running:
            raise AlreadyRunning
        self._identity = keypair
        self.service = None
        self._state = None  # otra identidad: ni las conexiones, ni la clave de transporte, ni los retos de la anterior sirven
        self._exhausted = False
        return keypair.public_hex

    # ----------------------------------------------------------------------------------------- ciclo de vida
    def _launch(self, state: ServiceState) -> tuple[SignerService, "asyncio.Task[str]"]:
        """Crea un firmante NUEVO (transporte nuevo) sobre el estado dado y lo pone a correr. `self.service` y `self._task` cambian juntos, sin `await` entre medias."""
        assert self._identity is not None
        service = SignerService(identity=self._identity, relay=self._factory(self.settings), settings=self.settings,
                                approvals=ApprovalRegistry(now=self._now, max_pending=self.settings.max_pending),
                                connections=state.connections, audit=self.audit, now=self._now, service_state=state)
        task = asyncio.create_task(service.run())
        self.service, self._task = service, task
        return service, task

    async def start(self) -> SignerService:
        async with self._lock:
            if self._identity is None:
                raise NoIdentity
            if self.running:
                raise AlreadyRunning
            await self._cancel_supervisor()  # defensivo: un supervisor ya terminado no debe quedar referenciado
            self._manual_stop, self._exhausted = False, False
            service, _task = self._launch(self._state_for_start())
            if not await service.wait_started(self._start_timeout):
                await self._stop_service("no_llego_a_estar_listo")
                raise StartFailed
            if self.settings.signer_mode == "continuous":
                self._supervisor = asyncio.create_task(self._supervise())
            return service

    def _state_for_start(self) -> ServiceState:
        """Estado para el próximo arranque. Supervisado: siempre nuevo. Continuo: el conservado, salvo que una parada no recuperable lo haya invalidado."""
        if self.settings.signer_mode != "continuous":
            return ServiceState.create(self.settings, self._now)
        previous = self._state
        if previous is not None and not previous.stale:
            return previous  # reanudación: misma clave de transporte, mismas conexiones y mismos registros anti-replay
        self._state = ServiceState.create(self.settings, self._now, challenges=previous.seen_challenges if previous is not None else None)
        return self._state

    async def stop(self, reason: str = "detenido_por_el_operador") -> None:
        if self.service is None or self._task is None:
            raise NotRunning
        self._manual_stop = True  # primero se fija la parada manual y se cancela al supervisor: así ninguna reconexión puede resucitar el servicio
        await self._cancel_supervisor()
        async with self._lock:
            await self._stop_service(reason)
            self._exhausted = False

    async def _stop_service(self, reason: str) -> None:
        service, task = self.service, self._task  # se relee: una reconexión en curso pudo haber cambiado el servicio
        if service is None or task is None:
            raise NotRunning
        await service.stop(reason)
        await self._finish_task(task)
        if self.settings.signer_mode == "continuous" and reason not in RECOVERABLE_END_REASONS:
            service.connections.revoke_all()  # cubre también la parada durante una espera de reconexión (no hay servicio en marcha que lo haga)
            service.service_state.invalidate()

    @staticmethod
    async def _finish_task(task: "asyncio.Task[str]") -> None:
        try:
            await asyncio.wait_for(asyncio.shield(task), STOP_WAIT_S)
        except TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - `run()` ya dejó session_end; aquí solo se evita propagar un fallo del relay
            pass

    async def shutdown(self) -> None:
        """Apagado de la aplicación: detiene el firmante (y cualquier reconexión) con evidencia de cierre. No falla si no estaba en marcha."""
        if self.running:
            with contextlib.suppress(NotRunning):
                await self.stop("apagado_de_la_aplicacion")

    # ----------------------------------------------------------------------------------------- reconexión (solo modo continuo)
    async def _cancel_supervisor(self) -> None:
        supervisor, self._supervisor = self._supervisor, None
        if supervisor is not None and not supervisor.done():
            supervisor.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await supervisor

    @staticmethod
    def _retrieve(task: "asyncio.Task[str]") -> None:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            task.result()  # marca como recuperada cualquier excepción de la sesión (ya quedó en la auditoría)

    def _should_reconnect(self, service: SignerService) -> bool:
        return (self.settings.signer_mode == "continuous" and not self._manual_stop and not service.stop_requested
                and service.end_reason in RECONNECTABLE_REASONS and not service.service_state.stale)

    async def _supervise(self) -> None:
        """Vigila el servicio en marcha y, si el relay se pierde de forma recuperable, reconecta con las esperas aprobadas. Una sola tarea por arranque."""
        failures, ready_at = 0, self._now()
        while True:
            service, task = self.service, self._task
            assert service is not None and task is not None
            await asyncio.wait({task})  # si se cancela al supervisor, el servicio NO se cancela (lo detiene `stop()`)
            self._retrieve(task)
            if not self._should_reconnect(service):
                return  # parada manual, error permanente o motivo no recuperable: no se reconecta
            if self._now() - ready_at >= RECONNECT_STABLE_S:
                failures = 0
            while True:
                if failures >= len(self._backoff):
                    self._exhausted = True
                    self.audit.emit("reconnect_exhausted", attempts=len(self._backoff))
                    return  # FAILED con las conexiones conservadas: se reanuda con un «Iniciar» manual
                delay = self._backoff[failures]
                failures += 1
                self.audit.emit("relay_reconnect", attempt=failures, max_attempts=len(self._backoff), delay_s=int(delay))
                await self._sleep(delay)
                outcome = await self._attempt()
                if outcome == "ready":
                    ready_at = self._now()
                    break
                if outcome == "permanent":
                    return

    async def _attempt(self) -> AttemptOutcome:
        state = self._state
        if state is None or state.stale:
            return "permanent"
        try:
            service, task = self._launch(state)
        except RelayError:  # configuración del relay o de TLS inválida: no se arregla reintentando
            self.audit.emit("error", where="relay", error_type="configuracion_relay")
            return "permanent"
        if await service.wait_started(self._start_timeout):
            return "ready"
        if service.running:  # no llegó a estar listo a tiempo: se detiene ordenadamente este intento
            await service.stop("no_llego_a_estar_listo")
        await self._finish_task(task)
        # Solo una pérdida recuperable (o no llegar a tiempo) se reintenta. AUTH y suscripción cerrada terminan la sesión como fin NO recuperable: invalidan el estado.
        transient = service.end_reason in (*RECONNECTABLE_REASONS, "no_llego_a_estar_listo") and not state.stale
        return "retry" if transient else "permanent"

    # ----------------------------------------------------------------------------------------- conexiones
    def revoke_connection(self, connection_id: str) -> None:
        """Revoca una conexión por su id opaco. `UnknownConnection` si no pertenece al estado activo del runtime (o no hay firmante)."""
        if self.service is None:
            raise UnknownConnection
        self.service.revoke_connection(connection_id)

    # ----------------------------------------------------------------------------------------- consultas
    def requests(self, scope: str = "pending") -> list[PendingRequest]:
        if self.service is None:
            return []
        reg = self.service.approvals
        return reg.pending() if scope == "pending" else reg.recent() if scope == "recent" else [*reg.pending(), *reg.recent()]

    def status(self) -> dict[str, Any]:
        base: dict[str, Any] = {"identity": {"present": self._identity is not None, "public_key": self.public_key}}
        if self.service is None:
            base["signer"] = {"state": SignerState.IDLE.value, "relay_host": None, "signatures": 0, "max_signatures": None if self.settings.signer_mode == "continuous" else self.settings.max_signatures,
                              "end_reason": None, "pending": 0, "connections_active": 0, "connections_pending": 0, "connections_unused_secrets": 0}
            return base
        signer = self.service.status()
        if self._supervisor_alive and not self.service.running:
            signer["state"] = "reconnecting"  # esperando o reintentando la conexión con el relay
        elif self._exhausted:
            signer["end_reason"] = "reconexion_agotada"  # FAILED, con las conexiones conservadas: «Iniciar» las reanuda
        base["signer"] = signer
        return base

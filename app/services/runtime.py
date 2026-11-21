"""Control de la instancia: identidad en memoria y ciclo de vida del firmante (lo que usa la API local de B3).

La clave privada vive SOLO en memoria (D-3): nunca se escribe en disco ni se devuelve. Cada `start()` crea un firmante, un registro de
conexiones y uno de solicitudes nuevos (los secretos y las aprobaciones de una sesión no sirven en la siguiente). La auditoría es común.
"""
import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import Any

from app.config import Settings
from app.nostr.keys import Keypair
from app.nostr.relay import RelayTransport, WebsocketRelay
from app.services.approvals import ApprovalRegistry, PendingRequest
from app.services.audit import AuditLog
from app.services.connections import ConnectionManager
from app.services.signer import SignerService, SignerState

STOP_WAIT_S = 10.0  # espera maxima a que `run()` termine tras pedir la parada; despues se cancela
RelayFactory = Callable[[Settings], RelayTransport]


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
                 start_timeout_s: float = 15.0) -> None:
        self.settings, self._factory, self._now, self._start_timeout = settings, relay_factory, now, start_timeout_s
        self.audit = AuditLog(now=now)
        self._identity: Keypair | None = None
        self.service: SignerService | None = None
        self._task: asyncio.Task[str] | None = None

    def now(self) -> float:
        return self._now()

    # ----------------------------------------------------------------------------------------- identidad
    @property
    def running(self) -> bool:
        return self.service is not None and self.service.running

    @property
    def public_key(self) -> str | None:
        return self._identity.public_hex if self._identity else None

    def set_identity(self, keypair: Keypair) -> str:
        """Carga una identidad (creada o importada). Solo con el firmante detenido."""
        if self.running:
            raise AlreadyRunning
        self._identity = keypair
        self.service = None
        return keypair.public_hex

    # ----------------------------------------------------------------------------------------- ciclo de vida
    async def start(self) -> SignerService:
        if self._identity is None:
            raise NoIdentity
        if self.running:
            raise AlreadyRunning
        service = SignerService(identity=self._identity, relay=self._factory(self.settings), settings=self.settings,
                                approvals=ApprovalRegistry(now=self._now, max_pending=self.settings.max_pending),
                                connections=ConnectionManager(now=self._now, secret_ttl_s=self.settings.secret_ttl_s,
                                                              connection_ttl_s=self.settings.connection_ttl_s),
                                audit=self.audit, now=self._now)
        self.service = service
        self._task = asyncio.create_task(service.run())
        if not await service.wait_started(self._start_timeout):
            await self.stop("no_llego_a_estar_listo")
            raise StartFailed
        return service

    async def stop(self, reason: str = "detenido_por_el_operador") -> None:
        service, task = self.service, self._task
        if service is None or task is None:
            raise NotRunning
        await service.stop(reason)
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
        """Apagado de la aplicación: detiene el firmante con evidencia de cierre. No falla si no estaba en marcha."""
        if self.running:
            with contextlib.suppress(NotRunning):
                await self.stop("apagado_de_la_aplicacion")

    # ----------------------------------------------------------------------------------------- consultas
    def requests(self, scope: str = "pending") -> list[PendingRequest]:
        if self.service is None:
            return []
        reg = self.service.approvals
        return reg.pending() if scope == "pending" else reg.recent() if scope == "recent" else [*reg.pending(), *reg.recent()]

    def status(self) -> dict[str, Any]:
        base: dict[str, Any] = {"identity": {"present": self._identity is not None, "public_key": self.public_key}}
        if self.service is None:
            base["signer"] = {"state": SignerState.IDLE.value, "relay_host": None, "signatures": 0, "max_signatures": self.settings.max_signatures,
                              "end_reason": None, "pending": 0, "connections_active": 0, "connections_pending": 0, "connections_unused_secrets": 0}
        else:
            base["signer"] = self.service.status()
        return base

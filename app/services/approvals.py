"""Solicitudes pendientes de decisión del operador (en memoria). Cada aprobación queda vinculada a UNA solicitud concreta.

El firmante crea una solicitud (`connect` o `sign_event`) y espera su resolución; la API la resuelve con `resolve`. Denegar por defecto:
una solicitud sin decisión a tiempo caduca como denegada, y al detener el firmante las pendientes se cancelan. No hay aprobación automática
ni autorizaciones persistentes: una aprobación sirve para esa solicitud y nada más.
"""
import asyncio
import secrets
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RequestKind(StrEnum):
    CONNECT = "connect"
    SIGN_EVENT = "sign_event"


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class UnknownRequest(Exception):
    """No existe una solicitud con ese identificador."""


class AlreadyResolved(Exception):
    """La solicitud ya se resolvió, caducó o se canceló."""


class TooManyPending(Exception):
    """Hay demasiadas solicitudes pendientes."""


@dataclass(eq=False)
class PendingRequest:
    id: str
    kind: RequestKind
    client8: str
    created_at: float
    expires_at: float
    summary: dict[str, Any]
    checks: list[dict[str, Any]]
    status: RequestStatus = RequestStatus.PENDING
    reason: str | None = None
    decided_at: float | None = None
    binding: str | None = None  # huella de lo que se ofrecio al operador (P-38): la firma solo procede si lo que se firma coincide
    consumed: bool = False  # una aprobacion se gasta UNA vez, al intentar firmar (haya o no exito)
    # P-42: RESULTADO real de una firma tras la aprobacion humana. `status` sigue siendo la decision del operador (compatibilidad); `outcome` dice que paso
    # despues: None = aprobada y aun sin resultado, `signed` = firma producida y autoverificada, `refused` = rechazada al firmar (revalidacion o reto/tope) y
    # `failed` = fallo interno o la sesion termino antes del resultado. Solo se usa en `sign_event`.
    outcome: str | None = None
    outcome_reason: str | None = None  # codigo corto y fijo (nunca texto libre del cliente ni datos de la plantilla)
    # B6.1D-R3: instante (reloj del servidor, EXCLUSIVO) a partir del cual la politica ya NO acepta firmar esta plantilla: `created_at + ventana + 1`. Es el plazo
    # EFECTIVO para firmar, distinto de `expires_at` (TTL de la aprobacion). Solo informa a la interfaz; la politica y la revalidacion no cambian.
    sign_deadline: float | None = None
    owner: str | None = None  # id OPACO de la conexión que originó la solicitud (D-17): permite cancelar solo las suyas al revocarla; nunca se expone
    _future: "asyncio.Future[bool]" = field(init=False, repr=False)

    def public(self, now: float) -> dict[str, Any]:
        """Vista sanitizada para la API: nunca contiene secretos, el reto ni el evento completo."""
        return {"id": self.id, "kind": self.kind.value, "status": self.status.value, "client": self.client8, "reason": self.reason,
                "expires_in_s": max(0, round(self.expires_at - now)) if self.status is RequestStatus.PENDING else 0,
                "summary": self.summary, "checks": self.checks, "outcome": self.outcome, "outcome_reason": self.outcome_reason,
                "sign_expires_in_s": self._sign_left(now)}

    def _sign_left(self, now: float) -> int | None:
        """Segundos que quedan para poder FIRMAR (plazo real de la politica), solo para firmas pendientes. Por defecto (floor) no sobreestima."""
        if self.sign_deadline is None or self.status is not RequestStatus.PENDING:
            return None
        return max(0, int(self.sign_deadline - now))


class ApprovalRegistry:
    def __init__(self, *, now: Callable[[], float], max_pending: int = 16, history: int = 100) -> None:
        self._now, self._max_pending = now, max_pending
        self._pending: dict[str, PendingRequest] = {}
        self._done: deque[PendingRequest] = deque(maxlen=history)

    def create(self, kind: RequestKind, client8: str, summary: dict[str, Any], checks: list[dict[str, Any]], ttl_s: float,
               binding: str | None = None, sign_deadline: float | None = None, owner: str | None = None) -> PendingRequest:
        if len(self._pending) >= self._max_pending:
            raise TooManyPending
        now = self._now()
        req = PendingRequest(secrets.token_urlsafe(9), kind, client8, now, now + ttl_s, summary, checks, binding=binding, sign_deadline=sign_deadline, owner=owner)
        req._future = asyncio.get_running_loop().create_future()
        self._pending[req.id] = req
        return req

    def _finish(self, req: PendingRequest, status: RequestStatus, reason: str) -> None:
        req.status, req.reason, req.decided_at = status, reason, self._now()
        self._pending.pop(req.id, None)
        self._done.append(req)
        if not req._future.done():
            req._future.set_result(status is RequestStatus.APPROVED)

    async def wait(self, req: PendingRequest, ttl_s: float) -> tuple[bool, str]:
        """Espera la decisión (hasta `ttl_s`). Devuelve (aprobada, motivo): `humano`, `timeout` o `cancelada`."""
        try:
            await asyncio.wait_for(asyncio.shield(req._future), ttl_s)
        except TimeoutError:
            if req.status is RequestStatus.PENDING:
                self._finish(req, RequestStatus.EXPIRED, "timeout")
        return req.status is RequestStatus.APPROVED, req.reason or "cancelada"

    def resolve(self, request_id: str, approve: bool) -> PendingRequest:
        req = self._pending.get(request_id)
        if req is None:
            if any(r.id == request_id for r in self._done):
                raise AlreadyResolved
            raise UnknownRequest
        if self._now() >= req.expires_at:
            self._finish(req, RequestStatus.EXPIRED, "timeout")
            raise AlreadyResolved
        self._finish(req, RequestStatus.APPROVED if approve else RequestStatus.DENIED, "humano")
        return req

    def consume(self, req: PendingRequest) -> str | None:
        """Gasta la aprobacion de `req` JUSTO antes de firmar (P-38). Devuelve `None` si sigue siendo valida o el motivo del rechazo.

        Sincrono y sin `await`: entre esta comprobacion y la firma no puede intercalarse otra tarea. La aprobacion queda consumida aunque se rechace
        (falla de forma segura: no se reintenta con la misma decision). Debe estar aprobada por una persona, no consumida y dentro de su vigencia.
        """
        if req.consumed:
            return "aprobacion_consumida"
        req.consumed = True
        if req.status is not RequestStatus.APPROVED or req.reason != "humano":
            return "aprobacion_no_vigente"
        if self._now() >= req.expires_at:
            return "aprobacion_caducada"
        return None

    def set_outcome(self, req: PendingRequest, outcome: str, reason: str | None = None) -> None:
        """Registra el resultado de una firma aprobada (P-42). Solo una vez: un resultado ya fijado no se sobrescribe."""
        if req.outcome is None:
            req.outcome, req.outcome_reason = outcome, reason

    def finalize_unresolved(self, reason: str) -> int:
        """Al terminar la sesion: toda firma aprobada que quedo SIN resultado pasa a `failed` (no puede quedar eternamente «pendiente de resultado»)."""
        stale = [r for r in self._done if r.kind is RequestKind.SIGN_EVENT and r.status is RequestStatus.APPROVED and r.outcome is None]
        for req in stale:
            self.set_outcome(req, "failed", reason)
        return len(stale)

    def cancel_owner(self, owner: str, reason: str) -> int:
        """Cancela las solicitudes PENDIENTES de una conexión (p. ej. al revocarla). Las de otras conexiones no se tocan."""
        mine = [r for r in self._pending.values() if r.owner == owner]
        for req in mine:
            self._finish(req, RequestStatus.CANCELLED, reason)
        return len(mine)

    def cancel_all(self, reason: str) -> int:
        pending = list(self._pending.values())
        for req in pending:
            self._finish(req, RequestStatus.CANCELLED, reason)
        return len(pending)

    def pending(self) -> list[PendingRequest]:
        return sorted(self._pending.values(), key=lambda r: r.created_at)

    def recent(self, limit: int = 50) -> list[PendingRequest]:
        return list(self._done)[-limit:]

    def get(self, request_id: str) -> PendingRequest | None:
        return self._pending.get(request_id) or next((r for r in self._done if r.id == request_id), None)

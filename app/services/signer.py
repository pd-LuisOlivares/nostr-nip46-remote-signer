"""Servicio firmante NIP-46 (B2): recibe solicitudes por un relay, aplica la política y firma SOLO con aprobación explícita del operador.

Separación de responsabilidades: la IDENTIDAD (`Keypair` del usuario) solo firma el evento de login aprobado; la clave de TRANSPORTE
(distinta, generada por sesión) firma y cifra las respuestas; la POLÍTICA (`policy.py`) decide si un evento es firmable; las CONEXIONES
(`connections.py`) administran secretos y clientes; las APROBACIONES (`approvals.py`) vinculan cada decisión humana a una solicitud concreta.

Reglas: denegar por defecto; eventos de transporte con firma o id inválidos, ventana excedida, `p` ajeno o repetidos NO se descifran ni
responden; NIP-04 solo se descifra (entrante) y las respuestas son SIEMPRE NIP-44; solo `kind 27235`; una aprobación = una firma de un reto;
cada firma se autoverifica antes de responder; los errores hacia el cliente son genéricos; una sola conexión al relay y cierre ordenado que
deja siempre `session_end` (incluso ante cancelación o error).
"""
import asyncio
import contextlib
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from app.config import Settings
from app.nostr import nip04, nip44
from app.nostr.errors import (InvalidEventError, InvalidKeyError, InvalidNip46Message, Nip04Error, Nip44Error, RelayError, SigningError)
from app.nostr.event import NostrEvent, parse_and_verify_event, sign_event, verify_event
from app.nostr.keys import Keypair
from app.nostr.nip46 import NIP46_KIND, Nip46Response, build_bunker_uri, parse_request
from app.nostr.relay import RelayAuth, RelayEose, RelayEvent, RelayNotice, RelayOk, RelayTransport
from app.services.approvals import ApprovalRegistry, PendingRequest, RequestKind, TooManyPending
from app.services.audit import AuditLog
from app.services.connections import ClientState, ConnectionManager, TooManyClients
from app.services.policy import PolicyConfig, PolicyResult, challenge_hash, evaluate, safe_text

MAX_CONCURRENT_HANDLERS = 64
MAX_PENDING_OK = 256


class SignerState(StrEnum):
    IDLE = "idle"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class NotReady(Exception):
    """El firmante no está listo (sin suscripción activa en el relay)."""


class SignerService:
    def __init__(self, *, identity: Keypair, relay: RelayTransport, settings: Settings, approvals: ApprovalRegistry, connections: ConnectionManager,
                 audit: AuditLog, now: Callable[[], float] = time.time) -> None:
        self.identity, self.relay, self.settings = identity, relay, settings
        self.approvals, self.connections, self.audit, self._now = approvals, connections, audit, now
        self.transport = Keypair.generate()  # clave de transporte: DISTINTA de la identidad
        self.policy = PolicyConfig(settings.service_origin, window_s=settings.window_s)
        self.state = SignerState.IDLE
        self.end_reason: str | None = None
        self.signatures = 0
        self.requests = 0
        self._seen_events: set[str] = set()
        self._seen_requests: set[tuple[str, str]] = set()
        self._seen_challenges: set[str] = set()
        self._pending_ok: dict[str, str] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._stop_requested = False

    # ------------------------------------------------------------------------------------------- ciclo de vida
    @property
    def running(self) -> bool:
        return self.state in (SignerState.STARTING, SignerState.READY, SignerState.STOPPING)

    def _end(self, reason: str) -> None:
        if self.end_reason is None:
            self.end_reason = reason

    async def wait_started(self, timeout: float) -> bool:
        """True cuando el firmante está listo; False si terminó o no llegó a tiempo."""
        async def starting() -> None:
            while self.state in (SignerState.IDLE, SignerState.STARTING):
                await asyncio.sleep(0.01)

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(starting(), timeout)
        return self.state is SignerState.READY

    async def run(self) -> str:
        """Atiende al relay hasta que se detenga. Siempre deja `session_end`, incluso ante cancelación o error."""
        self.state = SignerState.STARTING
        s = self.settings
        self.audit.emit("session_start", relay_host=self.relay.host, origin=s.service_origin, max_signatures=s.max_signatures, window_s=s.window_s,
                        tls_groups=s.relay_tls_groups or "por_defecto")
        watchdog: asyncio.Task[None] | None = None
        try:
            await self.relay.connect()
            await self.relay.subscribe(self.transport.public_hex, int(self._now()) - s.window_s)
            watchdog = asyncio.create_task(self._watchdog())
            async for msg in self.relay.messages():
                if isinstance(msg, RelayEose):
                    if self.state is SignerState.STARTING:
                        self.state = SignerState.READY
                        self.audit.emit("relay_ready")
                elif isinstance(msg, RelayEvent):
                    self._spawn(msg.event)
                elif isinstance(msg, RelayOk):
                    method = self._pending_ok.pop(msg.event_id, None)
                    if method is not None:
                        self.audit.emit("response_published", method=method, relay_ok=msg.accepted, relay_message=safe_text(msg.message, 60))
                elif isinstance(msg, RelayNotice):
                    self.audit.emit("relay_notice", kind=msg.kind, message=safe_text(msg.message, 80))
                    if msg.kind == "CLOSED":
                        self._end("el_relay_cerro_la_suscripcion")
                elif isinstance(msg, RelayAuth):
                    self.audit.emit("relay_notice", kind="AUTH", message="el relay pidio autenticacion; no se responde")
                    self._end("el_relay_exige_auth")
                if self.end_reason is not None:
                    break
            self._end("el_relay_cerro_la_conexion")
        except RelayError:
            self.audit.emit("error", where="relay", error_type="RelayError")
            self._end("relay_no_disponible")
        except asyncio.CancelledError:
            self._end("cancelado")
            raise
        finally:
            await self._shutdown(watchdog)
        return self.end_reason or "sin_motivo"

    async def _shutdown(self, watchdog: asyncio.Task[None] | None) -> None:
        self.state = SignerState.STOPPING
        for task in [t for t in (watchdog, *self._tasks) if t is not None]:
            task.cancel()
        await asyncio.gather(*[t for t in (watchdog, *self._tasks) if t is not None], return_exceptions=True)
        self.approvals.cancel_all("cancelada")
        self.connections.revoke_all()
        with contextlib.suppress(Exception):  # el cierre del relay no debe impedir dejar la evidencia de cierre
            await self.relay.close()
        reason = self.end_reason or "sin_motivo"
        self.state = SignerState.STOPPED if self._stop_requested or reason in ("vida_maxima_de_sesion", "tope_de_solicitudes") else SignerState.FAILED
        self.audit.emit("session_end", reason=reason, signatures=self.signatures)

    async def stop(self, reason: str = "detenido_por_el_operador") -> None:
        """Detiene el firmante de forma ordenada: `run()` termina y deja `session_end` con este motivo."""
        if self.running and not self._stop_requested:
            self._stop_requested = True
            self._end(reason)
            await self.relay.close()

    async def _watchdog(self) -> None:
        await asyncio.sleep(self.settings.session_ttl_s)
        await self.stop("vida_maxima_de_sesion")

    # ------------------------------------------------------------------------------------------- URI
    def issue_bunker_uri(self) -> str:
        """URI `bunker://` de un solo uso. Solo con el firmante listo. Se devuelve UNA vez y nunca se registra."""
        if self.state is not SignerState.READY:
            raise NotReady
        secret = self.connections.issue_secret()  # puede lanzar TooManySecrets
        uri = build_bunker_uri(self.transport.public_hex, [self.settings.relay_url], secret, allow_insecure_relays=self.settings.relay_allow_insecure)
        self.audit.emit("bunker_issued", transport_pub8=self.transport.public_hex[:8], ttl_s=self.settings.secret_ttl_s)
        return uri

    def status(self) -> dict[str, Any]:
        return {"state": self.state.value, "relay_host": self.relay.host, "signatures": self.signatures, "max_signatures": self.settings.max_signatures,
                "end_reason": self.end_reason, "pending": len(self.approvals.pending()), **{f"connections_{k}": v for k, v in self.connections.counts().items()}}

    # ------------------------------------------------------------------------------------------- eventos de transporte
    def _spawn(self, raw: dict[str, object]) -> None:
        if len(self._tasks) >= MAX_CONCURRENT_HANDLERS:
            self.audit.emit("error", where="transporte", error_type="saturado")
            return
        task = asyncio.create_task(self._guarded(raw))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _guarded(self, raw: dict[str, object]) -> None:
        try:
            await self.handle_event(raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - una solicitud rota no debe tumbar la sesión; se registra solo el tipo
            self.audit.emit("error", where="manejador", error_type=type(exc).__name__)

    async def handle_event(self, raw: dict[str, object]) -> None:
        """Valida el evento de transporte (firma e id ANTES de descifrar), descifra, despacha y responde."""
        try:
            event = parse_and_verify_event(raw)
        except InvalidEventError:
            self.audit.emit("error", where="transporte", error_type="evento_descartado")
            return
        now = self._now()
        if (event.kind != NIP46_KIND or not any(t[:2] == ("p", self.transport.public_hex) for t in event.tags)
                or abs(now - event.created_at) > self.settings.window_s or event.id in self._seen_events):
            self.audit.emit("error", where="transporte", error_type="evento_descartado")
            return
        self._seen_events.add(event.id)
        self.requests += 1
        if self.requests > self.settings.max_requests:
            self._end("tope_de_solicitudes")
            await self.relay.close()
            return
        client = event.pubkey
        scheme = "nip04" if "?iv=" in event.content else "nip44"
        try:
            plaintext = (nip04.decrypt(self.transport, client, event.content) if scheme == "nip04"
                         else nip44.decrypt(event.content, nip44.get_conversation_key(self.transport, client)))
            request = parse_request(plaintext)
        except (Nip04Error, Nip44Error, InvalidNip46Message, InvalidKeyError) as exc:
            self.audit.emit("error", where="solicitud", error_type=type(exc).__name__)  # no se distingue hacia el exterior
            return
        if (client, request.id) in self._seen_requests:
            self.audit.emit("error", where="solicitud", error_type="id_repetido")
            return
        self._seen_requests.add((client, request.id))
        self.audit.emit("request", method=safe_text(request.method, 24), scheme=scheme, client8=client[:8])
        result, error = await self._dispatch(client, request.method, request.params)
        await self._respond(client, request.id, request.method, result, error)

    async def _dispatch(self, client: str, method: str, params: list[str]) -> tuple[str | None, str | None]:
        if method == "connect":
            return await self._on_connect(client, params)
        if not self.connections.is_active(client):
            return None, "unauthorized"
        if method == "get_public_key":
            return self.identity.public_hex, None  # nunca un error a un cliente activo (P-19)
        if method == "ping":
            return "pong", None
        if method == "sign_event":
            return await self._on_sign(client, params)
        return None, "unsupported method"

    async def _respond(self, client: str, request_id: str, method: str, result: str | None, error: str | None) -> None:
        response = Nip46Response.fail(request_id, error) if error is not None else Nip46Response.ok(request_id, result or "")
        content = nip44.encrypt(response.to_json(), nip44.get_conversation_key(self.transport, client))  # respuestas SIEMPRE en NIP-44
        out = sign_event(self.transport, NIP46_KIND, [["p", client]], content, int(self._now()))
        if len(self._pending_ok) < MAX_PENDING_OK:
            self._pending_ok[out.id] = method if method in ("connect", "get_public_key", "sign_event", "ping") else "otro"
        try:
            await self.relay.publish(out)
        except RelayError:
            self.audit.emit("error", where="relay", error_type="RelayError")
            self._end("relay_no_disponible")
            await self.relay.close()

    # ------------------------------------------------------------------------------------------- aprobaciones
    async def _ask(self, kind: RequestKind, client: str, summary: dict[str, Any], checks: list[dict[str, Any]]) -> tuple[bool, str, PendingRequest | None]:
        try:
            req = self.approvals.create(kind, client[:8], summary, checks, self.settings.approval_ttl_s)
        except TooManyPending:
            self.audit.emit("decision", request_id="-", kind=kind.value, approved=False, reason="demasiadas_pendientes", latency_ms=0)
            return False, "demasiadas_pendientes", None
        self.audit.emit("pending_created", request_id=req.id, kind=kind.value, client8=client[:8], ttl_s=self.settings.approval_ttl_s)
        t0 = time.monotonic()
        approved, reason = await self.approvals.wait(req, self.settings.approval_ttl_s)
        self.audit.emit("decision", request_id=req.id, kind=kind.value, approved=approved, reason=reason, latency_ms=int((time.monotonic() - t0) * 1000))
        return approved, reason, req

    async def _on_connect(self, client: str, params: list[str]) -> tuple[str | None, str | None]:
        state = self.connections.state_of(client)
        if state is ClientState.ACTIVE:
            return "ack", None
        if state is not None:
            return None, "unauthorized"  # pendiente, denegado o revocado
        if not self.connections.consume_secret(params[1] if len(params) >= 2 else ""):
            return None, "unauthorized"
        try:
            self.connections.begin(client)
        except TooManyClients:
            return None, "unauthorized"
        summary = {"client": client[:8], "note": "el secreto de la URI fue valido"}
        approved, _reason, _req = await self._ask(RequestKind.CONNECT, client, summary, [])
        if not approved:
            self.connections.deny(client)
            return None, "unauthorized"
        self.connections.activate(client)
        return "ack", None

    async def _on_sign(self, client: str, params: list[str]) -> tuple[str | None, str | None]:
        if self.signatures >= self.settings.max_signatures:
            self.audit.emit("decision", request_id="-", kind="sign_event", approved=False, reason="tope", latency_ms=0)
            return None, "unauthorized"
        if len(params) != 1:
            return None, "invalid params"
        result = evaluate(params[0], self.identity.public_hex, int(self._now()), self._seen_challenges, self.policy)
        self.audit.emit("policy", ok=result.ok, failed=result.failed, origin_seen=result.origin_seen, content_ok=result.content_ok,
                        challenge_sha16=result.challenge_sha16, created_at_age_s=result.created_at_age_s)
        if not result.ok or result.template is None:
            return None, "unauthorized"  # una solicitud que incumple la política NO se ofrece al operador
        summary = {"kind": result.template.kind, "service": self.settings.service_origin, "identity": self.identity.public_hex[:8],
                   "u": result.origin_seen, "content": safe_text(result.template.content), "created_at_age_s": result.created_at_age_s,
                   "challenge_sha16": result.challenge_sha16, "client": client[:8]}
        approved, _reason, _req = await self._ask(RequestKind.SIGN_EVENT, client, summary, _checks(result))
        if not approved:
            return None, "unauthorized"
        return self._sign_once(result)

    def _sign_once(self, result: PolicyResult) -> tuple[str | None, str | None]:
        """Consume la aprobación de forma atómica (sin `await`) ANTES de firmar: dos solicitudes simultáneas no obtienen dos firmas."""
        template = result.template
        assert template is not None and result.challenge_sha16 is not None
        c_hash = challenge_hash(template.tags[0][1])
        if c_hash in self._seen_challenges or self.signatures >= self.settings.max_signatures:
            self.audit.emit("decision", request_id="-", kind="sign_event", approved=False, reason="reutilizacion_o_tope", latency_ms=0)
            return None, "unauthorized"
        self._seen_challenges.add(c_hash)
        self.signatures += 1
        try:
            signed = sign_event(self.identity, template.kind, template.tags, template.content, template.created_at)
            verify_event(signed)  # autoverificación antes de responder
            unchanged = (signed.pubkey == self.identity.public_hex and signed.tags == template.tags and signed.content == template.content
                         and signed.created_at == template.created_at and signed.kind == template.kind)
        except (InvalidEventError, SigningError):
            unchanged = False
        if not unchanged:
            self.audit.emit("error", where="firma", error_type="autoverificacion")
            return None, "internal error"
        self.audit.emit("sign_ok", event_id16=signed.id[:16], self_verify=True)
        return _event_json(signed), None


def _checks(result: PolicyResult) -> list[dict[str, Any]]:
    return [{"name": c.name, "ok": c.ok, "detail": c.detail if not c.ok else ""} for c in result.checks]


def _event_json(event: NostrEvent) -> str:
    return event.to_json()

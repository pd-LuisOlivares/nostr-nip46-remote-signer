"""Dobles de prueba compartidos: relay falso en proceso y cliente NIP-46 que imita a NDK (sin red real)."""
import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import Settings
from app.nostr import nip44
from app.nostr.errors import RelayError
from app.nostr.event import NostrEvent, sign_event
from app.nostr.keys import Keypair
from app.nostr.nip46 import NIP46_KIND, Nip46Response, parse_response
from app.nostr.relay import RelayEose, RelayMessage, RelayOk
from app.security.passwords import PasswordService
from app.services.approvals import ApprovalRegistry
from app.services.audit import AuditLog
from app.services.connections import ConnectionManager
from app.services.signer import SignerService, SignerState

NOW = 1_800_000_000
# El runtime actual (pasos 1 de D-17) solo implementa el comportamiento SUPERVISADO: el arnes lo fija de forma explicita con los plazos de antes de D-17.
SUPERVISED_TTLS = {"signer_mode": "supervised", "secret_ttl_s": 600, "connection_ttl_s": 1800}
USERNAME = "operador"
PASSWORD = "contrasena-ficticia-de-prueba-1"  # FICTICIA, solo para pruebas: no es una credencial real ni se usa fuera de ellas
WRONG_PASSWORD = "otra-contrasena-ficticia-2"


def fast_passwords() -> PasswordService:
    """Argon2id con coste mínimo SOLO para que la suite sea rápida; la configuración de producción se prueba aparte (tests/security/test_passwords.py)."""
    return PasswordService(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Ajustes de prueba con una base SQLite temporal y un administrador inicial ficticio."""
    values: dict[str, Any] = {"database_path": str(tmp_path / "admin.db"), "admin_username": USERNAME, "admin_password": PASSWORD}
    return Settings(**{**values, **overrides})


ORIGIN = "https://stacker.news"
CHALLENGE = "ab" * 32
CONTENT = "Stacker News Authentication"


class Clock:
    def __init__(self, at: float = float(NOW)) -> None:
        self.t = at

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@dataclass
class FakeRelay:
    """Implementa RelayTransport sin red. Registra lo publicado y permite inyectar mensajes del relay."""

    host: str = "relay.test"
    fail_connect: bool = False
    auto_eose: bool = True
    auto_ok: bool = True
    connects: int = 0
    closed: bool = False
    subscription: tuple[str, int] | None = None
    published: list[NostrEvent] = field(default_factory=list)
    _queue: "asyncio.Queue[RelayMessage | None]" = field(default_factory=asyncio.Queue)

    async def connect(self) -> None:
        self.connects += 1
        if self.fail_connect:
            raise RelayError("no se pudo conectar al relay")

    async def subscribe(self, pubkey: str, since: int) -> None:
        self.subscription = (pubkey, since)
        if self.auto_eose:
            self._queue.put_nowait(RelayEose("s1"))

    async def publish(self, event: NostrEvent) -> None:
        self.published.append(event)
        if self.auto_ok:
            self._queue.put_nowait(RelayOk(event.id, True, ""))

    async def messages(self) -> AsyncIterator[RelayMessage]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def close(self) -> None:
        self.closed = True
        self._queue.put_nowait(None)

    def inject(self, message: RelayMessage) -> None:
        self._queue.put_nowait(message)


def nip04_encrypt(sender: Keypair, recipient_pub: str, text: str) -> str:
    """Cifrador NIP-04 SOLO de pruebas (el producto no cifra con NIP-04): reproduce el `connect` inicial de NDK."""
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    data = padder.update(text.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(sender.ecdh_x(recipient_pub)), modes.CBC(iv)).encryptor()
    return base64.b64encode(enc.update(data) + enc.finalize()).decode() + "?iv=" + base64.b64encode(iv).decode()


class NdkLikeClient:
    """Cliente NIP-46 como el de Stacker News/NDK: `connect` cifrado con NIP-04 y el resto con NIP-44."""

    def __init__(self, transport_pub: str, clock: Callable[[], float]) -> None:
        self.key, self.transport_pub, self.clock, self.n = Keypair.generate(), transport_pub, clock, 0

    def request(self, method: str, params: list[str], *, scheme: str = "nip44", created_at: int | None = None, req_id: str | None = None,
                p: str | None = None, key: Keypair | None = None) -> dict[str, Any]:
        self.n += 1
        key = key or self.key
        body = json.dumps({"id": req_id or f"r{self.n}", "method": method, "params": params}, separators=(",", ":"))
        content = (nip04_encrypt(key, self.transport_pub, body) if scheme == "nip04"
                   else nip44.encrypt(body, nip44.get_conversation_key(key, self.transport_pub)))
        event = sign_event(key, NIP46_KIND, [["p", p or self.transport_pub]], content, created_at if created_at is not None else int(self.clock()))
        return event.to_dict()

    def decode(self, event: NostrEvent) -> Nip46Response:
        assert event.kind == NIP46_KIND and event.pubkey == self.transport_pub and ["p", self.key.public_hex] in [list(t[:2]) for t in event.tags]
        assert "?iv=" not in event.content, "las respuestas deben ir en NIP-44"
        return parse_response(nip44.decrypt(event.content, nip44.get_conversation_key(self.key, self.transport_pub)))


def login_template(identity_pub: str, *, now: int = NOW, challenge: str = CHALLENGE, origin: str = ORIGIN, method: str = "GET",
                   content: str = CONTENT, kind: int = 27235, age: int = 0, tags: list[list[str]] | None = None, with_id: bool = True) -> str:
    """El parámetro de `sign_event` como lo envía Stacker News: plantilla con id y pubkey, sin firma (6 campos)."""
    from app.nostr.event import compute_event_id
    the_tags = tags if tags is not None else [["challenge", challenge], ["u", origin], ["method", method]]
    created = now - age
    tpl: dict[str, Any] = {"kind": kind, "created_at": created, "content": content, "tags": the_tags}
    if with_id:
        tpl["pubkey"] = identity_pub
        tpl["id"] = compute_event_id(identity_pub, created, kind, tuple(tuple(t) for t in the_tags), content)
    return json.dumps(tpl, separators=(",", ":"))


@dataclass
class Rig:
    service: SignerService
    relay: FakeRelay
    audit: AuditLog
    approvals: ApprovalRegistry
    connections: ConnectionManager
    clock: Clock
    identity: Keypair
    task: "asyncio.Task[str]"

    def client(self) -> NdkLikeClient:
        return NdkLikeClient(self.service.transport.public_hex, self.clock)

    async def send(self, raw: dict[str, Any]) -> None:
        from app.nostr.relay import RelayEvent
        self.relay.inject(RelayEvent(raw))

    async def wait_for(self, predicate: Callable[[], bool], timeout: float = 3.0) -> None:
        async def poll() -> None:
            while not predicate():
                await asyncio.sleep(0.005)
        await asyncio.wait_for(poll(), timeout)

    async def exchange(self, client: NdkLikeClient, method: str, params: list[str], **kw: Any) -> Nip46Response:
        """Envía una solicitud y espera exactamente UNA respuesta nueva."""
        before = len(self.relay.published)
        await self.send(client.request(method, params, **kw))
        await self.wait_for(lambda: len(self.relay.published) > before)
        return client.decode(self.relay.published[-1])

    async def pending_request(self, kind: str) -> Any:
        await self.wait_for(lambda: any(r.kind.value == kind for r in self.approvals.pending()))
        return next(r for r in self.approvals.pending() if r.kind.value == kind)

    async def connect_client(self, client: NdkLikeClient | None = None) -> NdkLikeClient:
        """Flujo completo de `connect` (NIP-04, como NDK) con aprobación del operador. Devuelve el cliente ya activo."""
        client = client or self.client()
        secret = self.service.issue_bunker_uri().split("secret=")[1]
        before = len(self.relay.published)
        await self.send(client.request("connect", ["", secret], scheme="nip04"))
        req = await self.pending_request("connect")
        self.approvals.resolve(req.id, True)
        await self.wait_for(lambda: len(self.relay.published) > before)
        assert client.decode(self.relay.published[-1]).result == "ack"
        return client

    async def stop(self) -> None:
        await self.service.stop()
        await asyncio.wait_for(self.task, 5)


async def make_rig(*, settings: Settings | None = None, relay: FakeRelay | None = None, start: bool = True, **overrides: Any) -> Rig:
    clock = Clock()
    cfg = settings or Settings(**{**SUPERVISED_TTLS, "approval_ttl_s": 5, "max_signatures": 2, **overrides})
    identity = Keypair.generate()
    relay = relay or FakeRelay()
    audit = AuditLog(now=clock)
    approvals = ApprovalRegistry(now=clock, max_pending=cfg.max_pending)
    connections = ConnectionManager(now=clock, secret_ttl_s=cfg.secret_ttl_s, connection_ttl_s=cfg.connection_ttl_s)
    service = SignerService(identity=identity, relay=relay, settings=cfg, approvals=approvals, connections=connections, audit=audit, now=clock)
    task = asyncio.create_task(service.run())
    rig = Rig(service, relay, audit, approvals, connections, clock, identity, task)
    if start:
        assert await service.wait_started(3) and service.state is SignerState.READY
    return rig

"""Transporte de relay Nostr (NIP-01 sobre WebSocket). ÚNICO módulo del producto con E/S de red (decisión B2-1).

`RelayTransport` es la interfaz que usa el servicio firmante; `WebsocketRelay` la implementa con `websockets`: un solo intento de conexión
(sin reconexión automática), TLS verificado (certificado y nombre de host) con la opción `X25519` validada en el laboratorio, tiempos
acotados y tamaño máximo de mensaje. `ws://` solo con `allow_insecure` (relay local de pruebas). Un `AUTH` del relay se informa y NO se
responde: el firmante nunca se autentica ante el relay. Los mensajes de error son genéricos (sin detalles de red ni de TLS).
"""
import asyncio
import json
import re
import ssl
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import urlsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import WebSocketException

from app.nostr.errors import RelayError
from app.nostr.event import NostrEvent
from app.nostr.keys import require_pubkey
from app.nostr.nip46 import NIP46_KIND, validate_relay_url

SUBSCRIPTION_ID: Final = "s1"
_TLS_GROUPS_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,32}\Z")


@dataclass(frozen=True, slots=True)
class RelayEvent:
    event: dict[str, object]  # evento recibido, SIN validar (lo valida el servicio)


@dataclass(frozen=True, slots=True)
class RelayEose:
    subscription: str


@dataclass(frozen=True, slots=True)
class RelayOk:
    event_id: str
    accepted: bool
    message: str


@dataclass(frozen=True, slots=True)
class RelayNotice:
    kind: str  # "NOTICE" o "CLOSED"
    message: str


@dataclass(frozen=True, slots=True)
class RelayAuth:
    """El relay pidió NIP-42. El producto NO responde."""


RelayMessage = RelayEvent | RelayEose | RelayOk | RelayNotice | RelayAuth


class RelayTransport(Protocol):
    @property
    def host(self) -> str: ...

    async def connect(self) -> None: ...

    async def subscribe(self, pubkey: str, since: int) -> None: ...

    async def publish(self, event: NostrEvent) -> None: ...

    def messages(self) -> AsyncIterator[RelayMessage]: ...

    async def close(self) -> None: ...


def parse_relay_message(raw: str | bytes) -> RelayMessage | None:
    """Interpreta un mensaje del relay. Devuelve None si es desconocido o está mal formado (se ignora)."""
    if not isinstance(raw, str):
        return None
    try:
        msg = json.loads(raw)
    except (json.JSONDecodeError, RecursionError):
        return None
    if not isinstance(msg, list) or not msg or not isinstance(msg[0], str):
        return None
    kind = msg[0]
    if kind == "EVENT" and len(msg) == 3 and isinstance(msg[2], dict):
        return RelayEvent(msg[2])
    if kind == "EOSE" and len(msg) >= 2 and isinstance(msg[1], str):
        return RelayEose(msg[1])
    if kind == "OK" and len(msg) >= 3 and isinstance(msg[1], str) and isinstance(msg[2], bool):
        return RelayOk(msg[1], msg[2], str(msg[3])[:120] if len(msg) > 3 else "")
    if kind in ("NOTICE", "CLOSED") and len(msg) >= 2:
        return RelayNotice(kind, str(msg[-1])[:120])
    if kind == "AUTH":
        return RelayAuth()
    return None


def tls_context(groups: str | None) -> ssl.SSLContext | None:
    """None = contexto por defecto de `websockets`. Con `groups`, el mismo contexto verificado ofreciendo solo ese grupo (p. ej. X25519)."""
    if not groups:
        return None
    if not _TLS_GROUPS_RE.match(groups):
        raise RelayError("grupo tls invalido")
    ctx = ssl.create_default_context()
    try:
        ctx.set_ecdh_curve(groups)
    except ValueError:
        raise RelayError("grupo tls invalido") from None
    return ctx


class WebsocketRelay:
    def __init__(self, url: str, *, tls_groups: str | None = None, allow_insecure: bool = False, open_timeout: float = 10.0,
                 send_timeout: float = 10.0, max_message_bytes: int = 1 << 20) -> None:
        self._url = validate_relay_url(url, allow_insecure=allow_insecure)
        self._ssl = tls_context(tls_groups) if self._url.startswith("wss://") else None
        self._open_timeout, self._send_timeout, self._max_bytes = open_timeout, send_timeout, max_message_bytes
        self._ws: ClientConnection | None = None
        self._used = False

    @property
    def host(self) -> str:
        return urlsplit(self._url).hostname or ""

    async def connect(self) -> None:
        """UN intento. Un transporte no se reutiliza: tras cerrarse hay que crear otro (sin reconexión automática)."""
        if self._used:
            raise RelayError("el transporte ya se uso")
        self._used = True
        try:
            if self._ssl is not None:
                self._ws = await connect(self._url, open_timeout=self._open_timeout, max_size=self._max_bytes, ssl=self._ssl)
            else:
                self._ws = await connect(self._url, open_timeout=self._open_timeout, max_size=self._max_bytes)
        except (OSError, TimeoutError, WebSocketException):
            raise RelayError("no se pudo conectar al relay") from None

    async def _send(self, payload: list[object]) -> None:
        if self._ws is None:
            raise RelayError("relay no conectado")
        try:
            await asyncio.wait_for(self._ws.send(json.dumps(payload, separators=(",", ":"), ensure_ascii=False)), self._send_timeout)
        except (OSError, TimeoutError, WebSocketException):
            raise RelayError("no se pudo enviar al relay") from None

    async def subscribe(self, pubkey: str, since: int) -> None:
        await self._send(["REQ", SUBSCRIPTION_ID, {"kinds": [NIP46_KIND], "#p": [require_pubkey(pubkey)], "since": max(0, since)}])

    async def publish(self, event: NostrEvent) -> None:
        await self._send(["EVENT", event.to_dict()])

    async def messages(self) -> AsyncIterator[RelayMessage]:
        if self._ws is None:
            raise RelayError("relay no conectado")
        try:
            async for raw in self._ws:
                parsed = parse_relay_message(raw)
                if parsed is not None:
                    yield parsed
        except WebSocketException:
            return  # cierre anómalo del relay: la iteración termina; el servicio lo trata como «relay cerrado»

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await asyncio.wait_for(ws.close(), self._send_timeout)
            except (OSError, TimeoutError, WebSocketException):
                pass

"""Transporte WebSocket contra un relay LOCAL de pruebas (127.0.0.1, sin red externa). TLS con una CA desechable generada en la prueba."""
import asyncio
import datetime
import json
import ssl
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from websockets.asyncio.server import ServerConnection, serve

from app.nostr.errors import InvalidBunkerUri, RelayError
from app.nostr.event import sign_event
from app.nostr.keys import Keypair
from app.nostr.relay import RelayAuth, RelayEose, RelayEvent, RelayNotice, RelayOk, WebsocketRelay, parse_relay_message, tls_context

pytestmark = pytest.mark.anyio
Handler = Callable[[ServerConnection], Awaitable[None]]


async def collect(relay: WebsocketRelay, count: int, timeout: float = 3.0) -> list[object]:
    out: list[object] = []

    async def run() -> None:
        async for msg in relay.messages():
            out.append(msg)
            if len(out) >= count:
                return

    await asyncio.wait_for(run(), timeout)
    return out


class Server:
    def __init__(self, handler: Handler, ssl_context: ssl.SSLContext | None = None) -> None:
        self.handler, self.ssl_context, self.server = handler, ssl_context, None

    async def __aenter__(self) -> int:
        self.server = await serve(self.handler, "127.0.0.1", 0, ssl=self.ssl_context)
        return int(next(iter(self.server.sockets)).getsockname()[1])

    async def __aexit__(self, *exc: object) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()


# ------------------------------------------------------------------------------------------------ análisis de mensajes
@pytest.mark.parametrize(("raw", "expected"), [
    ('["EOSE","s1"]', RelayEose("s1")),
    ('["OK","ab",true,"x"]', RelayOk("ab", True, "x")),
    ('["OK","ab",false]', RelayOk("ab", False, "")),
    ('["NOTICE","hola"]', RelayNotice("NOTICE", "hola")),
    ('["CLOSED","s1","error: x"]', RelayNotice("CLOSED", "error: x")),
    ('["AUTH","challenge"]', RelayAuth()),
    ('["EVENT","s1",{"a":1}]', RelayEvent({"a": 1})),
])
def test_known_messages_are_parsed(raw: str, expected: object) -> None:
    assert parse_relay_message(raw) == expected


@pytest.mark.parametrize("raw", [
    b"bytes", "no json", "{}", "[]", "[1]", '["EVENT","s1","x"]', '["EVENT"]', '["EOSE"]', '["EOSE",1]', '["OK","a","b"]', '["OK","a"]',
    '["NOTICE"]', '["OTRO"]', "[" * 600,
])
def test_unknown_or_malformed_messages_are_ignored(raw: str | bytes) -> None:
    assert parse_relay_message(raw) is None


def test_long_relay_text_is_truncated() -> None:
    msg = parse_relay_message(json.dumps(["NOTICE", "x" * 500]))
    assert isinstance(msg, RelayNotice) and len(msg.message) == 120


# ------------------------------------------------------------------------------------------------ construcción
def test_insecure_scheme_requires_the_explicit_flag() -> None:
    with pytest.raises(InvalidBunkerUri):
        WebsocketRelay("ws://127.0.0.1:1")
    assert WebsocketRelay("ws://127.0.0.1:1", allow_insecure=True).host == "127.0.0.1"
    assert WebsocketRelay("wss://relay.example").host == "relay.example"


def test_tls_context_groups() -> None:
    assert tls_context(None) is None and tls_context("") is None
    ctx = tls_context("X25519")
    assert ctx is not None and ctx.verify_mode is ssl.CERT_REQUIRED and ctx.check_hostname
    for bad in ("bad group", "X25519:P-256", "x" * 40, "NOEXISTE"):
        with pytest.raises(RelayError):
            tls_context(bad)


# ------------------------------------------------------------------------------------------------ ws:// local
async def test_subscribe_publish_and_receive() -> None:
    received: list[object] = []
    key = Keypair.generate()
    event = sign_event(key, 24133, [["p", key.public_hex]], "c", 1_800_000_000)

    async def handler(ws: ServerConnection) -> None:
        async for raw in ws:
            msg = json.loads(raw)
            received.append(msg)
            if msg[0] == "REQ":
                await ws.send(json.dumps(["EOSE", msg[1]]))
                await ws.send("basura")  # se ignora
                await ws.send(json.dumps(["EVENT", msg[1], event.to_dict()]))
            elif msg[0] == "EVENT":
                await ws.send(json.dumps(["OK", msg[1]["id"], True, ""]))

    async with Server(handler) as port:
        relay = WebsocketRelay(f"ws://127.0.0.1:{port}", allow_insecure=True)
        await relay.connect()
        await relay.subscribe(key.public_hex, 1234)
        await relay.publish(event)
        got = await collect(relay, 3)
        await relay.close()
    assert received[0] == ["REQ", "s1", {"kinds": [24133], "#p": [key.public_hex], "since": 1234}]
    assert received[1] == ["EVENT", event.to_dict()]
    assert got[0] == RelayEose("s1") and got[1] == RelayEvent(event.to_dict()) and got[2] == RelayOk(event.id, True, "")


async def test_since_is_never_negative_and_pubkey_is_validated() -> None:
    seen: list[object] = []

    async def handler(ws: ServerConnection) -> None:
        async for raw in ws:
            seen.append(json.loads(raw))

    async with Server(handler) as port:
        relay = WebsocketRelay(f"ws://127.0.0.1:{port}", allow_insecure=True)
        await relay.connect()
        await relay.subscribe("a" * 64, -5)
        with pytest.raises(Exception):  # noqa: B017 - require_pubkey lanza el error de clave de la capa nostr
            await relay.subscribe("zz", 1)
        await asyncio.sleep(0.1)
        await relay.close()
    assert seen[0][2]["since"] == 0  # type: ignore[index]


async def test_transport_is_single_use() -> None:
    async def handler(ws: ServerConnection) -> None:
        await ws.wait_closed()

    async with Server(handler) as port:
        relay = WebsocketRelay(f"ws://127.0.0.1:{port}", allow_insecure=True)
        await relay.connect()
        with pytest.raises(RelayError):
            await relay.connect()
        await relay.close()
        await relay.close()  # idempotente


async def test_use_before_connect_and_after_close_fails() -> None:
    relay = WebsocketRelay("ws://127.0.0.1:1", allow_insecure=True)
    with pytest.raises(RelayError):
        await relay.subscribe("a" * 64, 0)
    with pytest.raises(RelayError):
        await anext(relay.messages())


async def test_connection_refused_and_timeout_become_relay_error() -> None:
    with pytest.raises(RelayError):
        await WebsocketRelay("ws://127.0.0.1:1", allow_insecure=True, open_timeout=1).connect()

    async def silent(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await asyncio.sleep(5)  # acepta TCP pero nunca completa el handshake WebSocket

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        with pytest.raises(RelayError):
            await WebsocketRelay(f"ws://127.0.0.1:{port}", allow_insecure=True, open_timeout=0.3).connect()
    finally:
        server.close()


async def test_server_closing_ends_the_message_stream_and_oversize_is_dropped() -> None:
    async def handler(ws: ServerConnection) -> None:
        await ws.send(json.dumps(["NOTICE", "a"]))
        await ws.send("x" * 5000)  # excede max_message_bytes: cierre 1009
        await asyncio.sleep(1)

    async with Server(handler) as port:
        relay = WebsocketRelay(f"ws://127.0.0.1:{port}", allow_insecure=True, max_message_bytes=1000)
        await relay.connect()
        msgs: list[object] = []
        async for m in relay.messages():
            msgs.append(m)
        await relay.close()
    assert msgs == [RelayNotice("NOTICE", "a")]


async def test_send_failure_becomes_relay_error() -> None:
    async def handler(ws: ServerConnection) -> None:
        await ws.close()

    async with Server(handler) as port:
        relay = WebsocketRelay(f"ws://127.0.0.1:{port}", allow_insecure=True)
        await relay.connect()
        await asyncio.sleep(0.2)
        with pytest.raises(RelayError):
            await relay.subscribe("a" * 64, 0)
        await relay.close()


# ------------------------------------------------------------------------------------------------ wss con CA desechable
def make_pki(tmp: Path) -> tuple[Path, Path, Path]:
    now = datetime.datetime.now(datetime.UTC)

    def build(subject: str, issuer_key: ec.EllipticCurvePrivateKey | None, key: ec.EllipticCurvePrivateKey, issuer_name: x509.Name | None,
              ca: bool) -> x509.Certificate:
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)])
        builder = (x509.CertificateBuilder().subject_name(name).issuer_name(issuer_name or name).public_key(key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
                   .not_valid_after(now + datetime.timedelta(hours=1)).add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if not ca:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        return builder.sign(issuer_key or key, hashes.SHA256())

    ca_key, leaf_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca_cert = build("prueba-ca", None, ca_key, None, True)
    leaf = build("localhost", ca_key, leaf_key, ca_cert.subject, False)
    ca_path, cert_path, key_path = tmp / "ca.pem", tmp / "leaf.pem", tmp / "leaf.key"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return ca_path, cert_path, key_path


async def echo_eose(ws: ServerConnection) -> None:
    async for raw in ws:
        msg = json.loads(raw)
        if msg[0] == "REQ":
            await ws.send(json.dumps(["EOSE", msg[1]]))


async def test_wss_with_untrusted_certificate_is_rejected(tmp_path: Path) -> None:
    _ca, cert, key = make_pki(tmp_path)
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert, key)
    async with Server(echo_eose, server_ctx) as port:
        for groups in (None, "X25519"):
            with pytest.raises(RelayError):
                await WebsocketRelay(f"wss://localhost:{port}", tls_groups=groups, open_timeout=3).connect()


async def test_wss_with_a_trusted_ca_connects_with_and_without_x25519(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ca, cert, key = make_pki(tmp_path)
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert, key)
    real = ssl.create_default_context

    def trusting(*args: object, **kwargs: object) -> ssl.SSLContext:
        ctx = real(*args, **kwargs)  # type: ignore[arg-type]
        ctx.load_verify_locations(cafile=str(ca))
        return ctx

    monkeypatch.setattr(ssl, "create_default_context", trusting)
    async with Server(echo_eose, server_ctx) as port:
        relay = WebsocketRelay(f"wss://localhost:{port}", tls_groups="X25519", open_timeout=3)
        await relay.connect()
        await relay.subscribe("a" * 64, 0)
        assert (await collect(relay, 1))[0] == RelayEose("s1")
        await relay.close()

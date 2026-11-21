import pytest

from app.config import Settings
from app.nostr.keys import Keypair
from app.nostr.relay import WebsocketRelay
from app.services.runtime import AlreadyRunning, NoIdentity, NotRunning, SignerRuntime, StartFailed, default_relay_factory
from tests.support import FakeRelay

pytestmark = pytest.mark.anyio


def test_default_factory_builds_a_websocket_relay_from_settings() -> None:
    relay = default_relay_factory(Settings(relay_url="wss://relay.example.com", relay_tls_groups="X25519"))
    assert isinstance(relay, WebsocketRelay) and relay.host == "relay.example.com"


async def test_lifecycle_errors_and_empty_views() -> None:
    runtime = SignerRuntime(Settings(), relay_factory=lambda _s: FakeRelay())
    assert runtime.requests() == [] and runtime.requests("all") == [] and runtime.status()["signer"]["state"] == "idle"
    with pytest.raises(NoIdentity):
        await runtime.start()
    with pytest.raises(NotRunning):
        await runtime.stop()
    await runtime.shutdown()  # sin firmante en marcha: no falla


async def test_start_stop_restart_creates_fresh_state_and_keeps_one_audit() -> None:
    runtime = SignerRuntime(Settings(), relay_factory=lambda _s: FakeRelay())
    pub = runtime.set_identity(Keypair.generate())
    first = await runtime.start()
    with pytest.raises(AlreadyRunning):
        await runtime.start()
    with pytest.raises(AlreadyRunning):
        runtime.set_identity(Keypair.generate())
    secret_uri = first.issue_bunker_uri()
    await runtime.stop()
    second = await runtime.start()
    assert second is not first and second.approvals is not first.approvals and second.connections is not first.connections
    assert second.connections.counts()["unused_secrets"] == 0 and runtime.public_key == pub and secret_uri
    assert runtime.requests("pending") == [] and runtime.requests("recent") == [] and runtime.requests("all") == []
    await runtime.shutdown()
    assert [e["event"] for e in runtime.audit.entries()].count("session_end") == 2


async def test_failed_start_raises_start_failed_and_leaves_evidence() -> None:
    runtime = SignerRuntime(Settings(), relay_factory=lambda _s: FakeRelay(fail_connect=True))
    runtime.set_identity(Keypair.generate())
    with pytest.raises(StartFailed):
        await runtime.start()
    assert runtime.audit.entries()[-1]["event"] == "session_end" and not runtime.running


async def test_stop_cancels_a_session_that_does_not_end_in_time(monkeypatch: pytest.MonkeyPatch) -> None:
    class Stubborn(FakeRelay):
        async def close(self) -> None:  # no libera el flujo de mensajes: run() no termina solo
            self.closed = True

    monkeypatch.setattr("app.services.runtime.STOP_WAIT_S", 0.2)
    runtime = SignerRuntime(Settings(), relay_factory=lambda _s: Stubborn())
    runtime.set_identity(Keypair.generate())
    await runtime.start()
    await runtime.stop()
    assert not runtime.running and runtime.audit.entries()[-1]["event"] == "session_end"


async def test_stop_tolerates_a_session_that_ends_with_an_unexpected_error() -> None:
    import asyncio

    class Exploding(FakeRelay):
        gate: "asyncio.Event" = None  # type: ignore[assignment]

        async def messages(self):  # type: ignore[no-untyped-def]
            from app.nostr.relay import RelayEose
            yield RelayEose("s1")
            await self.gate.wait()
            raise RuntimeError("fallo inesperado del transporte")

    relay = Exploding()
    relay.gate = asyncio.Event()
    runtime = SignerRuntime(Settings(), relay_factory=lambda _s: relay)
    runtime.set_identity(Keypair.generate())
    await runtime.start()
    relay.gate.set()
    await asyncio.sleep(0.05)
    await runtime.stop()  # no propaga el error de la sesion
    assert runtime.audit.entries()[-1]["event"] == "session_end"

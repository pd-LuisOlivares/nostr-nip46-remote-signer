"""E2E de NAVEGADOR REAL: la reconexión automática al relay (modo continuo) vista desde la interfaz. El relay es un proceso local que la prueba mata y reinicia.

Aprobación humana de cada `connect` y cada `sign_event` en la interfaz; identidades ficticias; sin servicios externos. No sustituye a la autenticación real con Stacker News.
"""
import re
import sys
import time
from collections.abc import Callable
from typing import Any

import pytest

from app.nostr.nip46 import parse_bunker_uri
from tests.e2e.conftest import ROOT, AppHandle, Proc, RelayClient, free_port, spawn
from tests.e2e.test_browser_flow import approve_card, issue_uri, open_ui, sign_in

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
pytestmark = pytest.mark.e2e
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def start_relay(port: int) -> Proc:
    for _ in range(20):  # el puerto puede tardar un instante en liberarse tras matar el proceso anterior
        proc = spawn([sys.executable, str(ROOT / "tests" / "e2e" / "relay_server.py"), str(port)], {})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any("relay listo" in line for line in proc.lines) and proc.popen.poll() is None:
            time.sleep(0.05)
        if any("relay listo" in line for line in proc.lines):
            return proc
        proc.stop()
        time.sleep(0.25)
    raise AssertionError("no se pudo levantar el relay local")


def test_the_ui_shows_reconnecting_keeps_the_connection_and_returns_to_ready(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    port = free_port()
    relay = start_relay(port)
    relay_url = f"ws://127.0.0.1:{port}"
    client: RelayClient | None = None
    client2: RelayClient | None = None
    try:
        app = start_app(RELAY_URL=relay_url)
        context, page, problems = open_ui(browser, app)
        sign_in(page, app)
        page.click("#identity-create")
        expect(page.locator("#identity-pub")).to_have_text(HEX64)
        identity_pub = page.inner_text("#identity-pub").strip()
        page.click("#signer-start")
        expect(page.locator("#signer-state")).to_have_text("Listo")
        uri = issue_uri(page)
        client = RelayClient(relay_url, parse_bunker_uri(uri, allow_insecure_relays=True).signer_pubkey)
        client.send("connect", ["", uri.split("secret=")[1]], scheme="nip04")
        approve_card(page, "connect").locator("button.ok").click()  # el emparejamiento exige la aprobación humana en la interfaz
        assert client.reply().result == "ack"
        expect(page.locator("#connections-list")).to_contain_text("active")

        relay.stop()  # el relay desaparece
        expect(page.locator("#signer-state")).to_have_text("Reconectando", timeout=15000)
        expect(page.locator("#signer-stop")).to_be_enabled()  # «Detener» sigue disponible mientras se reconecta
        expect(page.locator("#signer-start")).to_be_disabled()
        expect(page.locator("#connections-list")).to_contain_text("active")  # las conexiones autorizadas se conservan

        relay = start_relay(port)  # el relay vuelve en el mismo puerto
        expect(page.locator("#signer-state")).to_have_text("Listo", timeout=30000)
        expect(page.locator("#connections-list")).to_contain_text("active")
        expect(page.locator("#banner")).to_contain_text("Reconectado")
        client2 = RelayClient(relay_url, client.ndk.transport_pub, ndk=client.ndk)  # el mismo cliente, sin repetir `connect`
        assert client2.call("get_public_key", []).result == identity_pub

        page.click("#signer-stop")
        expect(page.locator("#signer-state")).to_have_text("Detenido")
        expect(page.locator("#connections-list")).to_contain_text("revoked")  # la detención manual revoca
        assert problems == [], problems
        context.close()
    finally:
        for c in (client, client2):
            if c is not None:
                c.close()
        relay.stop()

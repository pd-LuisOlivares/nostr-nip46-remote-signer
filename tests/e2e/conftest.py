"""Infraestructura E2E: relay local y aplicación real (Uvicorn) como procesos, un navegador real (Chrome/Edge instalado) y un cliente NIP-46 de prueba."""
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from websockets.sync.client import ClientConnection, connect

from app.nostr.event import NostrEvent, parse_event
from app.nostr.nip46 import Nip46Response
from tests.support import NdkLikeClient

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://sn.e2e.invalid"
CODE_RE = re.compile(r"ESTA ejecucion[^:]*: ([A-Za-z0-9_-]{20,})")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_http(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(url)


@dataclass
class Proc:
    popen: subprocess.Popen[str]
    lines: list[str] = field(default_factory=list)

    def stop(self) -> None:
        if self.popen.poll() is None:
            self.popen.terminate()
            try:
                self.popen.wait(8)
            except subprocess.TimeoutExpired:
                self.popen.kill()


def spawn(args: list[str], env: dict[str, str]) -> Proc:
    popen = subprocess.Popen(args, cwd=ROOT, env={**os.environ, "PYTHONUNBUFFERED": "1", **env}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
    proc = Proc(popen)

    def drain() -> None:
        assert popen.stdout is not None
        for line in popen.stdout:
            proc.lines.append(line.rstrip("\n"))

    threading.Thread(target=drain, daemon=True).start()
    return proc


@dataclass
class AppHandle:
    base: str
    code: str
    relay_url: str
    proc: Proc

    def log(self) -> str:
        return "\n".join(self.proc.lines)


@pytest.fixture(scope="session")
def relay() -> Iterator[str]:
    port = free_port()
    proc = spawn([sys.executable, str(ROOT / "tests" / "e2e" / "relay_server.py"), str(port)], {})
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not any("relay listo" in line for line in proc.lines):
        time.sleep(0.05)
    assert any("relay listo" in line for line in proc.lines), proc.lines
    yield f"ws://127.0.0.1:{port}"
    proc.stop()


@pytest.fixture
def start_app(relay: str) -> Iterator[Callable[..., AppHandle]]:
    started: list[Proc] = []

    def factory(**env: str) -> AppHandle:
        port = free_port()
        proc = spawn([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                     {"RELAY_URL": relay, "RELAY_ALLOW_INSECURE": "1", "SERVICE_ORIGIN": ORIGIN, "APPROVAL_TTL_S": "30", "MAX_SIGNATURES": "2", **env})
        started.append(proc)
        base = f"http://127.0.0.1:{port}"
        wait_http(base + "/health")
        deadline = time.monotonic() + 10
        code = None
        while code is None and time.monotonic() < deadline:
            match = next((CODE_RE.search(line) for line in proc.lines if CODE_RE.search(line)), None)
            code = match.group(1) if match else None
            time.sleep(0.05)
        assert code, "la aplicacion no mostro el codigo de acceso"
        return AppHandle(base, code, relay, proc)

    yield factory
    for proc in started:
        proc.stop()


@pytest.fixture(scope="module")  # por modulo: el bucle de Playwright (sync) debe cerrarse antes de las pruebas asincronas de otros modulos
def browser() -> Iterator[Any]:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        instance = None
        for channel in ("chrome", "msedge", None):
            try:
                instance = pw.chromium.launch(channel=channel, headless=True) if channel else pw.chromium.launch(headless=True)
                break
            except Exception:  # noqa: BLE001 - se prueba el siguiente navegador disponible
                continue
        if instance is None:
            pytest.skip("no hay un navegador Chromium/Chrome/Edge disponible para Playwright")
        yield instance
        instance.close()


class RelayClient:
    """Cliente NIP-46 de prueba (hace de «Stacker News»): habla con el relay local y descifra lo que el firmante le responde."""

    def __init__(self, relay_url: str, transport_pub: str) -> None:
        self.ndk = NdkLikeClient(transport_pub, time.time)
        self.ws: ClientConnection = connect(relay_url, open_timeout=5, legacy=True)
        self.inbox: queue.Queue[NostrEvent] = queue.Queue()
        self.ws.send(json.dumps(["REQ", "c1", {"kinds": [24133], "#p": [self.ndk.key.public_hex], "since": int(time.time()) - 5}]))
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        try:
            for raw in self.ws:
                msg = json.loads(raw)
                if msg[0] == "EVENT" and msg[1] == "c1":
                    self.inbox.put(parse_event(msg[2]))
        except Exception:  # noqa: BLE001 - la conexion se cierra al terminar la prueba
            return

    def send(self, method: str, params: list[str], **kw: Any) -> None:
        self.ws.send(json.dumps(["EVENT", self.ndk.request(method, params, **kw)]))

    def reply(self, timeout: float = 10.0) -> Nip46Response:
        return self.ndk.decode(self.inbox.get(timeout=timeout))

    def call(self, method: str, params: list[str], **kw: Any) -> Nip46Response:
        self.send(method, params, **kw)
        return self.reply()

    def silent(self, wait: float = 1.0) -> bool:
        try:
            self.inbox.get(timeout=wait)
        except queue.Empty:
            return True
        return False

    def close(self) -> None:
        self.ws.close()

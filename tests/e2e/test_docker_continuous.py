"""Validación LOCAL de la imagen DEFINITIVA (modo continuo) en Docker: proyecto efímero propio, relay local en el mismo compose y NINGÚN servicio externo.

Se activa con E2E_DOCKER=1. NO construye ni descarga nada: usa la imagen local `nostr-nip46-remote-signer:d17-continuous` (o la de `D17_TEST_IMAGE`) con `--no-build --pull never`.
Proyecto, red y volumen PROPIOS (`nip46-d17v-*`): no toca el entorno B6.2, sus imágenes, su volumen ni sus respaldos. Identidad y contraseña FICTICIAS y aleatorias.

Opera la INTERFAZ en un navegador real: importa una identidad de prueba, inicia el firmante, emite la URI desde la interfaz (sin registrarla en logs), exige la aprobación humana
de cada `connect` y de cada `sign_event`, comprueba los límites, la revocación individual y la reconexión. NO es una autenticación con Stacker News.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.nostr.event import parse_and_verify_event
from app.nostr.keys import Keypair
from app.nostr.nip46 import parse_bunker_uri
from tests.e2e.conftest import ROOT, RelayClient, free_port, wait_http
from tests.e2e.test_browser_flow import approve_card, issue_uri, open_ui, pair_from_ui, sign_in
from tests.support import CHALLENGE, login_template

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("E2E_DOCKER") != "1", reason="defina E2E_DOCKER=1 para ejecutar las pruebas de Docker")]
IMAGE = os.environ.get("D17_TEST_IMAGE", "nostr-nip46-remote-signer:d17-continuous")
ORIGIN = "https://sn.d17.invalid"
LAB_RELAY_IMAGE = "nip46-lab-py:1.0a"

OVERRIDE = """services:
  relay:
    image: {relay_image}
    command: ["python", "-m", "lab_relay"]
    environment: {{LAB_ACTOR: relay, RELAY_PORT: "7777"}}
    ports: ["127.0.0.1:{relay_port}:7777"]
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: ["/tmp:size=16m"]
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 7777), 2).close()"]
      interval: 2s
      timeout: 3s
      retries: 20
  app:
    environment:
      RELAY_URL: ws://relay:7777
      RELAY_ALLOW_INSECURE: "1"
      SERVICE_ORIGIN: {origin}
    depends_on:
      relay:
        condition: service_healthy
"""

_EFFECTIVE = (
    "import json, os\n"
    "from app.config import Settings\n"
    "c = Settings.from_env(os.environ)\n"
    "st = dict(l.split(':', 1) for l in open('/proc/self/status').read().splitlines() if ':' in l)\n"
    "print(json.dumps({'mode': c.signer_mode, 'requests_per_min': c.requests_per_min, 'connection_ttl_s': c.connection_ttl_s, 'secret_ttl_s': c.secret_ttl_s,\n"
    "  'approval_ttl_s': c.approval_ttl_s, 'window_s': c.window_s, 'uid': os.getuid(), 'cap_eff': st['CapEff'].strip(), 'no_new_privs': st['NoNewPrivs'].strip(),\n"
    "  'mode_env_is_set': 'SIGNER_MODE' in os.environ and os.environ['SIGNER_MODE'] != ''}))"
)
_SOCKETS = (
    "import ipaddress, json\n"
    "remotes = set()\n"
    "for name in ('/proc/net/tcp', '/proc/net/tcp6'):\n"
    "    for line in open(name).read().splitlines()[1:]:\n"
    "        f = line.split()\n"
    "        if f[3] != '01' or int(f[1].split(':')[1], 16) == 8000:\n"
    "            continue\n"
    "        raw = f[2].split(':')[0]\n"
    "        if len(raw) == 8:\n"
    "            remotes.add(str(ipaddress.IPv4Address(bytes.fromhex(raw)[::-1])))\n"
    "        elif raw.upper().startswith('0000000000000000FFFF0000'):\n"
    "            remotes.add(str(ipaddress.IPv4Address(bytes.fromhex(raw[24:])[::-1])))\n"
    "        else:\n"
    "            remotes.add('v6:' + raw)\n"
    "print(json.dumps(sorted(remotes)))"
)


@dataclass
class Handle:
    """Lo mínimo que usan los ayudantes de los E2E de navegador (`base`, `relay_url`, `username`, `password`)."""

    base: str
    relay_url: str
    username: str
    password: str
    project: str
    tmp: Path
    app_port: int

    def log(self) -> str:
        return compose(self, "logs", "--no-color", "--no-log-prefix").stdout


def compose(h: Handle, *args: str, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ADMIN_") and k not in ("SIGNER_MODE", "REQUESTS_PER_MIN", "RELAY_URL", "APP_IMAGE")}
    env.update(APP_IMAGE=IMAGE, APP_PORT=str(h.app_port), ADMIN_USERNAME=h.username, ADMIN_PASSWORD=h.password)
    return subprocess.run(["docker", "compose", "--env-file", str(h.tmp / "vacio.env"), "-p", h.project, "-f", str(ROOT / "compose.yaml"), "-f", str(h.tmp / "override.yaml"), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=timeout, check=False)


@pytest.fixture
def stack(tmp_path: Path) -> Iterator[Handle]:
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    for image in (IMAGE, LAB_RELAY_IMAGE):
        if subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=60, check=False).returncode != 0:
            pytest.skip(f"la imagen local {image} no existe (esta prueba no construye ni descarga nada)")
    (tmp_path / "vacio.env").write_text("", encoding="utf-8")
    relay_port, app_port = free_port(), free_port()
    (tmp_path / "override.yaml").write_text(OVERRIDE.format(relay_image=LAB_RELAY_IMAGE, relay_port=relay_port, origin=ORIGIN), encoding="utf-8")
    h = Handle(f"http://127.0.0.1:{app_port}", f"ws://127.0.0.1:{relay_port}", "operador-d17", secrets.token_urlsafe(24), f"nip46-d17v-{secrets.token_hex(3)}", tmp_path, app_port)
    try:
        up = compose(h, "up", "-d", "--no-build", "--pull", "never")
        assert up.returncode == 0, up.stderr[-500:]
        wait_http(h.base + "/health", timeout=90)
        yield h
    finally:
        compose(h, "down", "--remove-orphans", timeout=120)  # sin `-v`: el volumen efímero se elimina a continuación, por su nombre exacto y solo si es de ESTE proyecto
        volume = f"{h.project}_app_data"
        if volume.startswith("nip46-d17v-"):
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True, timeout=60, check=False)


def wait_until(predicate: Any, timeout: float = 30.0, step: float = 0.25) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(step)
    raise TimeoutError


def test_the_definitive_image_works_locally_in_continuous_mode_from_the_web_ui(browser: Any, stack: Handle) -> None:
    h = stack
    secret_hex = secrets.token_hex(32)  # clave de PRUEBA, generada para esta ejecución (nunca la identidad B4)
    identity = Keypair.from_hex(secret_hex)

    # 1) arranque y valores efectivos DENTRO del contenedor: modo continuo por defecto, límites y endurecimiento
    with urllib.request.urlopen(h.base + "/health", timeout=10) as response:  # noqa: S310 - 127.0.0.1 local
        assert json.loads(response.read()) == {"status": "ok"}
    eff = json.loads(compose(h, "exec", "-T", "app", "python", "-c", _EFFECTIVE).stdout)
    assert eff == {"mode": "continuous", "requests_per_min": 30, "connection_ttl_s": 28800, "secret_ttl_s": 300, "approval_ttl_s": 300, "window_s": 120, "uid": 10001,
                   "cap_eff": "0000000000000000", "no_new_privs": "1", "mode_env_is_set": False}  # continuo SIN configurarlo: es el valor por defecto de la imagen
    first_logs = h.log()
    assert "admin_bootstrap result=created" in first_logs and not re.search(r"relay_ready|session_start|bunker_issued", first_logs)  # arrancar no abre ninguna conexión
    assert json.loads(compose(h, "exec", "-T", "app", "python", "-c", _SOCKETS).stdout) == []  # ni un socket saliente antes de «Iniciar firmante»

    context, page, problems = open_ui(browser, h)
    sign_in(page, h)

    # 2) importación de la identidad por la interfaz: la clave no se devuelve, no se muestra y no se registra
    page.fill("#identity-secret", secret_hex)
    page.click("#identity-import")
    expect(page.locator("#identity-pub")).to_have_text(identity.public_hex)
    assert page.input_value("#identity-secret") == "" and secret_hex not in page.content() + page.inner_text("body")
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo", timeout=30000)

    # 3) la URI bunker se emite SOLO desde la interfaz y no queda en ningún registro
    uri = issue_uri(page)
    secret = uri.split("secret=")[1]
    client = pair_from_ui_with(page, h, uri)
    logs = h.log()
    for leaked in (secret, uri, secret_hex, "nsec1"):
        assert leaked not in logs, leaked[:8]
    assert not re.search(r"bunker://[0-9a-f]{64}", logs)

    clients: list[RelayClient] = [client]
    try:
        # 4) sign_event: pendiente hasta que una persona decide; con DOS firmas en una misma conexión (el modo continuo no tiene tope total)
        for challenge in (CHALLENGE, "cd" * 32):
            template = login_template(identity.public_hex, now=int(time.time()), origin=ORIGIN, challenge=challenge)
            client.send("sign_event", [template])
            assert client.silent(1.0)  # NADA se firma sin la aprobación humana
            card = approve_card(page, "sign_event")
            expect(card.locator("ul.checks li.pass")).to_have_count(11)
            card.locator("button.ok").click()
            reply = client.reply()
            assert reply.error is None and parse_and_verify_event(json.loads(reply.result)).pubkey == identity.public_hex
        expect(page.locator("#signer-signatures")).to_contain_text("2 (cada una aprobada por una persona)")
        client.send("sign_event", [login_template(identity.public_hex, now=int(time.time()), origin=ORIGIN, challenge=CHALLENGE)])
        assert client.reply().error == "unauthorized"  # un reto ya firmado no se vuelve a ofrecer (anti-replay)
        expect(page.locator("#pending-count")).to_have_text("0")

        # 5) límite por conexión: 30 por minuto, con otra conexión (cupo propio); sin detener el firmante ni revocar
        second = pair_from_ui(page, h)
        clients.append(second)
        for _ in range(35):
            second.send("get_public_key", [])
        answered = 0
        while not second.silent(2.0):
            answered += 1
        assert answered == 30  # el `connect` no cuenta (aún no era activa): 30 respuestas y los 5 restantes se descartan sin responder
        expect(page.locator("#signer-state")).to_have_text("Listo")  # superar el límite no detiene el firmante
        expect(page.locator("#connections-list li", has_text=second.ndk.key.public_hex[:8])).to_contain_text("active")

        # 6) revocación individual desde la interfaz: solo la segunda
        page.locator("#connections-list li", has_text=second.ndk.key.public_hex[:8]).locator(".revoke-btn").click()
        expect(page.locator("#connections-list li", has_text=second.ndk.key.public_hex[:8])).to_contain_text("revoked")
        second.send("get_public_key", [])
        assert second.reply().error == "unauthorized"
        assert client.call("get_public_key", []).result == identity.public_hex

        # 7) reconexión: el relay desaparece y vuelve; las conexiones y la clave de transporte se conservan, sin repetir `connect`
        assert compose(h, "stop", "relay").returncode == 0
        expect(page.locator("#signer-state")).to_have_text("Reconectando", timeout=20000)
        expect(page.locator("#signer-stop")).to_be_enabled()
        assert compose(h, "start", "relay").returncode == 0
        expect(page.locator("#signer-state")).to_have_text("Listo", timeout=60000)
        again = RelayClient(h.relay_url, client.ndk.transport_pub, ndk=client.ndk)
        clients.append(again)
        assert again.call("get_public_key", []).result == identity.public_hex

        # 8) ni un solo socket hacia fuera de la red de Docker en todo el recorrido
        remotes = json.loads(compose(h, "exec", "-T", "app", "python", "-c", _SOCKETS).stdout)
        assert remotes and all(re.fullmatch(r"(10|172\.(1[6-9]|2\d|3[01])|192\.168)\..*", r) for r in remotes), remotes  # solo direcciones privadas (el relay local)

        # 9) detener: cierre ordenado y revocación
        page.click("#signer-stop")
        expect(page.locator("#signer-state")).to_have_text("Detenido")
        expect(page.locator("#connections-list")).not_to_contain_text("active")
    finally:
        for c in clients:
            c.close()

    final = h.log()
    for leaked in (secret, uri, secret_hex, "nsec1", "Traceback"):
        assert leaked not in final, leaked[:8]
    assert not re.search(r"bunker://[0-9a-f]{64}", final) and h.password not in final
    assert problems == [], problems
    context.close()


def pair_from_ui_with(page: Any, h: Handle, uri: str) -> RelayClient:
    """Empareja un cliente con una URI YA emitida: `connect` NIP-04 y aprobación humana en la interfaz."""
    client = RelayClient(h.relay_url, parse_bunker_uri(uri, allow_insecure_relays=True).signer_pubkey)
    client.send("connect", ["", uri.split("secret=")[1]], scheme="nip04")
    approve_card(page, "connect").locator("button.ok").click()
    assert client.reply().result == "ack"
    page.click("#bunker-hide")
    return client

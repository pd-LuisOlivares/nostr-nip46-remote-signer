"""E2E completo en Docker: NAVEGADOR real -> aplicación del producto (contenedor) -> relay del laboratorio <- cliente NDK 2.12.2 REAL (Node).

Se activa con E2E_DOCKER=1 y requiere las imágenes `nostr-nip46-remote-signer:dev`, `nip46-lab-py:1.0a` y `nip46-lab-node:1.0a`. Sin servicios externos: el
producto solo conoce `ws://relay:7777`; la interfaz se publica únicamente en 127.0.0.1. NO es una autenticación con Stacker News.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

from tests.e2e.conftest import ROOT, free_port, wait_http

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("E2E_DOCKER") != "1", reason="defina E2E_DOCKER=1 para ejecutar el E2E en Docker")]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "lab" / "e2e" / "compose.yaml"), "-p", "nip46-e2e"]


def compose(*args: str, env: dict[str, str] | None = None, timeout: int = 240) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*COMPOSE, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, **(env or {})}, timeout=timeout)


@pytest.fixture
def stack() -> Iterator[tuple[str, str, dict[str, str]]]:
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    port = free_port()
    password = secrets.token_urlsafe(24)  # administrador FICTICIO de esta ejecucion; solo vive en el entorno de compose y en el contenedor
    env = {"E2E_PORT": str(port), "LAB_ADMIN_PASSWORD": password}
    compose("down", "-v", "--remove-orphans", env=env, timeout=120)
    up = compose("up", "-d", "relay", "app", env=env)
    assert up.returncode == 0, up.stderr[-400:]
    try:
        base = f"http://127.0.0.1:{port}"
        wait_http(base + "/health", timeout=40)
        yield base, password, env
    finally:
        compose("down", "-v", "--remove-orphans", env=env, timeout=120)


def test_browser_drives_the_containerised_signer_for_the_real_ndk_client(browser: Any, stack: tuple[str, str, dict[str, str]]) -> None:
    base, password, env = stack
    context = browser.new_context(base_url=base)
    page = context.new_page()
    page.goto("/")
    page.fill("#login-username", "e2e-operador")
    page.fill("#login-password", password)
    page.click("#login-btn")
    expect(page.locator("#view-app")).to_be_visible()
    page.click("#identity-create")
    expect(page.locator("#identity-pub")).to_have_text(re.compile(r"^[0-9a-f]{64}$"))
    identity_pub = page.inner_text("#identity-pub").strip()
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo", timeout=20000)
    page.click("#bunker-issue")
    expect(page.locator("#bunker-box")).to_be_visible()
    uri = page.input_value("#bunker-uri")
    assert uri.startswith("bunker://") and "relay=ws" in uri

    client = subprocess.Popen([*COMPOSE, "run", "--rm", "-T", "client"], env={**os.environ, **env}, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    assert client.stdin is not None
    client.stdin.write(uri + "\n")  # la URI llega al cliente por la entrada estándar (nunca por archivo ni argumentos)
    client.stdin.flush()
    try:
        connect_card = page.locator("#pending-list .kind-connect")
        expect(connect_card).to_have_count(1, timeout=60000)
        connect_card.locator("button.ok").click()
        sign_card = page.locator("#pending-list .kind-sign_event")
        expect(sign_card).to_have_count(1, timeout=60000)
        expect(sign_card.locator("ul.checks li.pass")).to_have_count(11)
        expect(sign_card.locator("ul.checks li.fail")).to_have_count(0)
        expect(sign_card).to_contain_text("https://sn.lab.invalid")
        sign_card.locator("button.ok").click()
        out, err = client.communicate(timeout=90)
    except Exception:
        client.kill()
        raise
    events = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    ready = next(e for e in events if e.get("ev") == "ready_result")
    login = next(e for e in events if e.get("ev") == "login_event")
    assert ready["ok"] is True and ready["matches_identity"] is True and ready["user_pub8"] == identity_pub[:8], ready
    # el cliente NDK real verificó id, firma, reto e identidad como lo hace el servidor de Stacker News
    assert login["all_ok"] is True and login["pubkey_is_identity"] is True and login["kind"] == 27235, login
    assert client.returncode == 0, err[-300:]

    expect(page.locator("#signer-signatures")).to_contain_text("1 (cada una aprobada por una persona)")  # modo continuo (por defecto de la imagen): sin tope total, cada firma aprobada por una persona
    page.click("#signer-stop")
    expect(page.locator("#signer-state")).to_have_text("Detenido")
    audit = page.inner_text("#audit-body")
    for expected in ("session_start", "sign_ok", "session_end"):
        assert expected in audit
    logs = compose("logs", "--no-color", "--no-log-prefix", "app", env=env).stdout
    assert uri.split("secret=")[1] not in logs and uri not in logs  # nunca la URI
    assert password not in logs and "$argon2" not in logs and "event=login_ok" in logs  # el registro tiene el evento, nunca la contraseña ni el hash
    context.close()

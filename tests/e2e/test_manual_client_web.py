"""B6.1D-R3: cliente web de laboratorio (NDK 2.12.2 REAL en Node) contra el firmante REAL del producto y un relay local, todo en Docker Compose, con DOS navegadores
(pestaña A = firmante, pestaña B = cliente). Se activa con E2E_DOCKER=1 y requiere las imágenes del laboratorio `nip46-lab-py:1.0a` y `nip46-lab-node:1.0a`.

IMPORTANTE (qué es cada cosa): los clics de «Aprobar» de estas pruebas los hace PLAYWRIGHT: son aprobaciones AUTOMATIZADAS de prueba, distintas de las que realiza el
propietario en la validación manual (que nadie automatiza ni sustituye). Credenciales ficticias y aleatorias; proyecto, imagen y puertos propios; sin Internet.
Parámetros de ESTAS pruebas (más cortos que los de la demostración: ventana 10 s, TTL de aprobación 25 s, el cliente deja de esperar a los 14 s).
"""
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.conftest import ROOT, free_port, wait_http

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("E2E_DOCKER") != "1", reason="defina E2E_DOCKER=1 para ejecutar las pruebas de Docker")]
IMAGE = "nostr-nip46-remote-signer:r3-test"
USER = "r3-operador"
WINDOW_S, TTL_S, CLIENT_TIMEOUT_MS = 10, 25, 14000
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SECRETS_SEEN: list[str] = []  # secretos de URI usados por estas pruebas: no deben aparecer en NINGUN registro
WEB = ROOT / "lab" / "manual" / "client_web"


class Stack:
    def __init__(self, tmp: Path) -> None:
        self.project = f"nip46-r3-{secrets.token_hex(3)}"
        self.app_port, self.relay_port, self.client_port = free_port(), free_port(), free_port()
        self.app, self.client = f"http://127.0.0.1:{self.app_port}", f"http://127.0.0.1:{self.client_port}"
        self.password = secrets.token_urlsafe(24)
        self.empty_env = tmp / "vacio.env"
        self.empty_env.write_text("", encoding="utf-8")

    def env(self) -> dict[str, str]:
        return {**os.environ, "APP_PORT": str(self.app_port), "APP_IMAGE": IMAGE, "ADMIN_USERNAME": USER, "ADMIN_PASSWORD": self.password,
                "MANUAL_RELAY_PORT": str(self.relay_port), "MANUAL_CLIENT_PORT": str(self.client_port), "MANUAL_SIGNER_WINDOW_S": str(WINDOW_S),
                "MANUAL_APPROVAL_TTL_S": str(TTL_S), "MANUAL_CLIENT_OP_TIMEOUT_MS": str(CLIENT_TIMEOUT_MS)}

    def dc(self, *args: str, timeout: int = 400) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["docker", "compose", "--env-file", str(self.empty_env), "-p", self.project, "-f", "compose.yaml", "-f", "lab/manual/compose.manual.yaml", *args],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env(), timeout=timeout)

    def logs(self, service: str) -> str:
        return self.dc("logs", "--no-color", "--no-log-prefix", service).stdout


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    for image in ("nip46-lab-py:1.0a", "nip46-lab-node:1.0a"):
        if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
            pytest.skip(f"falta la imagen de laboratorio {image} (lab/README.md)")
    s = Stack(tmp_path_factory.mktemp("r3"))
    try:
        up = s.dc("up", "--build", "-d")
        assert up.returncode == 0, up.stderr[-500:]
        wait_http(s.app + "/health", timeout=120)
        wait_http(s.client + "/healthz", timeout=60)
        yield s
    finally:
        s.dc("down", "-v", "--remove-orphans", timeout=180)  # -v: solo los volumenes de ESTE proyecto (el de datos del firmante y los anonimos de sus contenedores)
        subprocess.run(["docker", "image", "rm", "-f", IMAGE], capture_output=True, timeout=60)


# ------------------------------------------------------------------------------------------------ pestaña A: firmante
def login_signer(browser: Any, s: Stack) -> tuple[Any, Any]:
    context = browser.new_context(base_url=s.app)
    page = context.new_page()
    page.goto("/")
    page.fill("#login-username", USER)
    page.fill("#login-password", s.password)
    page.click("#login-btn")
    expect(page.locator("#view-app")).to_be_visible()
    expect(page.locator("#signer-state")).not_to_have_text("—")
    return context, page


def fresh_signer(page: Any) -> str:
    if page.inner_text("#signer-state").strip() in ("Listo", "Iniciando"):
        page.click("#signer-stop")
        expect(page.locator("#signer-state")).to_have_text("Detenido", timeout=15000)
    page.click("#identity-create")
    expect(page.locator("#identity-pub")).to_have_text(HEX64)
    pub = str(page.inner_text("#identity-pub")).strip()
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo", timeout=25000)
    return pub


def issue_uri(page: Any) -> str:
    previous = str(page.input_value("#bunker-uri"))
    page.click("#bunker-issue")
    expect(page.locator("#bunker-box")).to_be_visible()
    expect(page.locator("#bunker-uri")).not_to_have_value(previous)  # espera a la URI NUEVA (la anterior se ve hasta que llega la respuesta)
    uri = str(page.input_value("#bunker-uri"))
    SECRETS_SEEN.append(uri.split("secret=")[1])
    return uri


def card(page: Any, kind: str, nth: int = 0) -> Any:
    loc = page.locator(f"#pending-list .kind-{kind}").nth(nth)
    expect(loc).to_be_visible(timeout=12000)
    return loc


def approve(page: Any, kind: str, nth: int = 0) -> None:
    """APROBACION AUTOMATIZADA DE PRUEBA (clic de Playwright en la pestaña del firmante). No es la aprobacion del propietario."""
    card(page, kind, nth).locator("button.ok").click()


def audit_rows(page: Any) -> list[tuple[int, str, str]]:
    """Filas de auditoria de la SESION ACTUAL del firmante (la auditoria del proceso conserva las de sesiones anteriores)."""
    rows = []
    for tr in page.locator("#audit-body tr").all():
        cells = [c.strip() for c in tr.inner_text().split("\t")]
        rows.append((int(cells[0]), cells[2], cells[3] if len(cells) > 3 else ""))
    rows.sort()
    start = max((seq for seq, event, _ in rows if event == "session_start"), default=0)
    return [r for r in rows if r[0] >= start]


# ------------------------------------------------------------------------------------------------ pestaña B: cliente
def open_client(browser: Any, s: Stack) -> tuple[Any, Any, list[str]]:
    context = browser.new_context(base_url=s.client)
    page = context.new_page()
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto("/")
    return context, page, requests


def start_client(page: Any, uri: str) -> None:
    page.fill("#uri", uri)
    page.click("#session-btn")
    expect(page.locator("#panel-ops")).to_be_visible()
    assert page.input_value("#uri") == ""  # la URI no permanece en el campo


def rows(page: Any, op_type: str) -> Any:
    return page.locator(f'tr.op-row[data-op-type="{op_type}"]')  # el DOM lista la mas reciente primero


def wait_state(row: Any, state: str, timeout: int = 15000) -> None:
    expect(row).to_have_attribute("data-state", state, timeout=timeout)


def connect_client(a: Any, b: Any) -> None:
    b.click("#op-connect")
    approve(a, "connect")
    wait_state(rows(b, "connect").first, "ok")


def pending_count(a: Any) -> int:
    return int(a.inner_text("#pending-count"))


# ================================================================================================ pruebas
def test_node_verifier_unit_tests_accept_only_fully_verified_signatures() -> None:
    """El verificador (id, BIP-340, identidad, plantilla, reto) rechaza firmas alteradas, ids falsos, otra clave, otra plantilla y basura (node --test, sin red)."""
    run = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL", "-v", f"{WEB}:/lab/node/web:ro", "nip46-lab-node:1.0a",
                          "node", "--test", "web/verify.test.mjs"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert run.returncode == 0, run.stdout[-800:] + run.stderr[-400:]
    assert re.search(r"# pass 7\b", run.stdout) and re.search(r"# fail 0\b", run.stdout), run.stdout[-300:]


def test_full_nip46_flow_through_two_browser_tabs_with_the_real_ndk_client(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    identity = fresh_signer(a)
    uri = issue_uri(a)
    ctx_b, b, requests = open_client(browser, stack)
    start_client(b, uri)
    expect(b.locator("#info-ndk")).to_contain_text("NDK 2.12.2")  # cliente real, version verificada en tiempo de ejecucion
    expect(b.locator("#info-relay")).to_have_text("relay:7777")

    b.click("#op-ping")  # sin conexion aprobada, el firmante NO responde a un cliente desconocido
    wait_state(rows(b, "ping").first, "rejected", 12000)
    assert pending_count(a) == 0

    b.click("#op-connect")  # connect: exige aprobacion humana
    expect(card(a, "connect")).to_contain_text("Conexión de un cliente")
    b.wait_for_timeout(2500)
    wait_state(rows(b, "connect").first, "pending", 3000)  # sigue pendiente: nadie aprobo
    approve(a, "connect")
    wait_state(rows(b, "connect").first, "ok")
    expect(b.locator("#info-identity")).to_have_text(f"{identity[:8]}…")  # identidad del firmante = la que muestra el panel A
    b.click("#op-pubkey")
    wait_state(rows(b, "get_public_key").first, "ok", 12000)
    b.click("#op-ping")
    wait_state(rows(b, "ping").first, "ok", 12000)

    b.click("#op-sign")  # firma valida: NO se firma sola
    expect(card(a, "sign_event")).to_contain_text("Plazo efectivo para firmar")
    b.wait_for_timeout(3000)
    wait_state(rows(b, "sign_valid").first, "pending", 3000)
    expect(a.locator("#signer-signatures")).to_contain_text("0 de 2")
    assert not [r for r in audit_rows(a) if r[1] == "sign_ok"]
    approve(a, "sign_event")
    signed = rows(b, "sign_valid").first
    wait_state(signed, "signed", 15000)
    expect(signed.locator("ul.checks li.pass")).to_have_count(7)  # id, firma BIP-340, identidad, contenido, reto... TODAS verificadas
    expect(signed.locator("ul.checks li.fail")).to_have_count(0)
    expect(signed).to_contain_text("Firma recibida y VERIFICADA")
    expect(a.locator("#recent-list")).to_contain_text("Firmada correctamente")
    expect(a.locator("#signer-signatures")).to_contain_text("1 (cada una aprobada por una persona)")

    audit = audit_rows(a)  # la decision HUMANA de esa solicitud precede a la firma
    sign_seq = next(seq for seq, event, _ in audit if event == "sign_ok")
    human = [seq for seq, event, detail in audit if event == "decision" and "kind=sign_event" in detail and "approved=true" in detail and "reason=humano" in detail]
    assert human and max(human) < sign_seq
    assert all(urllib.request.urlparse(u).netloc == f"127.0.0.1:{stack.client_port}" for u in requests)  # la pagina B solo habla con su propio servicio
    ctx_a.close()
    ctx_b.close()


def test_every_invalid_signature_variant_is_rejected_without_reaching_the_operator(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    ctx_b, b, _ = open_client(browser, stack)
    start_client(b, issue_uri(a))
    connect_client(a, b)
    for variant in ("origen", "kind", "metodo", "contenido", "edad", "reto"):
        b.select_option("#variant", variant)
        b.click("#op-invalid")
        row = rows(b, "sign_invalid").first
        wait_state(row, "rejected", 12000)
        expect(row).to_contain_text("Rechazo esperado")
        assert pending_count(a) == 0, variant  # nunca llegaron a una tarjeta: se denegaron solas
    expect(a.locator("#signer-signatures")).to_contain_text("0 de 2")
    b.click("#op-sign")  # una valida (aprobada por la prueba) y despues su REPETICION
    approve(a, "sign_event")
    wait_state(rows(b, "sign_valid").first, "signed", 15000)
    b.select_option("#variant", "repeticion")
    b.click("#op-invalid")
    wait_state(rows(b, "sign_invalid").first, "rejected", 12000)
    assert pending_count(a) == 0
    ctx_a.close()
    ctx_b.close()


def test_a_late_approval_is_refused_by_the_revalidation_and_the_client_shows_it_as_rejected(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    ctx_b, b, _ = open_client(browser, stack)
    start_client(b, issue_uri(a))
    connect_client(a, b)
    b.click("#op-sign")
    late = card(a, "sign_event")
    expect(late).to_contain_text(re.compile(r"Plazo efectivo para firmar: \d+ s"))
    expect(late).to_contain_text(f"La aprobación caduca en: ")
    a.wait_for_timeout((WINDOW_S + 2) * 1000)  # el operador tarda mas que la ventana de firma
    expect(late).to_contain_text("Ya no puede firmarse")
    expect(late.locator("button.ok")).to_have_text("Aprobar (ya no firmará)")
    late.locator("button.ok").click()  # aprobacion automatizada de prueba, FUERA de plazo
    wait_state(rows(b, "sign_valid").first, "rejected", 12000)
    expect(rows(b, "sign_valid").first).not_to_contain_text("VERIFICADA")
    expect(a.locator("#recent-list")).to_contain_text("Rechazada al firmar: la política dejó de cumplirse")
    expect(a.locator("#signer-signatures")).to_contain_text("0 de 2")
    assert not [r for r in audit_rows(a) if r[1] == "sign_ok"]
    ctx_a.close()
    ctx_b.close()


def test_a_request_nobody_answers_expires_on_the_client_and_a_late_reply_never_counts_as_success(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    ctx_b, b, _ = open_client(browser, stack)
    start_client(b, issue_uri(a))
    connect_client(a, b)
    b.click("#op-sign")
    row = rows(b, "sign_valid").first
    card(a, "sign_event")
    wait_state(row, "expired", CLIENT_TIMEOUT_MS + 8000)  # el cliente deja de esperar
    expect(row).to_contain_text("dejó de esperar")
    approve(a, "sign_event")  # la aprobacion llega TARDE (tras la ventana): el firmante rechaza y esa respuesta llega despues de expirar
    expect(row.locator(".warn")).to_be_visible(timeout=12000)
    expect(row.locator(".warn")).to_contain_text("respuesta tardía")
    wait_state(row, "expired", 2000)  # sigue expirada: una respuesta tardia JAMAS la convierte en exito
    expect(row).not_to_contain_text("VERIFICADA")
    ctx_a.close()
    ctx_b.close()


def test_simultaneous_signature_requests_are_correlated_by_request_id(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    ctx_b, b, _ = open_client(browser, stack)
    start_client(b, issue_uri(a))
    connect_client(a, b)
    b.click("#op-sign")
    b.click("#op-sign")
    expect(a.locator("#pending-list .kind-sign_event")).to_have_count(2, timeout=12000)
    ops: dict[str, str] = {}
    for tr in b.locator('tr.op-row[data-op-type="sign_valid"]').all():
        ops[tr.get_attribute("data-op-id") or ""] = re.search(r"reto sha16 ([0-9a-f]{16})", tr.inner_text()).group(1)  # type: ignore[union-attr]
    assert len(ops) == 2 and len(set(ops.values())) == 2
    first_id, second_id = sorted(ops, key=lambda i: int(i[2:]))
    second_card = a.locator("#pending-list .kind-sign_event").filter(has_text=ops[second_id])  # tarjeta de la SEGUNDA solicitud
    second_card.locator("button.ok").click()
    wait_state(b.locator(f'tr.op-row[data-op-id="{second_id}"]'), "signed", 12000)  # se firma la que se aprobo...
    assert b.locator(f'tr.op-row[data-op-id="{first_id}"]').get_attribute("data-state") == "pending"  # ...y la otra sigue pendiente (no se cruzan)
    a.locator("#pending-list .kind-sign_event").filter(has_text=ops[first_id]).locator("button.ok").click()
    wait_state(b.locator(f'tr.op-row[data-op-id="{first_id}"]'), "signed", 12000)
    ids = []
    for op_id in (first_id, second_id):
        row = b.locator(f'tr.op-row[data-op-id="{op_id}"]')
        expect(row.locator("ul.checks li.pass")).to_have_count(7)  # cada respuesta coincide con SU plantilla (si se cruzaran, 'contenido idéntico' fallaria)
        ids.append(re.search(r"id de solicitud (\S+)", row.inner_text()).group(1))  # type: ignore[union-attr]
    assert len(set(ids)) == 2 and all(ids)
    ctx_a.close()
    ctx_b.close()


def test_a_used_uri_cannot_be_reused_by_a_new_client_session(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    uri = issue_uri(a)
    ctx_1, b1, _ = open_client(browser, stack)
    start_client(b1, uri)
    connect_client(a, b1)
    b1.click("#close-btn")  # cierra la sesion del cliente: se olvidan URI y claves
    expect(b1.locator("#panel-ops")).to_be_hidden()
    ctx_2, b2, _ = open_client(browser, stack)
    start_client(b2, uri)  # la MISMA URI (de un solo uso) en una sesion nueva
    b2.click("#op-connect")
    wait_state(rows(b2, "connect").first, "rejected", 15000)
    assert pending_count(a) == 0  # ni siquiera llega al operador
    ctx_a.close()
    ctx_1.close()
    ctx_2.close()


def test_two_client_sessions_are_isolated_from_each_other(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    uri1 = issue_uri(a)
    uri2 = issue_uri(a)
    assert uri1 != uri2 and uri1.split("secret=")[1] != uri2.split("secret=")[1]
    ctx_1, b1, _ = open_client(browser, stack)
    ctx_2, b2, _ = open_client(browser, stack)
    start_client(b1, uri1)
    start_client(b2, uri2)
    connect_client(a, b1)
    b1.click("#op-ping")
    wait_state(rows(b1, "ping").first, "ok", 12000)
    connect_client(a, b2)
    assert b1.locator("tr.op-row").count() == 2 and b2.locator("tr.op-row").count() == 1  # cada sesion ve SOLO sus operaciones
    assert b1.inner_text("#info-client") != b2.inner_text("#info-client")  # claves efimeras distintas
    for path in ("/api/state", "/api/session"):
        for token in (None, "0" * 48, "zz"):
            status, _, _ = http_call(stack, "GET" if path == "/api/state" else "DELETE", path, headers={"X-Lab-Token": token, "X-Lab-Client": "1"} if token else {"X-Lab-Client": "1"})
            assert status == 401, (path, token)
    ctx_a.close()
    ctx_1.close()
    ctx_2.close()


def test_relay_restart_ends_the_signer_session_without_silent_reconnection_and_a_fresh_uri_works(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    ctx_b, b, _ = open_client(browser, stack)
    start_client(b, issue_uri(a))
    connect_client(a, b)
    assert stack.dc("restart", "relay").returncode == 0
    expect(a.locator("#signer-state")).to_have_text(re.compile("Detenido|Fallido"), timeout=40000)  # el firmante termina: no reconecta en silencio
    b.click("#op-ping")
    wait_state(rows(b, "ping").first, "expired", CLIENT_TIMEOUT_MS + 12000)  # nadie contesta; el cliente NO inventa una respuesta
    for _ in range(40):  # el relay vuelve a aceptar conexiones
        if stack.dc("exec", "-T", "relay", "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 7777), 2).close()").returncode == 0:
            break
        time.sleep(1)
    fresh_signer(a)  # reconexion CONTROLADA: firmante nuevo, URI nueva, sesion de cliente nueva
    ctx_2, b2, _ = open_client(browser, stack)
    start_client(b2, issue_uri(a))
    connect_client(a, b2)
    ctx_a.close()
    ctx_b.close()
    ctx_2.close()


# ------------------------------------------------------------------------------------------------ seguridad del cliente web
def http_call(s: Stack, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    conn = http.client.HTTPConnection("127.0.0.1", s.client_port, timeout=15)
    try:
        hdrs = dict(headers or {})
        conn.putrequest(method, path, skip_host="Host" in hdrs, skip_accept_encoding=True)
        if "Host" in hdrs:
            conn.putheader("Host", hdrs.pop("Host"))
        for k, v in hdrs.items():
            conn.putheader(k, v)
        conn.putheader("Content-Length", str(len(body or b"")))
        conn.endheaders(body or b"")
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read().decode("utf-8", "replace")
    finally:
        conn.close()


JSON = {"Content-Type": "application/json", "X-Lab-Client": "1"}
GOOD_PUB = "ab" * 32


def uri_for(relay: str, extra: str = "", secret: str = "S3cr3t-0123456789abcdef") -> str:
    return f"bunker://{GOOD_PUB}?relay={relay}" + (f"&secret={secret}" if secret else "") + extra


def test_web_client_http_surface_is_closed_to_foreign_pages_hosts_and_non_local_relays(stack: Stack) -> None:
    status, headers, _ = http_call(stack, "GET", "/")
    assert status == 200 and "default-src 'none'" in headers["content-security-policy"] and "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-frame-options"] == "DENY" and headers["cache-control"] == "no-store" and not [h for h in headers if h.startswith("access-control-")]
    assert http_call(stack, "GET", "/", headers={"Host": "evil.example"})[0] == 400  # DNS rebinding
    body = json.dumps({"uri": uri_for("ws%3A%2F%2Frelay%3A7777")}).encode()
    assert http_call(stack, "POST", "/api/session", body, {"Content-Type": "application/json"})[0] == 403  # sin la cabecera propia (pagina ajena)
    assert http_call(stack, "POST", "/api/session", body, {**JSON, "Origin": "http://evil.example"})[0] == 403  # Origin ajeno
    status, headers, _ = http_call(stack, "OPTIONS", "/api/session", None, {"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert status in (403, 405) and not [h for h in headers if h.startswith("access-control-")]  # sin CORS: el preflight no se concede
    assert http_call(stack, "GET", "/api/state")[0] == 401 and http_call(stack, "POST", "/api/op", b"{}", JSON)[0] == 401
    assert http_call(stack, "POST", "/api/session", b"x" * 5000, JSON)[0] == 413 and http_call(stack, "POST", "/api/session", b"{}", {"Content-Type": "text/plain", "X-Lab-Client": "1"})[0] == 415
    for path in ("/server.mjs", "/verify.mjs", "/verify.test.mjs", "/../server.mjs", "/%2e%2e/server.mjs", "/api/", "/etc/passwd"):
        assert http_call(stack, "GET", path)[0] in (401, 404), path  # nada fuera de la lista de archivos estaticos

    for relay in ("wss%3A%2F%2Frelay.damus.io", "ws%3A%2F%2Frelay.damus.io%3A7777", "ws%3A%2F%2Fevil.example%3A7777", "ws%3A%2F%2F10.0.0.5%3A7777", "ws%3A%2F%2F127.0.0.1.evil.com%3A7777",
                  "ws%3A%2F%2Fuser%3Apw%40relay%3A7777", "http%3A%2F%2Frelay%3A7777", "ws%3A%2F%2Frelay%3A7777%3Fx%3D1"):
        uri = uri_for(relay)
        status, _, text = http_call(stack, "POST", "/api/session", json.dumps({"uri": uri}).encode(), JSON)
        assert status == 400, relay
        assert "S3cr3t" not in text and "bunker://" not in text and GOOD_PUB not in text  # el error no repite la URI
    for uri in (uri_for("ws%3A%2F%2Frelay%3A7777", secret=""), uri_for("ws%3A%2F%2Frelay%3A7777", "&pubkey=" + GOOD_PUB), "bunker://zz?relay=ws%3A%2F%2Frelay%3A7777&secret=abc",
                "http://" + GOOD_PUB, "x" * 3000, "", 5):
        assert http_call(stack, "POST", "/api/session", json.dumps({"uri": uri}).encode(), JSON)[0] == 400

    status, _, text = http_call(stack, "POST", "/api/session", json.dumps({"uri": uri_for("ws%3A%2F%2Frelay%3A7777")}).encode(), JSON)  # una URI local sintacticamente valida SI crea sesion
    assert status == 201
    created = json.loads(text)
    assert "S3cr3t" not in text and "bunker://" not in text and set(created) == {"token", "session"}
    auth = {**JSON, "X-Lab-Token": created["token"]}
    for path in ("/api/approve", "/api/requests/abc/approve", "/api/requests", "/api/identity", "/api/signer/start"):
        assert http_call(stack, "POST", path, b"{}", auth)[0] == 404, path  # el cliente NO tiene ninguna forma de aprobar ni de administrar el firmante
    assert http_call(stack, "DELETE", "/api/session", None, auth)[0] == 204 and http_call(stack, "GET", "/api/state", None, auth)[0] == 401


def test_page_b_keeps_nothing_in_the_browser_and_never_shows_the_uri(browser: Any, stack: Stack) -> None:
    ctx_a, a = login_signer(browser, stack)
    fresh_signer(a)
    uri = issue_uri(a)
    ctx_b, b, requests = open_client(browser, stack)
    start_client(b, uri)
    b.click("#op-ping")
    wait_state(rows(b, "ping").first, "rejected", 12000)
    secret = uri.split("secret=")[1]
    content = b.content()
    where = content.find(secret)
    assert where < 0, "EL SECRETO ESTA EN EL DOM: ..." + content[max(0, where - 120): where + 40]
    assert not re.search(r"bunker://[0-9a-f]{8}", content) and secret not in b.url
    assert b.evaluate("[localStorage.length, sessionStorage.length, document.cookie]") == [0, 0, ""]
    assert "?" not in b.url and "#" not in b.url
    assert b.locator("input[type=password]").input_value() == ""
    assert not [u for u in requests if not u.startswith(f"http://127.0.0.1:{stack.client_port}/")]  # ninguna peticion fuera del propio servicio
    ctx_a.close()
    ctx_b.close()


def exec_out(s: Stack, service: str, *cmd: str) -> subprocess.CompletedProcess[str]:
    return s.dc("exec", "-T", service, *cmd, timeout=60)


def public_connections(s: Stack, service: str) -> list[str]:
    raw = exec_out(s, service, "sh", "-c", "cat /proc/net/tcp /proc/net/tcp6").stdout
    found = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) > 3 and parts[3] == "01" and ":" in parts[2]:
            host = parts[2].split(":")[0]
            if len(host) == 8:
                ip = ipaddress.ip_address(bytes.fromhex(host)[::-1])
            else:
                packed = b"".join(bytes.fromhex(host[i:i + 8])[::-1] for i in range(0, 32, 8))
                ip = ipaddress.ip_address(packed)
                ip = ip.ipv4_mapped or ip  # type: ignore[assignment]
            if not (ip.is_private or ip.is_loopback):
                found.append(str(ip))
    return found


def test_there_are_no_external_connections_and_the_client_cannot_reach_the_signer(stack: Stack) -> None:
    for service in ("app", "relay", "client-web"):
        assert public_connections(stack, service) == [], service  # ninguna conexion TCP establecida hacia direcciones publicas
    probe = "const s=require('net').connect(%d,'%s');s.on('connect',()=>{console.log('CONNECTED');process.exit(0)});s.on('error',e=>{console.log('ERR '+e.code);process.exit(0)});setTimeout(()=>{console.log('ERR TIMEOUT');process.exit(0)},3000)"
    assert exec_out(stack, "client-web", "node", "-e", probe % (7777, "relay")).stdout.strip() == "CONNECTED"  # alcanza al relay local...
    assert exec_out(stack, "client-web", "node", "-e", probe % (8000, "app")).stdout.strip().startswith("ERR")  # ...pero NO al firmante (redes separadas)
    back = "import socket,sys\ntry:\n socket.create_connection(('client-web',18080),3)\n print('CONNECTED')\nexcept OSError as e:\n print('ERR')"
    assert exec_out(stack, "app", "python", "-c", back).stdout.strip() == "ERR"  # y el firmante tampoco alcanza al cliente
    info = json.loads(subprocess.run(["docker", "inspect", f"{stack.project}-client-web-1"], capture_output=True, text=True, timeout=30).stdout)[0]
    assert info["HostConfig"]["ReadonlyRootfs"] is True and info["HostConfig"]["CapDrop"] == ["ALL"]
    assert all(p["HostIp"] == "127.0.0.1" for ports in info["NetworkSettings"]["Ports"].values() for p in ports)  # solo loopback


def test_no_secret_appears_in_any_log_and_the_client_log_is_structured_and_redacted(stack: Stack) -> None:
    assert SECRETS_SEEN, "las pruebas anteriores debieron emitir URI"
    client_log = stack.logs("client-web")
    for service, text in (("app", stack.logs("app")), ("relay", stack.logs("relay")), ("client-web", client_log)):
        for secret in SECRETS_SEEN:
            assert secret not in text, service  # el secreto de ninguna URI aparece en ningun registro
        assert stack.password not in text and "bunker://" not in text, service
    assert not re.search(r"[0-9a-f]{64}", client_log)  # ni claves ni ids completos
    events = {json.loads(line)["ev"] for line in client_log.splitlines() if line.startswith("{")}
    assert {"listening", "session_created", "op_result", "session_closed"} <= events
    assert "ndk" in client_log and "2.12.2" in client_log


# ------------------------------------------------------------------------------------------------ respuestas MANIPULADAS: nunca se muestran como firma
class InProcessSigner:
    """El firmante REAL del producto (`SignerRuntime`), en un hilo del proceso de pytest, conectado al relay local. Se usa SOLO para poder manipular la
    serializacion de su respuesta y comprobar que el cliente no la acepta. Sus aprobaciones son PROGRAMATICAS DE PRUEBA (automatizadas), no del propietario."""

    def __init__(self, relay_port: int) -> None:
        import asyncio
        import threading

        from app.config import Settings
        from app.nostr.keys import Keypair
        from app.services.runtime import SignerRuntime

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        settings = Settings(relay_url=f"ws://127.0.0.1:{relay_port}", relay_allow_insecure=True, service_origin="https://sn.manual.invalid", window_s=60,
                            approval_ttl_s=60, max_signatures=10, max_requests=100)
        self.runtime = SignerRuntime(settings)
        self.identity = Keypair.generate()
        self.runtime.set_identity(self.identity)
        self._run(self.runtime.start())
        assert self.runtime.service is not None
        self.service = self.runtime.service

    def _run(self, coro: Any) -> Any:
        import asyncio
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(30)

    def client_uri(self) -> str:
        from app.nostr.nip46 import build_bunker_uri
        secret = self.service.issue_bunker_uri().split("secret=")[1]
        SECRETS_SEEN.append(secret)
        return build_bunker_uri(self.service.transport.public_hex, ["ws://relay:7777"], secret, allow_insecure_relays=True)  # el cliente alcanza el relay como `relay`

    def approve_next(self, kind: str, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pending = [r for r in self.service.approvals.pending() if r.kind.value == kind]
            if pending:
                self.loop.call_soon_threadsafe(self.service.approvals.resolve, pending[0].id, True)
                return
            time.sleep(0.05)
        raise AssertionError(f"no apareció una solicitud {kind}")

    def stop(self) -> None:
        try:
            self._run(self.runtime.stop())
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)


def test_the_client_never_shows_success_for_a_tampered_signer_response(browser: Any, stack: Stack, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.signer as signer_module
    from app.nostr.event import sign_event
    from app.nostr.keys import Keypair

    original = signer_module._event_json
    foreign = Keypair.generate()

    def flip(hex_text: str) -> str:
        return ("b" if hex_text[0] == "a" else "a") + hex_text[1:]

    def tamper_sig(event: Any) -> str:
        d = json.loads(original(event))
        d["sig"] = flip(d["sig"])
        return json.dumps(d)

    def tamper_content(event: Any) -> str:
        d = json.loads(original(event))
        d["content"] = "otro texto"  # id y firma ya no corresponden
        return json.dumps(d)

    def other_request_reply(event: Any) -> str:  # firma VALIDA de la identidad, pero de OTRA solicitud (otro reto): la respuesta no es de esta
        other = sign_event(signer.identity, event.kind, (("challenge", "cd" * 32), *event.tags[1:]), event.content, event.created_at)
        return original(other)

    def foreign_key(event: Any) -> str:  # evento autoconsistente firmado por OTRA clave
        return original(sign_event(foreign, event.kind, event.tags, event.content, event.created_at))

    signer = InProcessSigner(stack.relay_port)
    ctx_b, b, _ = open_client(browser, stack)
    try:
        start_client(b, signer.client_uri())
        b.click("#op-connect")
        signer.approve_next("connect")
        wait_state(rows(b, "connect").first, "ok", 15000)
        for name, tamper in (("firma alterada", tamper_sig), ("contenido alterado", tamper_content), ("respuesta de otra solicitud", other_request_reply),
                             ("firmada por otra clave", foreign_key)):
            monkeypatch.setattr(signer_module, "_event_json", tamper)
            b.click("#op-sign")
            signer.approve_next("sign_event")
            row = rows(b, "sign_valid").first
            wait_state(row, "invalid", 15000)  # la respuesta llego, pero NO se acepta
            expect(row).to_contain_text("NO se acepta como firma")
            expect(row).not_to_contain_text("VERIFICADA")
            assert row.locator("ul.checks li.fail").count() >= 1, name
        assert b.locator('tr.op-row[data-state="signed"]').count() == 0  # ninguna respuesta manipulada llego a verse como firma
        monkeypatch.setattr(signer_module, "_event_json", original)  # control: sin manipulacion, el MISMO camino si da una firma verificada
        b.click("#op-sign")
        signer.approve_next("sign_event")
        wait_state(rows(b, "sign_valid").first, "signed", 15000)
        expect(rows(b, "sign_valid").first.locator("ul.checks li.pass")).to_have_count(7)
    finally:
        signer.stop()
        ctx_b.close()

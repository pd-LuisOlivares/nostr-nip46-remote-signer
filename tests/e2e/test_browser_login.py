"""E2E de NAVEGADOR REAL del inicio de sesión con usuario y contraseña (SQLite + Argon2id -> JWT) y de la defensa P-37 de la interfaz.

Aplicación real (Uvicorn) con una base SQLite temporal y un administrador FICTICIO. No hay servicios externos ni relays públicos.
"""
import json
import re
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.security.operator_auth import MAX_LOGIN_FAILURES
from tests.e2e.conftest import AppHandle
from tests.e2e.test_browser_flow import open_ui, sign_in

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
pytestmark = pytest.mark.e2e
BAD = "contrasena-incorrecta-123"


def try_login(page: Any, username: str, password: str) -> None:
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#login-btn")


# ------------------------------------------------------------------------------------------------ formulario
def test_login_form_is_accessible_and_has_no_terminal_code(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    expect(page.get_by_label("Usuario")).to_be_visible()
    expect(page.get_by_label("Contraseña")).to_be_visible()
    expect(page.get_by_role("button", name="Iniciar sesión")).to_be_visible()
    assert page.get_attribute("#login-password", "type") == "password"
    assert page.get_attribute("#login-username", "autocomplete") == "username" and page.get_attribute("#login-password", "autocomplete") == "current-password"
    assert page.locator("#login-code").count() == 0 and "código de acceso" not in page.inner_text("body").lower()
    assert problems == []
    context.close()


def test_enter_submits_the_form_and_the_password_does_not_stay_in_the_page(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    page.fill("#login-username", app.username)
    page.fill("#login-password", app.password)
    page.press("#login-password", "Enter")  # sin pulsar el boton
    expect(page.locator("#view-app")).to_be_visible()
    assert app.password not in page.content() and page.input_value("#login-password") == ""
    assert problems == []
    context.close()


def test_loading_state_blocks_double_submit_and_is_announced(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    held: list[Any] = []
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and r.url.endswith("/api/auth/login") else None)
    page.route("**/api/auth/login", lambda route: held.append(route))  # la peticion queda en espera: la interfaz debe mostrar «Verificando…»
    page.fill("#login-username", app.username)
    page.fill("#login-password", app.password)
    page.click("#login-btn")
    expect(page.locator("#login-btn")).to_be_disabled()
    expect(page.locator("#login-status")).to_be_visible()
    expect(page.locator("#login-status")).to_have_text("Verificando…")
    assert page.get_attribute("#login-form", "aria-busy") == "true" and page.get_attribute("#login-status", "role") == "status"
    page.press("#login-username", "Enter")  # un segundo envio mientras tanto no debe duplicar la peticion
    page.wait_for_timeout(300)
    assert len(held) == 1 and len(posts) == 1
    held[0].continue_()  # se libera la peticion retenida
    expect(page.locator("#view-app")).to_be_visible()
    expect(page.locator("#login-btn")).to_be_enabled()
    context.close()


# ------------------------------------------------------------------------------------------------ errores seguros
def test_errors_are_generic_identical_for_unknown_user_and_wrong_password_and_limit_message_appears(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    try_login(page, "usuario-inexistente", BAD)
    expect(page.locator("#login-error")).to_be_visible()
    unknown = page.inner_text("#login-error")
    try_login(page, app.username, BAD)
    expect(page.locator("#login-error")).to_be_visible()
    wrong = page.inner_text("#login-error")
    assert unknown == wrong == "Usuario o contraseña incorrectos."  # no revela si el usuario existe
    assert app.username not in page.inner_text("#login-error") and BAD not in page.content()
    for _ in range(MAX_LOGIN_FAILURES - 2):
        try_login(page, app.username, BAD)
        expect(page.locator("#login-btn")).to_be_enabled()
    try_login(page, app.username, app.password)  # incluso con la contraseña correcta: bloqueado por el limite de intentos
    expect(page.locator("#login-error")).to_contain_text("Demasiados intentos")
    expect(page.locator("#view-app")).to_be_hidden()
    assert not [c for c in context.cookies() if c["name"] == "nip46_session"]
    assert problems == []
    assert BAD not in app.log() and app.password not in app.log() and app.username not in app.log()
    context.close()


def test_the_jwt_is_never_exposed_to_page_scripts(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    page.fill("#login-username", app.username)
    page.fill("#login-password", app.password)
    with page.expect_response("**/api/auth/login") as info:
        page.click("#login-btn")
    body = info.value.json()
    assert set(body) == {"csrf_token", "expires_in_s"}  # el cuerpo que recibe el JavaScript no trae el token
    expect(page.locator("#view-app")).to_be_visible()
    cookie = next(c for c in context.cookies() if c["name"] == "nip46_session")
    assert cookie["httpOnly"] is True and cookie["value"].count(".") == 2
    assert page.evaluate("document.cookie") == "" and page.evaluate("[localStorage.length, sessionStorage.length]") == [0, 0]
    assert cookie["value"] not in page.content() and cookie["value"] not in json.dumps(page.evaluate("Object.keys(window)"))
    page.reload()
    expect(page.locator("#view-app")).to_be_visible()  # la sesion sobrevive a una recarga solo por la cookie
    context.close()


# ------------------------------------------------------------------------------------------------ P-35 desde la interfaz
def test_page_loads_and_anonymous_probes_never_block_the_login(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    for _ in range(25):  # cada carga hace un GET /api/auth/session sin sesion (401): antes contaba como fallo y desembocaba en 429
        page.reload()
        expect(page.locator("#view-login")).to_be_visible()
    statuses = page.evaluate("Promise.all(Array.from({length: 30}, () => fetch('/api/status', {credentials: 'same-origin'}).then(r => r.status)))")
    assert set(statuses) == {401}
    sign_in(page, app)  # sigue funcionando: ni 429 ni mensaje de bloqueo
    expect(page.locator("#login-error")).to_be_hidden()
    assert problems == []
    context.close()


# ------------------------------------------------------------------------------------------------ persistencia y reinicio
def test_the_admin_persists_across_restarts_and_the_database_holds_only_the_argon2id_hash(browser: Any, start_app: Callable[..., AppHandle], tmp_path: Path) -> None:
    first = start_app()
    context, page, _ = open_ui(browser, first)
    sign_in(page, first)
    context.close()
    first.proc.stop()
    con = sqlite3.connect(first.db_path)
    (stored,) = con.execute("SELECT password_hash FROM admins").fetchone()
    con.close()
    assert stored.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    raw = Path(first.db_path).read_bytes()
    assert first.password.encode() not in raw

    second = start_app(DATABASE_PATH=first.db_path, ADMIN_PASSWORD="", ADMIN_USERNAME="otro-nombre")  # sin contraseña inicial y con otro usuario en el entorno
    assert not re.search(r"auth event=admin_bootstrap result=created", second.log())
    context, page, _ = open_ui(browser, second)
    sign_in(page, second)  # la misma cuenta, con la contraseña original
    context.close()
    con = sqlite3.connect(first.db_path)
    assert con.execute("SELECT COUNT(*), MIN(username) FROM admins").fetchone() == (1, first.username)
    con.close()


def test_a_session_from_the_previous_run_does_not_survive_a_restart(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    first = start_app()
    context, page, _ = open_ui(browser, first)
    sign_in(page, first)
    cookie = next(c for c in context.cookies() if c["name"] == "nip46_session")["value"]
    context.close()
    first.proc.stop()
    second = start_app(DATABASE_PATH=first.db_path, ADMIN_PASSWORD="")
    stale = browser.new_context().request.get(second.base + "/api/status", headers={"Authorization": f"Bearer {cookie}"})
    assert stale.status == 401  # clave de firma nueva: el JWT anterior ya no vale


def test_the_application_refuses_to_start_without_an_admin_and_without_an_initial_password(start_app: Callable[..., AppHandle]) -> None:
    app = start_app(ADMIN_PASSWORD="", EXPECT_EXIT="1")  # base nueva + sin contraseña inicial: el arranque aborta con instrucciones
    assert app.proc.popen.returncode not in (None, 0)
    time.sleep(0.3)  # deja que el hilo lector termine de volcar la salida
    log = app.log()
    assert "ADMIN_PASSWORD" in log and "ADMIN_PASSWORD_FILE" in log and "README" in log
    assert not Path(app.db_path).exists() or sqlite3.connect(app.db_path).execute("SELECT COUNT(*) FROM admins").fetchone() == (0,)  # nunca una cuenta silenciosa


def test_operational_log_has_authentication_events_and_no_credentials(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    try_login(page, app.username, BAD)
    expect(page.locator("#login-error")).to_be_visible()
    sign_in(page, app)
    page.click("#logout-btn")
    expect(page.locator("#view-login")).to_be_visible()
    context.close()
    log = app.log()
    for event in ("admin_bootstrap result=created", "event=login_failed", "event=login_ok", "event=logout"):
        assert event in log, event
    cookie_like = re.findall(r"eyJ[A-Za-z0-9_-]{10,}\.", log)
    assert not cookie_like and app.password not in log and BAD not in log and "$argon2" not in log


# ------------------------------------------------------------------------------------------------ P-37: «Aprobar» con una comprobación en rojo
def checks(bad_index: int | None = None) -> list[dict[str, Any]]:
    out = [{"name": f"comprobacion {i}", "ok": True, "detail": ""} for i in range(1, 12)]
    if bad_index is not None:
        out[bad_index] = {"name": "origen u esperado", "ok": False, "detail": "u distinto"}
    return out


HOSTILE = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script>'


def card(request_id: str, kind: str = "sign_event", client: str = "aaaa1111", **over: Any) -> dict[str, Any]:
    base = {"id": request_id, "kind": kind, "status": "pending", "client": client, "reason": None, "expires_in_s": 100, "summary": {"kind": 27235}, "checks": []}
    return {**base, **over}


def serve_cards(page: Any, cards: list[dict[str, Any]], approvals: list[str], before: Callable[[], None] | None = None) -> None:
    def handler(route: Any) -> None:
        request = route.request
        if request.method == "GET" and "scope=all" in request.url:
            if before is not None:
                before()  # permite que los valores evolucionen con el tiempo, como en un servidor real
            route.fulfill(status=200, content_type="application/json", body=json.dumps(cards))
        elif request.method == "POST" and request.url.endswith("/approve"):
            approvals.append(request.url.rsplit("/", 2)[-2])  # se registra el intento y se responde sin tocar el servidor real
            route.fulfill(status=200, content_type="application/json", body=json.dumps(cards[0] | {"status": "approved"}))
        else:
            route.continue_()
    page.route(re.compile(r".*/api/requests.*"), handler)  # incluye /api/requests?scope=all y /api/requests/<id>/approve


def test_approve_is_disabled_and_decide_refuses_even_a_synthetic_click_when_a_check_is_red(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    approvals: list[str] = []
    serve_cards(page, [card("badcard", checks=checks(4)), card("okcard", checks=checks()), card("connectcard", kind="connect", summary={"nota": "-"}),
                       card("xsscard", client=HOSTILE, summary={HOSTILE: HOSTILE, "obj": {"a": HOSTILE}}, checks=[{"name": HOSTILE, "ok": False, "detail": HOSTILE}])], approvals)
    sign_in(page, app)
    bad = page.locator("#approve-badcard")
    expect(bad).to_be_disabled()
    expect(page.locator("[data-request-id=badcard]")).to_contain_text("no puede aprobarse")
    expect(page.locator("[data-request-id=badcard] li.fail")).to_have_count(1)
    expect(page.locator("#deny-badcard")).to_be_enabled()

    box = bad.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)  # click REAL
    page.press("body", "Enter")
    bad.dispatch_event("click")  # click SINTETICO de JavaScript: antes llegaba a decide() y enviaba el POST
    expect(page.locator("#banner")).to_contain_text("incumple la política")
    page.wait_for_timeout(500)
    assert approvals == [], approvals  # ninguna aprobacion invalida salio de la interfaz
    expect(bad).to_be_disabled()  # sigue visualmente desactivado

    expect(page.locator("#approve-xsscard")).to_be_disabled()
    page.locator("#approve-xsscard").dispatch_event("click")
    page.wait_for_timeout(300)
    assert approvals == []

    expect(page.locator("#approve-okcard")).to_be_enabled()  # control: con las 11 en verde y en connect si se puede aprobar
    expect(page.locator("#approve-connectcard")).to_be_enabled()
    page.locator("#approve-okcard").click()
    expect(page.locator("#banner")).to_contain_text("aprobada")
    assert approvals == ["okcard"]
    assert problems == []
    context.close()


def test_hostile_card_content_is_rendered_as_text_never_as_html(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    serve_cards(page, [card("xsscard", client=HOSTILE, summary={HOSTILE: HOSTILE, "obj": {"a": HOSTILE}}, checks=[{"name": HOSTILE, "ok": False, "detail": HOSTILE}])], [])
    sign_in(page, app)
    expect(page.locator("#approve-xsscard")).to_be_disabled()
    assert page.locator("#pending-list img, #pending-list script").count() == 0
    assert page.evaluate("typeof window.__pwned") == "undefined"
    assert "<img src=x" in page.locator("[data-request-id=xsscard]").inner_text()
    context.close()



# ------------------------------------------------------------------------------------------------ P-42: resultado real de la firma en la interfaz
def settled(request_id: str, outcome: str | None, reason: str | None = None, **over: Any) -> dict[str, Any]:
    return card(request_id, status="approved", reason="humano", outcome=outcome, outcome_reason=reason, **over)


def test_recent_list_shows_the_real_signing_outcome_and_announces_each_transition(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    history = settled("old", "refused", "politica_incumplida")  # historial que ya existe al entrar: NO debe anunciarse
    cards: list[dict[str, Any]] = [history, settled("w1", None)]
    serve_cards(page, cards, [])
    sign_in(page, app)
    recent = page.locator("#recent-list")
    expect(recent).to_contain_text("Aprobada por el operador; falta el resultado de la firma")  # aprobada, pendiente de resultado: NO es una firma
    expect(recent).to_contain_text("Rechazada al firmar: la política dejó de cumplirse")
    expect(recent).not_to_contain_text("Firmada correctamente")
    expect(page.locator("#banner")).to_be_hidden()  # lo anterior a la entrada no se anuncia

    cards[1]["outcome"] = "signed"  # el servidor confirma la firma
    expect(page.locator("#banner")).to_contain_text("Firma realizada correctamente", timeout=6000)
    expect(recent).to_contain_text("Firmada correctamente")
    expect(recent).not_to_contain_text("falta el resultado de la firma")

    cards.append(settled("w2", "refused", "aprobacion_caducada"))
    expect(page.locator("#banner")).to_contain_text("La firma NO se realizó: la aprobación caducó", timeout=6000)
    expect(page.locator("#banner")).not_to_contain_text("correctamente")
    cards.append(settled("w3", "failed", "sesion_terminada"))
    expect(page.locator("#banner")).to_contain_text("La firma NO se realizó: la sesión terminó antes de obtener el resultado", timeout=6000)
    for expected in ("Rechazada al firmar: la aprobación caducó", "Fallida: la sesión terminó antes de obtener el resultado"):
        expect(recent).to_contain_text(expected)

    # el resto de estados conserva su significado y nunca se presenta como firma
    cards.extend([card("d1", status="denied", reason="humano"), card("e1", status="expired", reason="timeout"), card("c1", status="cancelled", reason="cancelada"),
                  card("k1", kind="connect", status="approved", reason="humano", summary={"nota": "-"})])
    expect(recent).to_contain_text("caducada", timeout=6000)
    for expected in ("rechazada", "cancelada", "aprobada"):
        expect(recent).to_contain_text(expected)
    assert recent.inner_text().count("Firmada correctamente") == 1  # solo w1
    assert "<" not in page.locator("#banner").inner_text()
    assert problems == []
    context.close()


def test_unknown_reason_codes_are_shown_neutrally_without_html(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    serve_cards(page, [settled("w9", "refused", HOSTILE)], [])
    sign_in(page, app)
    expect(page.locator("#recent-list")).to_contain_text("Rechazada al firmar:")
    assert page.locator("#recent-list img, #recent-list script, #banner img, #banner script").count() == 0
    assert page.evaluate("typeof window.__pwned") == "undefined"
    context.close()


def test_real_flow_shows_signed_and_then_a_revalidation_refusal_as_not_signed(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    from app.nostr.nip46 import parse_bunker_uri
    from tests.e2e.conftest import ORIGIN, RelayClient
    from tests.e2e.test_browser_flow import approve_card, issue_uri
    from tests.support import login_template

    app = start_app(SIGNER_WINDOW_S="5")  # ventana de 5 s (margen frente a la carga de la maquina): una aprobacion de mas de 6 s llega con la plantilla fuera de la ventana
    context, page, problems = open_ui(browser, app)
    sign_in(page, app)
    page.click("#identity-create")
    expect(page.locator("#identity-pub")).to_have_text(re.compile(r"^[0-9a-f]{64}$"))
    identity_pub = page.inner_text("#identity-pub").strip()
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo")
    uri = issue_uri(page)
    client = RelayClient(app.relay_url, parse_bunker_uri(uri, allow_insecure_relays=True).signer_pubkey)
    try:
        client.send("connect", ["", uri.split("secret=")[1]], scheme="nip04")
        approve_card(page, "connect").locator("button.ok").click()
        assert client.reply().result == "ack"

        client.send("sign_event", [login_template(identity_pub, now=int(time.time()), origin=ORIGIN)])  # 1) aprobacion a tiempo -> firma
        approve_card(page, "sign_event").locator("button.ok").click()
        assert client.reply().error is None
        expect(page.locator("#recent-list")).to_contain_text("Firmada correctamente")
        expect(page.locator("#banner")).to_contain_text("Firma realizada correctamente")
        expect(page.locator("#signer-signatures")).to_contain_text("1 (cada una aprobada por una persona)")

        client.send("sign_event", [login_template(identity_pub, now=int(time.time()), origin=ORIGIN, challenge="cd" * 32)])  # 2) aprobacion tardia
        late = approve_card(page, "sign_event")
        expect(late).to_contain_text("Plazo efectivo para firmar")  # B6.1D-R3: el plazo real (ventana de 5 s), no el TTL de la aprobacion (30 s)
        page.wait_for_timeout(5800)  # el operador tarda mas que SIGNER_WINDOW_S
        expect(late).to_contain_text("Ya no puede firmarse")
        expect(late.locator("button.ok")).to_have_text("Aprobar (ya no firmará)")
        late.locator("button.ok").click()  # SI aprueba...
        assert client.reply().error == "unauthorized"  # ...pero el servidor revalida y NO firma
        expect(page.locator("#banner")).to_contain_text("La firma NO se realizó: la política dejó de cumplirse")
        expect(page.locator("#banner")).not_to_contain_text("correctamente")
        expect(page.locator("#recent-list")).to_contain_text("Rechazada al firmar: la política dejó de cumplirse")
        expect(page.locator("#signer-signatures")).to_contain_text("1 (cada una aprobada por una persona)")  # el contador no avanzo: no hubo segunda firma
        audit = page.inner_text("#audit-body")
        assert "revalidation" in audit and audit.count("sign_ok") == 1
    finally:
        client.close()
    assert problems == [], problems
    context.close()


# ------------------------------------------------------------------------------------------------ B6.1D-R3: plazo EFECTIVO para firmar en la tarjeta
def sign_card(request_id: str, sign_left: int | None, approval_left: int, **over: Any) -> dict[str, Any]:
    return card(request_id, expires_in_s=approval_left, sign_expires_in_s=sign_left, checks=checks(), **over)


def test_card_shows_the_effective_signing_deadline_apart_from_the_approval_ttl(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    serve_cards(page, [sign_card("s1", 40, 100), sign_card("s2", 60, 5, id="s2")], [])
    sign_in(page, app)
    first, second = page.locator("[data-request-id=s1]"), page.locator("[data-request-id=s2]")
    expect(first).to_contain_text(re.compile(r"Plazo efectivo para firmar: (40|39|38) s"))
    expect(first).to_contain_text("Ventana de la política:")
    expect(first).to_contain_text(re.compile(r"La aprobación caduca en: (100|99|98) s"))
    expect(first).to_contain_text("el plazo efectivo lo marca la ventana de la política")  # 40 < 100: manda la ventana
    expect(second).to_contain_text(re.compile(r"Plazo efectivo para firmar: [45] s"))  # 5 < 60: manda la aprobacion
    expect(second).not_to_contain_text("el plazo efectivo lo marca la ventana")
    expect(page.locator("#approve-s1")).to_have_text("Aprobar")
    assert problems == []
    context.close()


def test_card_counts_down_and_says_clearly_when_it_can_no_longer_be_signed(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    approvals: list[str] = []
    t0 = time.monotonic()
    cards = [sign_card("late", 3, 100, id="late")]

    def evolve() -> None:  # el servidor real devuelve segundos restantes decrecientes
        gone = int(time.monotonic() - t0)
        cards[0]["sign_expires_in_s"], cards[0]["expires_in_s"] = max(0, 3 - gone), max(0, 100 - gone)

    serve_cards(page, cards, approvals, evolve)
    sign_in(page, app)
    late = page.locator("[data-request-id=late]")
    expect(late).to_contain_text(re.compile(r"Plazo efectivo para firmar: [123] s"))
    expect(late).to_contain_text("Ya no puede firmarse", timeout=9000)  # la cuenta local baja hasta cero entre sondeos
    expect(late).to_contain_text("el firmante NO firmará esta solicitud")
    expect(page.locator("#approve-late")).to_have_text("Aprobar (ya no firmará)")
    expect(page.locator("#approve-late")).to_be_enabled()  # el servidor es la autoridad: se puede aprobar y se vera «Rechazada al firmar»
    expect(page.locator("#deny-late")).to_be_enabled()
    assert problems == [] and approvals == []
    context.close()


def test_connect_cards_keep_the_plain_approval_countdown_and_expired_sign_window_is_shown_from_the_start(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    serve_cards(page, [card("k1", kind="connect", expires_in_s=90, summary={"nota": "-"}), sign_card("z0", 0, 50, id="z0")], [])
    sign_in(page, app)
    expect(page.locator("[data-request-id=k1]")).to_contain_text(re.compile(r"caduca en (90|89|88) s"))
    expect(page.locator("[data-request-id=k1]")).not_to_contain_text("Plazo efectivo")
    expect(page.locator("[data-request-id=z0]")).to_contain_text("Ya no puede firmarse")
    context.close()

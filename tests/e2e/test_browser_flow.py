"""E2E de NAVEGADOR REAL (Chrome/Edge vía Playwright) contra la aplicación completa (Uvicorn) y un relay local. Identidades ficticias.

Estas pruebas operan la INTERFAZ (clics y texto), no la API: no sustituyen a la autenticación real con Stacker News.
"""
import json
import re
import time
from collections.abc import Callable
from typing import Any

import pytest

from app.nostr.event import parse_and_verify_event
from app.nostr.keys import Keypair
from app.nostr.nip46 import parse_bunker_uri
from tests.e2e.conftest import ORIGIN, AppHandle, RelayClient
from tests.support import CHALLENGE, login_template

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect
pytestmark = pytest.mark.e2e
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def open_ui(browser: Any, app: AppHandle) -> tuple[Any, Any, list[str]]:
    context = browser.new_context(base_url=app.base)
    page = context.new_page()
    problems: list[str] = []
    page.on("pageerror", lambda exc: problems.append(f"pageerror: {exc}"))
    # Se ignoran los «Failed to load resource» (el navegador los registra por cada 401/400 esperado); se vigilan violaciones de CSP y errores de JS.
    page.on("console", lambda msg: problems.append(f"console.{msg.type}: {msg.text}")
            if msg.type in ("error", "warning") and not msg.text.startswith("Failed to load resource") else None)
    page.goto("/")
    return context, page, problems


def sign_in(page: Any, app: AppHandle) -> None:
    page.fill("#login-username", app.username)
    page.fill("#login-password", app.password)
    page.click("#login-btn")
    expect(page.locator("#view-app")).to_be_visible()


def issue_uri(page: Any) -> str:
    page.click("#bunker-issue")
    expect(page.locator("#bunker-box")).to_be_visible()
    return str(page.input_value("#bunker-uri"))


def approve_card(page: Any, kind: str) -> Any:
    card = page.locator(f"#pending-list .kind-{kind}")
    expect(card).to_have_count(1)
    return card


def test_login_cookie_flags_and_no_browser_storage(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    expect(page.locator("#view-login")).to_be_visible()
    expect(page.locator("#view-app")).to_be_hidden()
    page.fill("#login-username", app.username)
    page.fill("#login-password", "contrasena-incorrecta-123")
    page.click("#login-btn")
    expect(page.locator("#login-error")).to_be_visible()
    expect(page.locator("#view-app")).to_be_hidden()
    assert page.input_value("#login-password") == ""  # la contraseña se vacía siempre
    assert not [c for c in context.cookies() if c["name"] == "nip46_session"]

    sign_in(page, app)
    cookie = next(c for c in context.cookies() if c["name"] == "nip46_session")
    assert cookie["httpOnly"] is True and cookie["sameSite"] == "Strict" and cookie["path"] == "/api"
    assert page.evaluate("document.cookie") == ""  # el JS no puede leer el JWT
    assert page.evaluate("[localStorage.length, sessionStorage.length]") == [0, 0]
    assert cookie["value"] not in page.content() and app.password not in page.content() and page.input_value("#login-password") == ""
    page.reload()  # la sesión sobrevive a una recarga (cookie) sin guardar nada en el navegador
    expect(page.locator("#view-app")).to_be_visible()
    assert page.evaluate("[localStorage.length, sessionStorage.length]") == [0, 0]
    assert problems == []
    context.close()


def test_csrf_and_unauthenticated_access_from_the_page(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    unauth = page.evaluate("fetch('/api/status', {credentials: 'same-origin'}).then(r => r.status)")
    assert unauth == 401
    sign_in(page, app)
    # con la cookie pero sin la cabecera CSRF, una escritura se rechaza (lo que haría una página ajena)
    assert page.evaluate("fetch('/api/identity', {method: 'POST', credentials: 'same-origin'}).then(r => r.status)") == 403
    assert page.evaluate("fetch('/api/identity', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': 'x'}}).then(r => r.status)") == 403
    context.close()


def test_logout_revokes_the_session(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, _ = open_ui(browser, app)
    sign_in(page, app)
    old_cookie = next(c for c in context.cookies() if c["name"] == "nip46_session")["value"]
    page.click("#logout-btn")
    expect(page.locator("#view-login")).to_be_visible()
    expect(page.locator("#view-app")).to_be_hidden()
    assert page.evaluate("fetch('/api/status', {credentials: 'same-origin'}).then(r => r.status)") == 401
    # el token antiguo ya no sirve aunque se conserve (revocado en el servidor)
    stale = context.request.get(app.base + "/api/status", headers={"Authorization": f"Bearer {old_cookie}"})
    assert stale.status == 401
    context.close()


def test_session_expires_in_the_ui(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app(JWT_TTL_S="5")
    context, page, _ = open_ui(browser, app)
    sign_in(page, app)
    expect(page.locator("#session-timer")).to_contain_text("Sesión")
    expect(page.locator("#view-login")).to_be_visible(timeout=15000)  # el sondeo recibe 401 y la UI vuelve al inicio de sesión
    expect(page.locator("#banner")).to_contain_text("caducó")
    assert page.input_value("#bunker-uri") == ""
    context.close()


def test_import_identity_through_the_ui_never_echoes_the_secret(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    key = Keypair.generate()
    secret_hex = "ab" * 32
    expected = Keypair.from_hex(secret_hex).public_hex
    context, page, problems = open_ui(browser, app)
    sign_in(page, app)
    page.fill("#identity-secret", secret_hex)
    page.click("#identity-import")
    expect(page.locator("#identity-pub")).to_have_text(expected)
    assert page.input_value("#identity-secret") == "" and secret_hex not in page.content() and key.public_hex != expected
    page.fill("#identity-secret", "zz" * 32)  # inválida: error genérico, sin eco
    page.click("#identity-import")
    expect(page.locator("#banner")).to_contain_text("no es válida")
    assert "zz" * 32 not in page.content() and secret_hex not in app.log()
    assert problems == []
    context.close()


def test_full_remote_signing_flow_from_the_ui(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    sign_in(page, app)

    # 1) identidad y firmante
    expect(page.locator("#signer-start")).to_be_disabled()  # sin identidad no se puede iniciar
    page.click("#identity-create")
    expect(page.locator("#identity-pub")).to_have_text(HEX64)
    identity_pub = page.inner_text("#identity-pub").strip()
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo")
    expect(page.locator("#identity-create")).to_be_disabled()  # no se cambia la identidad con el firmante en marcha
    assert app.relay_url.split("//")[1].split(":")[0] in page.inner_text("#signer-relay")

    # 2) URI: se muestra una vez y se puede ocultar
    uri = issue_uri(page)
    parsed = parse_bunker_uri(uri, allow_insecure_relays=True)
    assert parsed.signer_pubkey != identity_pub and parsed.relays == (app.relay_url,)
    secret = uri.split("secret=")[1]
    page.click("#bunker-hide")
    expect(page.locator("#bunker-box")).to_be_hidden()
    assert page.input_value("#bunker-uri") == "" and secret not in page.content()

    client = RelayClient(app.relay_url, parsed.signer_pubkey)
    try:
        # 3) connect (NIP-04, como NDK) pendiente en la interfaz -> aprobar
        client.send("connect", ["", secret], scheme="nip04")
        card = approve_card(page, "connect")
        expect(card).to_contain_text("Conexión de un cliente")
        card.locator("button.ok").click()
        assert client.reply().result == "ack"
        expect(page.locator("#connections-list")).to_contain_text("active")
        assert client.call("get_public_key", []).result == identity_pub

        # 4) solicitudes inválidas: nunca llegan a la interfaz y se deniegan solas
        bad = client.call("sign_event", [login_template(identity_pub, now=int(time.time()), origin="https://evil.example")])
        assert bad.error == "unauthorized"
        assert client.call("sign_event", [login_template(identity_pub, now=int(time.time()), origin=ORIGIN, kind=1)]).error == "unauthorized"
        expect(page.locator("#pending-count")).to_have_text("0")

        # 5) sign_event válido: 11 comprobaciones en verde -> aprobar -> firma válida
        template = login_template(identity_pub, now=int(time.time()), origin=ORIGIN)
        client.send("sign_event", [template])
        card = approve_card(page, "sign_event")
        expect(card.locator("ul.checks li.pass")).to_have_count(11)
        expect(card.locator("ul.checks li.fail")).to_have_count(0)
        expect(card).to_contain_text(ORIGIN)
        assert CHALLENGE not in page.content()  # el reto completo no se muestra
        expect(card.locator("button.ok")).to_be_enabled()
        card.locator("button.ok").click()
        reply = client.reply()
        assert reply.error is None
        signed = parse_and_verify_event(json.loads(reply.result))
        original = json.loads(template)
        assert signed.pubkey == identity_pub and signed.kind == 27235 and signed.id == original["id"] and signed.content == original["content"]
        expect(page.locator("#signer-signatures")).to_contain_text("1 (cada una aprobada por una persona)")

        # 6) reutilizar el mismo reto se rechaza sin preguntar
        assert client.call("sign_event", [template]).error == "unauthorized"
        expect(page.locator("#pending-count")).to_have_text("0")

        # 7) rechazar desde la interfaz: otro cliente con otra URI
        second_uri = issue_uri(page)
        second = RelayClient(app.relay_url, parse_bunker_uri(second_uri, allow_insecure_relays=True).signer_pubkey)
        try:
            second.send("connect", ["", second_uri.split("secret=")[1]], scheme="nip04")
            card = approve_card(page, "connect")
            card.locator("button.danger").click()
            assert second.reply().error == "unauthorized"
            assert second.call("get_public_key", []).error == "unauthorized"
        finally:
            second.close()
        expect(page.locator("#recent-list")).to_contain_text("rechazada")
        expect(page.locator("#recent-list")).to_contain_text("aprobada")
    finally:
        client.close()

    # 8) auditoría sanitizada visible y sin secretos
    audit = page.inner_text("#audit-body")
    for expected in ("session_start", "relay_ready", "bunker_issued", "sign_ok", "decision", "policy"):
        assert expected in audit
    visible = page.content() + page.inner_text("body")
    for leaked in (secret, second_uri.split("secret=")[1], "nsec1", CHALLENGE):
        assert leaked not in visible and leaked not in app.log()
    assert not re.search(r"bunker://[0-9a-f]{64}", visible + app.log())  # el titulo de la UI dice «bunker://», pero ninguna URI real

    # 9) detener: cierre ordenado con evidencia
    page.click("#signer-stop")
    expect(page.locator("#signer-state")).to_have_text("Detenido")
    expect(page.locator("#audit-body")).to_contain_text("session_end")
    expect(page.locator("#signer-end")).to_contain_text("detenido por el operador")
    expect(page.locator("#bunker-issue")).to_be_disabled()
    assert problems == [], problems
    context.close()


def test_ui_restart_cycle_and_clean_state(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    """Detener y volver a iniciar en la misma ejecución: sesión nueva, sin secretos ni solicitudes heredados."""
    app = start_app()
    context, page, _ = open_ui(browser, app)
    sign_in(page, app)
    page.click("#identity-create")
    expect(page.locator("#identity-pub")).to_have_text(HEX64)
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo")
    first_uri = issue_uri(page)
    page.click("#signer-stop")
    expect(page.locator("#signer-state")).to_have_text("Detenido")
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo")
    expect(page.locator("#connections-empty")).to_be_visible()
    second_uri = issue_uri(page)
    assert parse_bunker_uri(first_uri, allow_insecure_relays=True).signer_pubkey != parse_bunker_uri(second_uri, allow_insecure_relays=True).signer_pubkey  # clave de transporte nueva por sesión
    context.close()


def pair_from_ui(page: Any, app: AppHandle) -> RelayClient:
    """Empareja un cliente de prueba con la aprobación humana del `connect` desde la interfaz."""
    uri = issue_uri(page)
    client = RelayClient(app.relay_url, parse_bunker_uri(uri, allow_insecure_relays=True).signer_pubkey)
    client.send("connect", ["", uri.split("secret=")[1]], scheme="nip04")
    approve_card(page, "connect").locator("button.ok").click()
    assert client.reply().result == "ack"
    page.click("#bunker-hide")
    return client


def test_the_revoke_button_revokes_a_single_connection_and_cancels_its_pending_signature(browser: Any, start_app: Callable[..., AppHandle]) -> None:
    app = start_app()
    context, page, problems = open_ui(browser, app)
    sign_in(page, app)
    page.click("#identity-create")
    expect(page.locator("#identity-pub")).to_have_text(HEX64)
    identity_pub = page.inner_text("#identity-pub").strip()
    page.click("#signer-start")
    expect(page.locator("#signer-state")).to_have_text("Listo")
    first, second = pair_from_ui(page, app), pair_from_ui(page, app)
    try:
        expect(page.locator("#connections-list .revoke-btn")).to_have_count(2)
        first8, second8 = first.ndk.key.public_hex[:8], second.ndk.key.public_hex[:8]

        # una firma pendiente de la primera conexión (la persona todavía no decide)
        first.send("sign_event", [login_template(identity_pub, now=int(time.time()), origin=ORIGIN)])
        card = approve_card(page, "sign_event")
        expect(card).to_be_visible()

        # revocar SOLO la primera desde la interfaz
        row = page.locator("#connections-list li", has_text=first8)
        row.locator(".revoke-btn").click()
        expect(page.locator("#connections-list li", has_text=first8)).to_contain_text("revoked")
        expect(page.locator("#connections-list li", has_text=first8).locator(".revoke-btn")).to_have_count(0)
        expect(page.locator("#connections-list li", has_text=second8).locator(".revoke-btn")).to_have_count(1)
        expect(page.locator("#pending-list .kind-sign_event")).to_have_count(0)  # su solicitud pendiente se canceló
        assert first.reply().error == "unauthorized"  # el cliente revocado recibe la denegación
        assert first.call("get_public_key", []).error == "unauthorized"  # y ya no puede pedir nada
        assert second.call("get_public_key", []).result == identity_pub  # la otra conexión sigue activa

        # la firma de la segunda sigue exigiendo la aprobación humana en la interfaz
        second.send("sign_event", [login_template(identity_pub, now=int(time.time()), origin=ORIGIN, challenge="cd" * 32)])
        assert second.silent(0.5)  # nada se firma solo
        card = approve_card(page, "sign_event")
        card.locator("button.ok").click()
        assert second.reply().error is None
        expect(page.locator("#audit-body")).to_contain_text("connection_revoked")
        visible = page.content() + page.inner_text("body") + app.log()
        assert first.ndk.key.public_hex not in visible and second.ndk.key.public_hex not in visible  # solo prefijos de 8 caracteres
    finally:
        first.close()
        second.close()
    assert problems == [], problems
    context.close()

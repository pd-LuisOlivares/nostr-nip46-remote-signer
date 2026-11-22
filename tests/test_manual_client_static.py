"""B6.1D-R3: reglas ESTATICAS del cliente web de laboratorio (se ejecutan siempre, sin Docker): separacion del producto, ausencia de aprobaciones y de almacenamiento."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "lab" / "manual" / "client_web"
FILES = {name: (WEB / name).read_text(encoding="utf-8") for name in ("server.mjs", "verify.mjs", "app.js", "index.html", "app.css")}


def test_the_client_has_no_way_to_approve_or_to_reach_the_signer_api():
    code = "\n".join(FILES[n] for n in ("server.mjs", "verify.mjs", "app.js"))
    for forbidden in ("/approve", "/deny", "/api/requests", "/api/identity", "/api/signer", "/api/auth", ":8000", ":18000", "nip46_session", "X-CSRF-Token", "ADMIN_PASSWORD"):
        assert forbidden not in code, forbidden
    # el HTML solo MENCIONA, como texto para la persona, la direccion del firmante (no hay enlaces ni formularios hacia el)
    assert re.findall(r'href="([^"]+)"', FILES["index.html"]) == ["/app.css"] and "action=" not in FILES["index.html"]  # solo la hoja de estilos propia
    routes = re.findall(r"path === '(/api/[a-z/]+)'", FILES["server.mjs"])
    assert sorted(set(routes)) == ["/api/op", "/api/session", "/api/state"]  # unicas rutas de la API: nada de aprobar


def test_the_web_page_has_no_unsafe_patterns_and_no_browser_storage():
    js, html = FILES["app.js"], FILES["index.html"]
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "localStorage", "sessionStorage", "indexedDB", "document.cookie",
                      "location.search", "location.hash", "history.pushState"):
        assert forbidden not in js, forbidden
    assert not re.search(r"<script(?![^>]*src=)", html) and not re.search(r"\son[a-z]+\s*=|style\s*=|javascript:", html, re.IGNORECASE)
    assert not re.search(r"https?://", html.replace("http://127.0.0.1:18000", "") + js + FILES["app.css"])  # sin recursos externos (solo la direccion local escrita como texto)
    assert 'type="password"' in html and 'autocomplete="off"' in html  # la URI se escribe en un campo oculto
    assert "credentials: 'omit'" in js


def test_the_server_restricts_relays_hosts_origins_and_never_logs_secrets():
    server = FILES["server.mjs"]
    assert "LOCAL_RELAY_HOSTS = new Set(['relay', 'localhost', '127.0.0.1', '[::1]'])" in server and "ru.protocol !== 'ws:'" in server
    for needed in ("ALLOWED_HOSTS", "Origen no permitido", "x-lab-client", "x-lab-token", "timingSafeEqual", "Content-Security-Policy", "frame-ancestors 'none'", "MAX_BODY"):
        assert needed in server, needed
    assert "Access-Control" not in server  # sin CORS: otra pagina no puede leer ni usar el servicio
    assert not re.search(r"console\.(log|error|warn)\((?!JSON\.stringify)", server)  # todo registro pasa por log() que redacta URI, secreto y hex de 64
    assert "clean = " in server and "bunker:\\/\\/" in server
    for forbidden in ("writeFile", "appendFile", "createWriteStream", "localStorage"):
        assert forbidden not in server  # nada se guarda en disco


def test_the_client_uses_the_real_ndk_and_never_fabricates_signer_responses():
    server = FILES["server.mjs"]
    assert "from '@nostr-dev-kit/ndk'" in server and "NDKNip46Signer" in server and "rpc.sendRequest" in server and "blockUntilReady" in server
    assert "verifySignedResponse" in server
    assert not re.search(r"result:\s*['\"]ack['\"]|result:\s*['\"]pong['\"]|state:\s*'signed'", server)  # nada se da por exitoso sin comprobar
    assert re.search(r"finish\(op, 'signed'", server) and "if (v.ok && expectValid)" in server  # 'signed' SOLO tras verificar


def test_the_lab_client_is_not_part_of_the_product_image_or_default_compose():
    for name in ("Dockerfile", "compose.yaml", ".dockerignore"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "client_web" not in text and "client-web" not in text and "18080" not in text, name
    assert "lab/" in (ROOT / ".dockerignore").read_text(encoding="utf-8") or "COPY app" in (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert not re.search(r"COPY\s+(lab|\.)\b", dockerfile.replace("COPY app ./app", ""))  # solo se copia app/


def test_the_manual_compose_publishes_only_on_loopback_and_separates_the_networks():
    text = (ROOT / "lab" / "manual" / "compose.manual.yaml").read_text(encoding="utf-8")
    ports = re.findall(r'ports:\s*\["([^"]+)"\]', text)
    assert len(ports) == 2 and all(p.startswith("127.0.0.1:") for p in ports)
    assert "signer_net" in text and "client_net" in text
    client = text[text.index("  client-web:"):]
    assert "client_net" in client and "signer_net" not in client  # el cliente NO esta en la red del firmante
    app = text[text.index("  app:"):text.index("  # Cliente web")]
    assert "signer_net" in app and "client_net" not in app
    assert "read_only: true" in text and "cap_drop: [ALL]" in text and ":ro" in client
    assert "SIGNER_WINDOW_S: \"${MANUAL_SIGNER_WINDOW_S:-45}\"" in text and "APPROVAL_TTL_S: \"${MANUAL_APPROVAL_TTL_S:-120}\"" in text
    assert "wss://" not in text and "primal" not in text and "stacker.news" not in text.replace("sn.manual.invalid", "")


def test_local_client_script_is_kept_as_a_technical_tool_and_is_loopback_only():
    script = (ROOT / "lab" / "manual" / "local_client.py").read_text(encoding="utf-8")
    assert "LOOPBACK" in script and "solo se conecta a un relay local" in script and "getpass" in script

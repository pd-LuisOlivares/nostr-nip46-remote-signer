"""Reglas de arquitectura y portabilidad comprobables: el núcleo no depende de FastAPI ni del laboratorio, y no hay rutas personales."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
NOSTR = APP / "nostr"
PERSONAL_PATHS = re.compile(r"[A-Za-z]:\\Users\\|/Users/[A-Za-z]|/home/[a-z]|C:/Users/", re.IGNORECASE)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_the_core_package_exists_with_the_expected_modules():
    assert sorted(p.name for p in NOSTR.glob("*.py")) == ["__init__.py", "errors.py", "event.py", "keys.py", "nip04.py", "nip44.py", "nip46.py", "relay.py"]


def test_the_nostr_core_does_not_import_fastapi_starlette_or_the_http_layer():
    for path in NOSTR.glob("*.py"):
        for module in imported_modules(path):
            root = module.split(".")[0]
            assert root not in {"fastapi", "starlette", "uvicorn", "httpx"}, f"{path.name} importa {module}"
            assert module not in {"app.api", "app.main", "app.schemas"} and not module.startswith(("app.api.", "app.schemas.")), f"{path.name} importa {module}"


def test_the_core_does_not_import_the_configuration_layer():
    for path in NOSTR.glob("*.py"):
        assert not any(m == "app.config" for m in imported_modules(path)), path.name


def test_app_never_imports_from_the_laboratory():
    for path in APP.rglob("*.py"):
        for module in imported_modules(path):
            assert module.split(".")[0] not in {"lab", "lab_common", "lab_real", "lab_relay", "lab_signer"}, f"{path} importa {module}"


def test_network_io_is_confined_to_the_relay_transport():
    """B2-1: relay.py es el UNICO modulo del producto que hace E/S de red; el resto del nucleo y los servicios no."""
    forbidden = {"socket", "ssl", "urllib.request", "http", "http.client", "websockets", "subprocess", "requests", "aiohttp"}
    for path in NOSTR.glob("*.py"):
        mods = imported_modules(path)
        if path.name == "relay.py":
            assert {"asyncio", "ssl"} <= mods and any(m.startswith("websockets") for m in mods)
            continue
        assert not (mods & forbidden) and "asyncio" not in mods, path.name
        text = path.read_text(encoding="utf-8")
        assert "open(" not in text and "os.environ" not in text and "getenv" not in text, path.name
    for path in (APP / "services").glob("*.py"):
        mods = imported_modules(path)
        assert not any(m.split(".")[0] in {x.split(".")[0] for x in forbidden} for m in mods), path.name
        assert not any(m.split(".")[0] in {"fastapi", "starlette", "uvicorn"} for m in mods), path.name
        text = path.read_text(encoding="utf-8")
        assert "open(" not in text and "os.environ" not in text and "getenv" not in text, path.name


def test_the_api_layer_does_not_do_network_io_and_services_do_not_import_the_api():
    for path in (APP / "api").glob("*.py"):
        assert not (imported_modules(path) & {"socket", "ssl", "websockets", "subprocess"}), path.name
    for path in (APP / "services").glob("*.py"):
        assert not any(m.startswith(("app.api", "app.main")) for m in imported_modules(path)), path.name


def test_no_private_key_is_persisted_by_the_application():
    """D-3: la clave Nostr solo vive en memoria. D-9: SQLite existe SOLO para la cuenta del administrador y SOLO en app/storage/."""
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\.write_text\(|\.write_bytes\(|open\([^)]*[\"']w", text), path.name
        if path.parent.name != "storage":
            assert "sqlite3" not in text, f"{path.name}: sqlite3 solo se admite en app/storage/"
            assert not re.search(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM|CREATE TABLE)\b.*\b(FROM|INTO|SET|WHERE|VALUES|\()", text), f"{path.name}: SQL fuera de app/storage/"


def test_the_storage_layer_has_no_access_to_nostr_keys_tokens_or_the_http_layer():
    storage = APP / "storage"
    assert sorted(p.name for p in storage.glob("*.py")) == ["__init__.py", "admins.py", "database.py", "secret_file.py"]
    for path in storage.glob("*.py"):
        for module in imported_modules(path):
            assert not module.startswith(("app.nostr", "app.api", "app.main", "app.schemas", "app.services", "app.security", "fastapi", "starlette", "jwt")), f"{path.name} importa {module}"


def test_passwords_are_only_hashed_with_argon2id_never_with_a_plain_digest():
    text = (APP / "security" / "passwords.py").read_text(encoding="utf-8")
    assert "argon2" in text and "RFC_9106_LOW_MEMORY" in text
    for forbidden in ("hashlib", "md5", "sha1", "sha256", "base64", "Fernet", "AES"):
        assert forbidden not in text, forbidden
    accounts = (APP / "services" / "admin_accounts.py").read_text(encoding="utf-8")
    assert "hashlib" not in accounts and "PasswordService" in accounts  # el servicio de cuentas solo delega en PasswordService


def test_no_personal_paths_or_addresses_in_versioned_sources():
    files = [*APP.rglob("*.py"), *(ROOT / "tests").rglob("*.py"), ROOT / "README.md", ROOT / "Dockerfile", ROOT / "compose.yaml", ROOT / ".env.example",
             ROOT / "pyproject.toml", ROOT / "constraints.txt"]
    for path in files:
        if path == Path(__file__):   # este archivo contiene los patrones buscados
            continue
        assert not PERSONAL_PATHS.search(path.read_text(encoding="utf-8")), path.name
    for path in (ROOT / "compose.yaml", ROOT / ".env.example"):
        assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", path.read_text(encoding="utf-8").replace("127.0.0.1", "").replace("0.0.0.0", "")), path.name


def test_compose_publishes_only_on_loopback():
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    ports = re.findall(r'-\s*"([^"]*:\d+)"', text)
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)


def test_dependencies_are_pinned_and_present_in_constraints():
    pinned = {name.lower(): version for name, version in (line.split("==") for line in (ROOT / "constraints.txt").read_text(encoding="utf-8").split("\n")
                                                          if line and not line.startswith("#"))}
    for name, version in (("pyjwt", "2.15.1"), ("coincurve", "21.0.0"), ("cryptography", "50.0.2"), ("websockets", "17.4"), ("cffi", "2.1.1"), ("pycparser", "3.12"),
                          ("argon2-cffi", "25.1.0"), ("argon2-cffi-bindings", "26.2.0")):
        assert pinned[name] == version
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for dep in ("coincurve==21.0.0", "cryptography==50.0.2", "websockets==17.4", "argon2-cffi==25.1.0"):
        assert f'"{dep}"' in project


def test_the_security_package_is_independent_of_the_http_layer():
    for path in (APP / "security").glob("*.py"):
        assert not any(m.split(".")[0] in {"fastapi", "starlette"} or m.startswith(("app.api", "app.main")) for m in imported_modules(path)), path.name


def test_jwt_is_pinned_to_one_algorithm_and_never_accepts_none():
    text = (APP / "security" / "operator_auth.py").read_text(encoding="utf-8")
    assert 'ALGORITHM: Final = "HS256"' in text and "algorithms=[ALGORITHM]" in text and "verify_signature" in text
    assert "none" not in re.findall(r"algorithms=\[[^\]]*\]", text)[0].lower()


def test_the_web_ui_has_no_unsafe_patterns_and_no_browser_storage():
    static = APP / "static"
    assert {p.name for p in static.iterdir()} >= {"index.html", "app.js", "app.css"}
    js = (static / "app.js").read_text(encoding="utf-8")
    html = (static / "index.html").read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "localStorage", "sessionStorage",
                      "indexedDB", "document.cookie"):
        assert forbidden not in js, forbidden
    assert not re.search(r"<script(?![^>]*src=)", html) and not re.search(r"\son[a-z]+\s*=|style\s*=|javascript:", html, re.IGNORECASE)
    assert not re.search(r"https?://", html + js + (static / "app.css").read_text(encoding="utf-8"))

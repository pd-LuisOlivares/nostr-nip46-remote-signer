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
    assert sorted(p.name for p in NOSTR.glob("*.py")) == ["__init__.py", "errors.py", "event.py", "keys.py", "nip04.py", "nip44.py", "nip46.py"]


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


def test_no_network_or_filesystem_io_in_the_core():
    forbidden = {"socket", "ssl", "urllib.request", "http", "http.client", "websockets", "asyncio", "subprocess", "requests", "aiohttp"}
    for path in NOSTR.glob("*.py"):
        assert not (imported_modules(path) & forbidden), path.name
        text = path.read_text(encoding="utf-8")
        assert "open(" not in text and "os.environ" not in text and "getenv" not in text, path.name


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
    for name, version in (("coincurve", "21.0.0"), ("cryptography", "50.0.2"), ("websockets", "17.4"), ("cffi", "2.1.1"), ("pycparser", "3.12")):
        assert pinned[name] == version
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for dep in ("coincurve==21.0.0", "cryptography==50.0.2", "websockets==17.4"):
        assert f'"{dep}"' in project

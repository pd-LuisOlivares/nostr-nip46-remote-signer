"""D-16: el perfil `deploy/b62.env` sobre el `compose.yaml` REAL, con la importacion de una base SQLite y comprobaciones DENTRO del contenedor.

Se activa con E2E_DOCKER=1. NO construye ni descarga nada: usa una imagen que ya exista en local (por defecto `nostr-nip46-remote-signer:dev`, o la de
`B62_TEST_IMAGE`) con `--no-build --pull never`; si no existe, se omite. Proyecto y volumen PROPIOS y efimeros (`nip46-b62t-*`): no toca la demostracion B6.1D,
el proyecto por defecto, `data/b62.db` ni ningun `.env`. Base y contrasena FICTICIAS (de esta ejecucion). Sin relay ni servicios externos: el firmante nunca se inicia.
NO es una autenticacion con Stacker News.
"""
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.security.passwords import PasswordService
from app.services.admin_accounts import AdminAccounts, BootstrapResult
from app.storage.admins import AdminRepository
from app.storage.database import Database
from tests.e2e.conftest import ROOT, free_port, wait_http

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("E2E_DOCKER") != "1", reason="defina E2E_DOCKER=1 para ejecutar las pruebas de Docker")]
IMAGE = os.environ.get("B62_TEST_IMAGE", "nostr-nip46-remote-signer:dev")
PROFILE = ROOT / "deploy" / "b62.env"
TOOL = ROOT / "deploy" / "import_admin_db.py"
USER = "admin-ficticio-b62"

_PROC_NET_SCRIPT = (
    "import json\n"
    "LOOPBACK = ('0100007F', '00000000000000000000000001000000', '0000000000000000FFFF00000100007F')\n"
    "out = []\n"
    "for name in ('/proc/net/tcp', '/proc/net/tcp6'):\n"
    "    for line in open(name).read().splitlines()[1:]:\n"
    "        f = line.split()\n"
    "        local_port, remote, state = int(f[1].split(':')[1], 16), f[2].split(':')[0], f[3]\n"
    "        if state == '01' and local_port != 8000 and remote not in LOOPBACK:\n"
    "            out.append([name, remote])\n"
    "print(json.dumps(out))"
)
_EFFECTIVE_SCRIPT = (
    "import json, os\n"
    "from app.config import Settings\n"
    "c = Settings.from_env(os.environ)\n"
    "st = dict(l.split(':', 1) for l in open('/proc/self/status').read().splitlines() if ':' in l)\n"
    "print(json.dumps({'relay_url': c.relay_url, 'tls': c.relay_tls_groups, 'insecure': c.relay_allow_insecure, 'origin': c.service_origin, 'window': c.window_s,\n"
    "  'secret_ttl': c.secret_ttl_s, 'approval': c.approval_ttl_s, 'sigs': c.max_signatures, 'requests': c.max_requests, 'pending': c.max_pending,\n"
    "  'session': c.session_ttl_s, 'connection': c.connection_ttl_s, 'jwt': c.jwt_ttl_s, 'cookie_secure': c.cookie_secure, 'hosts': list(c.allowed_hosts),\n"
    "  'db': c.database_path, 'has_password': bool(c.admin_password or c.admin_password_file), 'uid': os.getuid(), 'cap_eff': st['CapEff'].strip(),\n"
    "  'no_new_privs': st['NoNewPrivs'].strip(), 'env_has_insecure': 'RELAY_ALLOW_INSECURE' in os.environ}))"
)


class Stack:
    def __init__(self, project: str) -> None:
        self.project, self.port = project, free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.volume = f"{project}_app_data"

    def dc(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("ADMIN_") and k not in ("RELAY_URL", "RELAY_ALLOW_INSECURE", "ALLOWED_HOSTS")}
        env.update(APP_PORT=str(self.port), APP_IMAGE=IMAGE)  # el entorno del proceso prevalece sobre --env-file: solo cambian el puerto libre y la imagen local
        return subprocess.run(["docker", "compose", "--env-file", str(PROFILE), "-p", self.project, "-f", str(ROOT / "compose.yaml"), *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=timeout, check=False)

    def login(self, username: str, password: str) -> int:
        body = json.dumps({"username": username, "password": password}).encode()
        req = urllib.request.Request(self.base + "/api/auth/login", data=body, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return int(resp.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)

    def logs(self) -> str:
        return self.dc("logs", "--no-color", "--no-log-prefix", "app").stdout

    def inside(self, code: str) -> str:
        done = self.dc("exec", "-T", "app", "python", "-c", code)
        assert done.returncode == 0, done.stderr[-300:]
        return done.stdout.strip()

    def import_db(self, source: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-I", str(TOOL), "--source", str(source), "--volume", self.volume, "--image", IMAGE],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, check=False)


@pytest.fixture
def stack() -> Iterator[Stack]:
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=60, check=False).returncode != 0:
        pytest.skip(f"la imagen local {IMAGE} no existe (esta prueba no construye ni descarga nada)")
    s = Stack(f"nip46-b62t-{secrets.token_hex(3)}")
    try:
        yield s
    finally:
        s.dc("down", "-v", "--remove-orphans", timeout=120)  # solo el proyecto efimero propio


def make_toy_db(path: Path, password: str) -> None:
    assert AdminAccounts(Database(str(path)), AdminRepository(Database(str(path))), PasswordService()).prepare(USER, lambda: password) is BootstrapResult.CREATED


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_b62_profile_runs_with_an_imported_database_without_external_connections(stack: Stack, tmp_path: Path) -> None:
    password = secrets.token_urlsafe(24)  # ficticia, de esta ejecucion
    source = tmp_path / "origen.db"
    make_toy_db(source, password)
    original = sha256(source)

    # 1) `create` deja volumen, red y contenedor listos SIN iniciar nada; el contenedor aun no esta en marcha
    created = stack.dc("create", "--no-build", "--pull", "never")
    assert created.returncode == 0, created.stderr[-500:]
    assert subprocess.run(["docker", "volume", "inspect", stack.volume], capture_output=True, timeout=60, check=False).returncode == 0
    assert stack.dc("ps", "-q", "--status", "running").stdout.strip() == ""

    # 2) importacion: el origen queda intacto, el destino es del uid 10001 con modo 0600 y /data 0700 (comprobado dentro del contenedor auxiliar)
    done = stack.import_db(source)
    assert done.returncode == 0, done.stderr[-500:]
    facts = json.loads(done.stdout)
    assert facts["ok"] is True and facts["integrity"] == "ok" and facts["admins"] == [1, 1] and facts["source_sha256_unchanged"] is True
    assert (facts["uid"], facts["mode"], facts["dir_uid"], facts["dir_mode"], facts["whoami"]) == (10001, "0o600", 10001, "0o700", 10001) and facts["leftovers"] == []
    assert sha256(source) == original
    assert password not in done.stdout and password not in done.stderr and "$argon2" not in done.stdout

    # 3) una segunda importacion NO sobrescribe: se rechaza y el destino sigue siendo el mismo
    again = stack.import_db(source)
    assert again.returncode == 1 and "destination_exists" in again.stderr and "no se modifico" in again.stderr
    assert sha256(source) == original

    # 4) arranque del producto SIN contrasena inicial: la cuenta importada ya inicia sesion, y el registro dice `exists` (nunca `created`)
    up = stack.dc("up", "-d", "--no-build", "--pull", "never")
    assert up.returncode == 0, up.stderr[-500:]
    wait_http(stack.base + "/health", timeout=90)
    assert stack.login(USER, password) == 200 and stack.login(USER, "incorrecta-" + password) == 401
    logs = stack.logs()
    assert "event=admin_bootstrap result=exists" in logs and "result=created" not in logs
    assert password not in logs and "$argon2" not in logs

    # 5) valores efectivos DENTRO del contenedor: los del perfil, usuario sin privilegios, sin capacidades y sin la llave del relay inseguro
    eff = json.loads(stack.inside(_EFFECTIVE_SCRIPT))
    assert eff == {"relay_url": "wss://relay.primal.net", "tls": "X25519", "insecure": False, "origin": "https://stacker.news", "window": 120, "secret_ttl": 600,
                   "approval": 120, "sigs": 1, "requests": 30, "pending": 16, "session": 720, "connection": 720, "jwt": 900, "cookie_secure": False,
                   "hosts": ["127.0.0.1", "localhost", "[::1]"], "db": "/data/nip46.db", "has_password": False, "uid": 10001,
                   "cap_eff": "0000000000000000", "no_new_privs": "1", "env_has_insecure": False}

    # 6) sin conexiones externas mientras no se inicie el firmante: ni sockets salientes ni eventos del relay
    time.sleep(1)
    assert json.loads(stack.inside(_PROC_NET_SCRIPT)) == []
    final = stack.logs()
    for event in ("relay_ready", "bunker_issued", "session_start", "relay_connect", "sign_ok"):
        assert event not in final, event

    # 7) el puerto se publica solo en loopback
    published = subprocess.run(["docker", "compose", "--env-file", str(PROFILE), "-p", stack.project, "-f", str(ROOT / "compose.yaml"), "port", "app", "8000"],
                               capture_output=True, text=True, timeout=60, check=False, env={**os.environ, "APP_PORT": str(stack.port), "APP_IMAGE": IMAGE}).stdout.strip()
    assert published == f"127.0.0.1:{stack.port}"

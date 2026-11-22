"""Docker Compose REAL del producto (`compose.yaml`): SQLite persistente en el volumen /data, administrador inicial, usuario no root y raíz de solo lectura.

Se activa con E2E_DOCKER=1 (construye la imagen del repositorio). Usa un proyecto y una imagen PROPIOS (`nip46-b61a-test`, etiqueta `b61a-test`) y un archivo
de entorno vacío (`--env-file`) para no tocar la imagen `:dev`, el proyecto por defecto ni ningún `.env` local. Credenciales FICTICIAS y aleatorias.
Sin relay ni servicios externos: el firmante nunca se inicia. NO es una autenticación con Stacker News.
"""
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.conftest import ROOT, free_port, wait_http

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("E2E_DOCKER") != "1", reason="defina E2E_DOCKER=1 para ejecutar las pruebas de Docker")]
IMAGE = "nostr-nip46-remote-signer:b61a-test"
USER = "docker-operador"


class Stack:
    def __init__(self, project: str, tmp_path: Path) -> None:
        self.project, self.port = project, free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.empty_env = tmp_path / "vacio.env"
        self.empty_env.write_text("", encoding="utf-8")

    def dc(self, *args: str, env: dict[str, str] | None = None, timeout: int = 400) -> subprocess.CompletedProcess[str]:
        full = {**os.environ, "APP_PORT": str(self.port), "APP_IMAGE": IMAGE, "ADMIN_USERNAME": "", "ADMIN_PASSWORD": "", **(env or {})}
        return subprocess.run(["docker", "compose", "--env-file", str(self.empty_env), "-p", self.project, "-f", str(ROOT / "compose.yaml"), *args],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=full, timeout=timeout)

    def login(self, username: str, password: str) -> int:
        body = json.dumps({"username": username, "password": password}).encode()
        req = urllib.request.Request(self.base + "/api/auth/login", data=body, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return int(resp.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)

    def logs(self) -> str:
        return self.dc("logs", "--no-color", "--no-log-prefix", "app").stdout

    def inside(self, code: str) -> str:
        done = self.dc("exec", "-T", "app", "python", "-c", code)
        assert done.returncode == 0, done.stderr[-300:]
        return done.stdout.strip()


@pytest.fixture
def stack(tmp_path: Path) -> Iterator[Stack]:
    if shutil.which("docker") is None:
        pytest.skip("docker no disponible")
    s = Stack(f"nip46-b61a-{secrets.token_hex(3)}", tmp_path)
    try:
        yield s
    finally:
        s.dc("down", "-v", "--remove-orphans", timeout=120)
        subprocess.run(["docker", "image", "rm", "-f", IMAGE], capture_output=True, timeout=60)


def test_admin_and_sqlite_persist_across_restart_recreate_and_without_the_initial_password(stack: Stack) -> None:
    password = secrets.token_urlsafe(24)  # ficticia, de esta ejecucion
    up = stack.dc("up", "--build", "-d", env={"ADMIN_USERNAME": USER, "ADMIN_PASSWORD": password})
    assert up.returncode == 0, up.stderr[-500:]
    wait_http(stack.base + "/health", timeout=90)

    # 1) primer arranque: el administrador creado desde el entorno ya puede iniciar sesion; los errores no distinguen cuentas
    assert stack.login(USER, password) == 200 and stack.login(USER, "incorrecta-" + password) == 401 and stack.login("otro-usuario", password) == 401
    first_logs = stack.logs()  # el registro es POR CONTENEDOR: el evento de creacion solo esta en el primero
    assert "event=admin_bootstrap result=created" in first_logs and "event=login_ok" in first_logs and "event=login_failed" in first_logs
    assert password not in first_logs and "$argon2" not in first_logs

    # 2) reinicio del contenedor: la base persiste en el volumen
    assert stack.dc("restart", "app", env={"ADMIN_USERNAME": USER, "ADMIN_PASSWORD": password}).returncode == 0
    wait_http(stack.base + "/health", timeout=60)
    assert stack.login(USER, password) == 200

    # 3) `down` (sin -v) y `up` SIN contrasena inicial ni usuario en el entorno: la cuenta sigue ahi, intacta
    assert stack.dc("down").returncode == 0
    assert stack.dc("up", "-d").returncode == 0  # sin --build: misma imagen
    wait_http(stack.base + "/health", timeout=60)
    assert stack.login(USER, password) == 200

    # 4) una contrasena distinta en el entorno NO sobrescribe la guardada
    other = secrets.token_urlsafe(24)
    assert stack.dc("up", "-d", "--force-recreate", env={"ADMIN_USERNAME": "otro", "ADMIN_PASSWORD": other}).returncode == 0
    wait_http(stack.base + "/health", timeout=60)
    assert stack.login(USER, password) == 200 and stack.login(USER, other) == 401 and stack.login("otro", other) == 401

    # 5) la base: solo el hash Argon2id, archivo y volumen del usuario sin privilegios, sin la contrasena en claro
    facts = json.loads(stack.inside(
        "import json, os, sqlite3\n"
        "p = '/data/nip46.db'\n"
        "con = sqlite3.connect(p)\n"
        "h = con.execute('SELECT password_hash FROM admins').fetchone()[0]\n"
        "n = con.execute('SELECT COUNT(*) FROM admins').fetchone()[0]\n"
        "raw = open(p, 'rb').read()\n"
        f"print(json.dumps({{'hash_ok': h.startswith('$argon2id$v=19$m=65536,t=3,p=4$'), 'admins': n, 'plain': {password!r}.encode() in raw, 'uid': os.stat(p).st_uid, "
        "'mode': oct(os.stat(p).st_mode & 0o777), 'dir_uid': os.stat('/data').st_uid, 'whoami': os.getuid()}))"))
    assert facts["hash_ok"] and facts["admins"] == 1 and facts["plain"] is False
    assert facts["uid"] == 10001 and facts["dir_uid"] == 10001 and facts["whoami"] == 10001 and facts["mode"] == "0o600"

    # 6) raiz de solo lectura: solo /data es escribible
    writes = json.loads(stack.inside(
        "import json\n"
        "def can(path):\n"
        "    try:\n"
        "        open(path, 'w').close()\n"
        "        return True\n"
        "    except OSError:\n"
        "        return False\n"
        "print(json.dumps({'app': can('/app/x'), 'root': can('/x'), 'tmp': can('/tmp/x'), 'data': can('/data/prueba')}))"))
    assert writes == {"app": False, "root": False, "tmp": False, "data": True}

    # 7) la imagen no contiene credenciales y los registros no contienen contrasenas ni hashes
    config = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{json .Config.Env}}"], capture_output=True, text=True, timeout=60).stdout
    assert password not in config and other not in config and "ADMIN_PASSWORD" not in config
    logs = stack.logs()
    assert password not in logs and other not in logs and "$argon2" not in logs
    assert "event=admin_bootstrap result=exists" in logs and "event=admin_bootstrap result=created" not in logs  # el contenedor actual solo encontro la cuenta
    assert "event=login_ok" in logs and "event=login_failed" in logs


def test_a_new_install_without_an_initial_password_stops_with_instructions_and_creates_no_account(stack: Stack) -> None:
    assert stack.dc("up", "--build", "-d").returncode == 0
    logs = ""
    for _ in range(40):
        logs = stack.logs()
        if "ADMIN_PASSWORD" in logs:
            break
        time.sleep(1)
    assert "ADMIN_PASSWORD" in logs and "ADMIN_PASSWORD_FILE" in logs and "README" in logs and "[arranque]" in logs
    with pytest.raises(TimeoutError):
        wait_http(stack.base + "/health", timeout=3)  # el servidor nunca queda a la escucha sin administrador

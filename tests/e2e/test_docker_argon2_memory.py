"""P-41: Argon2id (RFC 9106 «low memory»: 64 MiB por verificación) dentro del contenedor REAL del producto con un límite de memoria y SIN swap.

Se activa con E2E_DOCKER=1 y requiere la imagen `nostr-nip46-remote-signer:dev` (`docker compose build`). Credenciales FICTICIAS y aleatorias; sin servicios
externos (el firmante nunca se inicia). El limitador permite hasta 5 verificaciones en vuelo, así que el peor caso es una ráfaga de 5 (5 x 64 MiB mas la base de
Python y FastAPI). Antes de B6.1C (sin compuerta) la rafaga de 5 provocaba OOM-kill (exit 137) con 256 a 352 MiB; ahora `VerificationGate` limita a UNA verificacion activa por
proceso y estas pruebas pasan desde 128 MiB (Docker Desktop, cgroup v2, Python 3.12.16). Los parametros de Argon2id no se cambiaron.
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
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.e2e.conftest import free_port, wait_http

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get("E2E_DOCKER") != "1", reason="defina E2E_DOCKER=1 para ejecutar las pruebas de Docker")]
IMAGE = "nostr-nip46-remote-signer:dev"
USER = "p41-operador"


def docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def login(base: str, password: str) -> str:
    body = json.dumps({"username": USER, "password": password}).encode()
    req = urllib.request.Request(base + "/api/auth/login", data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except (urllib.error.URLError, ConnectionError, OSError) as exc:  # el contenedor murio a mitad de la peticion
        return type(exc).__name__


class Limited:
    def __init__(self, memory: str) -> None:
        self.name, self.port, self.password = f"nip46-p41-{secrets.token_hex(3)}", free_port(), secrets.token_urlsafe(24)
        self.memory, self.base = memory, ""

    def start(self) -> None:
        self.base = f"http://127.0.0.1:{self.port}"
        run = docker("run", "-d", "--name", self.name, "--memory", self.memory, "--memory-swap", self.memory, "--read-only", "--cap-drop", "ALL",
                     "--security-opt", "no-new-privileges:true", "-p", f"127.0.0.1:{self.port}:8000", "-e", f"ADMIN_USERNAME={USER}",
                     "-e", f"ADMIN_PASSWORD={self.password}", IMAGE)
        assert run.returncode == 0, run.stderr[-300:]
        wait_http(self.base + "/health", timeout=60)  # incluye el hash Argon2id de la creacion del administrador (64 MiB)

    def state(self) -> str:
        time.sleep(1)
        return docker("inspect", self.name, "--format", "{{.State.Status}} oom={{.State.OOMKilled}} exit={{.State.ExitCode}}").stdout.strip()

    def burst(self, size: int) -> set[str]:
        with ThreadPoolExecutor(size) as pool:
            return set(pool.map(lambda _i: login(self.base, "incorrecta-" + self.password), range(size)))


@pytest.fixture
def limited() -> Iterator[type[Limited]]:
    if shutil.which("docker") is None or docker("image", "inspect", IMAGE).returncode != 0:
        pytest.skip("docker o la imagen nostr-nip46-remote-signer:dev no disponibles (docker compose build)")
    created: list[Limited] = []

    class Tracked(Limited):
        def __init__(self, memory: str) -> None:
            super().__init__(memory)
            created.append(self)

    yield Tracked
    for item in created:
        docker("rm", "-fv", item.name)  # -v: elimina tambien el volumen ANONIMO (/data) de ESTE contenedor; no toca ningun otro volumen


@pytest.mark.parametrize(("memory", "concurrent"), [("128m", 1), ("128m", 5), ("128m", 8), ("256m", 5), ("256m", 8), ("384m", 8), ("512m", 8)])
def test_argon2id_survives_concurrent_attempts_inside_the_memory_limits(limited: type[Limited], memory: str, concurrent: int) -> None:
    """P-41 (cerrado): con la compuerta de UNA verificacion activa no hay OOM ni siquiera con 128 MiB y 8 intentos simultaneos (3 rondas)."""
    c = limited(memory)
    c.start()
    assert login(c.base, c.password) == "200"  # el hash del arranque ya se calculo; la verificacion correcta tambien funciona
    seen: set[str] = set()
    for _ in range(3):  # rafagas repetidas: no se acumula memoria entre rondas
        seen |= c.burst(concurrent)
    assert seen <= {"401", "429"}, seen  # nunca un corte de conexion ni un 5xx; los 429 son el limitador de fuerza bruta
    assert "401" in seen
    state = c.state()
    assert state.startswith("running") and "oom=false" in state, state
    assert json.loads(urllib.request.urlopen(c.base + "/health", timeout=10).read()) == {"status": "ok"}  # sigue sirviendo

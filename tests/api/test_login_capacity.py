"""P-41 en la API: una sola verificación Argon2id activa, respuestas equivalentes, 503 controlado y el resto de protecciones intactas."""
import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.security.operator_auth import MAX_LOGIN_FAILURES
from app.security.verification_gate import VerificationGate
from tests.support import PASSWORD, USERNAME, WRONG_PASSWORD, fast_passwords, make_settings

pytestmark = pytest.mark.anyio
BASE = "http://127.0.0.1:8000"
GOOD = {"username": USERNAME, "password": PASSWORD}
BAD = {"username": USERNAME, "password": WRONG_PASSWORD}
UNKNOWN = {"username": "no-existe", "password": WRONG_PASSWORD}


class Spy:
    """Envuelve `AdminAccounts.authenticate`: cuenta las verificaciones simultáneas (hilos) y puede retardarlas."""

    def __init__(self, app: FastAPI, delay: float = 0.03) -> None:
        self.real, self.delay, self.lock = app.state.accounts.authenticate, delay, threading.Lock()
        self.active = self.peak = self.calls = 0
        app.state.accounts.authenticate = self

    def __call__(self, username: str, password: str) -> bool:
        with self.lock:
            self.active += 1
            self.calls += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delay)
            return bool(self.real(username, password))
        finally:
            with self.lock:
                self.active -= 1


async def started(tmp_path: Path, **gate_args: Any) -> tuple[FastAPI, Spy]:
    app = create_app(make_settings(tmp_path), passwords=fast_passwords(), gate=VerificationGate(**gate_args) if gate_args else None)
    return app, Spy(app)


@pytest.fixture
async def served(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI, Spy]]:
    app, spy = await started(tmp_path)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            yield http, app, spy


async def login(http: httpx.AsyncClient, body: dict[str, Any]) -> httpx.Response:
    return await http.post("/api/auth/login", json=body)


async def test_correct_wrong_and_unknown_logins_still_behave_the_same(served: tuple[httpx.AsyncClient, FastAPI, Spy]) -> None:
    http, _, spy = served
    ok, wrong, unknown = await login(http, GOOD), await login(http, BAD), await login(http, UNKNOWN)
    assert ok.status_code == 200 and "set-cookie" in ok.headers
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json() == {"detail": "credenciales invalidas"}
    assert "set-cookie" not in wrong.headers and "set-cookie" not in unknown.headers
    assert spy.calls == 3  # el usuario inexistente tambien pasa por la compuerta (mismo costo)


@pytest.mark.parametrize("burst", [5, 8])
async def test_simultaneous_attempts_never_run_two_verifications_at_once(served: tuple[httpx.AsyncClient, FastAPI, Spy], burst: int) -> None:
    http, _, spy = served
    bodies = [BAD if i % 2 else UNKNOWN for i in range(burst)]  # mezcla de contrasena incorrecta y usuario inexistente
    answers = await asyncio.gather(*[login(http, b) for b in bodies])
    codes = sorted(r.status_code for r in answers)
    assert spy.peak == 1  # nunca dos Argon2id a la vez
    assert codes == [401] * MAX_LOGIN_FAILURES + [429] * (burst - MAX_LOGIN_FAILURES)  # el limitador de fuerza bruta sigue funcionando
    assert {r.text for r in answers if r.status_code == 401} == {'{"detail":"credenciales invalidas"}'}  # respuestas identicas con y sin usuario


async def test_a_wait_that_exceeds_the_limit_is_a_controlled_503_that_does_not_count_as_a_failed_login(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    app, spy = await started(tmp_path, max_waiting=4, wait_timeout_s=0.1)
    spy.delay = 0.5  # la verificacion activa tarda mas que la espera maxima
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            with caplog.at_level(logging.INFO):
                first, second = await asyncio.gather(login(http, BAD), _after(0.05, login(http, BAD)))
            assert first.status_code == 401
            assert second.status_code == 503 and second.json() == {"detail": "servicio ocupado"} and second.headers["retry-after"] == "2"
            assert "set-cookie" not in second.headers and WRONG_PASSWORD not in second.text
            assert len(app.state.auth._logins._stamps) == 1  # solo cuenta la verificacion real; el rechazo por capacidad no da ventaja ni quita cupo
            assert spy.calls == 1  # la rechazada nunca se verifico
            assert "event=login_busy" in caplog.text and WRONG_PASSWORD not in caplog.text and PASSWORD not in caplog.text
            spy.delay = 0.01  # recuperacion tras el rechazo
            assert (await login(http, GOOD)).status_code == 200


async def _after(delay: float, awaitable: Any) -> Any:
    await asyncio.sleep(delay)
    return await awaitable


async def test_a_full_queue_is_a_503_and_everything_recovers(tmp_path: Path) -> None:
    app, spy = await started(tmp_path, max_waiting=1, wait_timeout_s=5)
    spy.delay = 0.3
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            answers = await asyncio.gather(login(http, BAD), _after(0.05, login(http, BAD)), _after(0.1, login(http, BAD)))
            assert sorted(r.status_code for r in answers) == [401, 401, 503]  # 1 activa + 1 en cola + 1 rechazada por cola llena
            assert spy.peak == 1 and len(app.state.auth._logins._stamps) == 2
            spy.delay = 0.0
            assert (await login(http, GOOD)).status_code == 200


async def test_busy_rejections_do_not_weaken_or_consume_the_brute_force_limit(tmp_path: Path) -> None:
    app, spy = await started(tmp_path, max_waiting=0, wait_timeout_s=5)
    spy.delay = 0.1
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            burst = await asyncio.gather(*[login(http, BAD) for _ in range(6)])
            assert sorted({r.status_code for r in burst}) == [401, 503] and sum(r.status_code == 401 for r in burst) == 1
            spy.delay = 0.0
            codes = [(await login(http, BAD)).status_code for _ in range(MAX_LOGIN_FAILURES + 1)]
            assert codes[: MAX_LOGIN_FAILURES - 1] == [401] * (MAX_LOGIN_FAILURES - 1) and codes[-1] == 429  # solo 5 fallos REALES bloquean
            assert (await login(http, GOOD)).status_code == 429  # y el bloqueo sigue aplicando aunque la contrasena sea correcta


async def test_cookie_jwt_and_csrf_work_after_capacity_rejections(tmp_path: Path) -> None:
    app, spy = await started(tmp_path, max_waiting=0, wait_timeout_s=5)
    spy.delay = 0.1
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as http:
            rejected = await asyncio.gather(login(http, GOOD), *[_after(0.02, login(http, GOOD)) for _ in range(3)])
            assert sorted(r.status_code for r in rejected) == [200, 503, 503, 503]
            spy.delay = 0.0
            issued = await login(http, {**GOOD, "return_token": True})
            assert issued.status_code == 200
            lowered = issued.headers["set-cookie"].lower()
            assert "httponly" in lowered and "samesite=strict" in lowered and issued.json()["token"].count(".") == 2
            csrf = issued.json()["csrf_token"]
            assert (await http.post("/api/identity")).status_code == 403  # sin CSRF
            assert (await http.post("/api/identity", headers={"X-CSRF-Token": csrf})).status_code == 201
            assert (await http.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})).status_code == 204
            assert (await http.get("/api/status")).status_code == 401


async def test_the_deployment_runs_a_single_process() -> None:
    """El semaforo es por proceso: la configuracion real de despliegue (Dockerfile, compose, laboratorio y README) no usa varios procesos."""
    root = Path(__file__).resolve().parents[2]
    for name in ("Dockerfile", "compose.yaml", "README.md", "lab/product/compose.yaml", "lab/e2e/compose.yaml"):
        text = (root / name).read_text(encoding="utf-8")
        advice = text.replace("no use `--workers`", "").replace("`--workers N`", "").replace("--workers N", "")  # el README solo ADVIERTE de no usarlo
        assert "--workers" not in advice, name
        assert "WEB_CONCURRENCY" not in text, name

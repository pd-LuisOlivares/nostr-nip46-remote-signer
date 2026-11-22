"""P-41: compuerta de verificaciones Argon2id: una activa por proceso, cola acotada, espera máxima, cupo liberado al terminar el hilo."""
import asyncio
import threading
import time

import pytest

from app.security.verification_gate import DEFAULT_MAX_WAITING, DEFAULT_WAIT_TIMEOUT_S, Busy, VerificationGate

pytestmark = pytest.mark.anyio


class Probe:
    """Mide cuántas funciones corren A LA VEZ (en hilos distintos) y permite retenerlas con un evento."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = self.peak = self.started = 0
        self.release = threading.Event()
        self.release.set()

    def work(self, value: int = 0, hold: float = 0.02) -> int:
        with self.lock:
            self.active += 1
            self.started += 1
            self.peak = max(self.peak, self.active)
        try:
            self.release.wait(5)
            time.sleep(hold)
            return value
        finally:
            with self.lock:
                self.active -= 1


def test_defaults_are_bounded() -> None:
    assert DEFAULT_MAX_WAITING == 4 and 0 < DEFAULT_WAIT_TIMEOUT_S <= 5
    for bad in ({"max_waiting": -1}, {"wait_timeout_s": 0}, {"wait_timeout_s": -1.0}):
        with pytest.raises(ValueError):
            VerificationGate(**bad)  # type: ignore[arg-type]


async def test_returns_the_result_and_propagates_errors_releasing_the_slot() -> None:
    gate, probe = VerificationGate(), Probe()
    assert await gate.run(probe.work, 7) == 7

    def boom() -> None:
        raise RuntimeError("fallo interno")

    for _ in range(3):  # tras cada error el cupo sigue libre
        with pytest.raises(RuntimeError):
            await gate.run(boom)
    assert await gate.run(probe.work, 9) == 9 and gate.waiting == 0


async def test_never_more_than_one_verification_runs_at_the_same_time() -> None:
    gate, probe = VerificationGate(max_waiting=20, wait_timeout_s=10), Probe()
    results = await asyncio.gather(*[gate.run(probe.work, i, 0.02) for i in range(12)])
    assert sorted(results) == list(range(12)) and probe.peak == 1 and probe.started == 12 and gate.waiting == 0


async def test_a_full_queue_is_rejected_immediately_and_the_gate_recovers() -> None:
    gate, probe = VerificationGate(max_waiting=2, wait_timeout_s=10), Probe()
    probe.release.clear()  # la primera verificacion queda retenida
    active = asyncio.create_task(gate.run(probe.work, 1))
    await asyncio.sleep(0.05)
    waiting = [asyncio.create_task(gate.run(probe.work, i)) for i in (2, 3)]
    await asyncio.sleep(0.05)
    assert gate.waiting == 2
    t = time.perf_counter()
    with pytest.raises(Busy):
        await gate.run(probe.work, 4)  # cola llena: rechazo inmediato, no espera
    assert time.perf_counter() - t < 0.5 and gate.waiting == 2
    probe.release.set()
    assert await asyncio.gather(active, *waiting) == [1, 2, 3] and probe.peak == 1
    assert await gate.run(probe.work, 5) == 5 and gate.waiting == 0  # recuperacion


async def test_waiting_longer_than_the_timeout_is_busy_then_recovers() -> None:
    gate, probe = VerificationGate(max_waiting=4, wait_timeout_s=0.15), Probe()
    probe.release.clear()
    active = asyncio.create_task(gate.run(probe.work, 1))
    await asyncio.sleep(0.05)
    t = time.perf_counter()
    with pytest.raises(Busy):
        await gate.run(probe.work, 2)
    assert 0.1 <= time.perf_counter() - t < 1.0 and gate.waiting == 0  # espero ~el maximo y se fue de la cola
    probe.release.set()
    assert await active == 1
    assert await gate.run(probe.work, 3) == 3  # recuperacion
    assert probe.started == 2 and probe.peak == 1  # la rechazada nunca llego a ejecutarse


async def test_cancelling_the_caller_does_not_free_the_slot_until_the_thread_ends() -> None:
    """Un cliente que se desconecta no puede dejar dos calculos Argon2id a la vez: el cupo se libera al TERMINAR el hilo."""
    gate, probe = VerificationGate(max_waiting=4, wait_timeout_s=0.15), Probe()
    probe.release.clear()
    victim = asyncio.create_task(gate.run(probe.work, 1))
    await asyncio.sleep(0.05)
    victim.cancel()
    with pytest.raises(asyncio.CancelledError):
        await victim
    with pytest.raises(Busy):  # el hilo sigue calculando: no hay cupo
        await gate.run(probe.work, 2)
    assert probe.started == 1 and probe.active == 1
    probe.release.set()
    await asyncio.sleep(0.1)
    assert await gate.run(probe.work, 3) == 3 and probe.peak == 1


async def test_zero_waiting_slots_means_no_queue_at_all() -> None:
    gate, probe = VerificationGate(max_waiting=0, wait_timeout_s=5), Probe()
    probe.release.clear()
    active = asyncio.create_task(gate.run(probe.work, 1))
    await asyncio.sleep(0.05)
    with pytest.raises(Busy):
        await gate.run(probe.work, 2)
    probe.release.set()
    assert await active == 1

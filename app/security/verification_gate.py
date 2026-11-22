"""Compuerta de verificaciones Argon2id (P-41): UNA verificación activa por proceso, cola ACOTADA y espera máxima. Sin FastAPI.

Por qué: cada verificación Argon2id reserva 64 MiB (perfil RFC 9106 «low memory»). El limitador de intentos admite hasta 5 en vuelo, y 5 verificaciones
simultáneas con 256 a 352 MiB de memoria provocaban un OOM-kill del contenedor (B6.1B). Con una sola activa el pico es ~43 MiB de base + 64 MiB.

Reglas:
- `max_active = 1`: nunca dos cálculos Argon2id a la vez en el proceso. La verificación corre en un hilo (`asyncio.to_thread`): no bloquea el *event loop*.
- Cola acotada (`max_waiting`) y espera máxima (`wait_timeout_s`): superado cualquiera de los dos, `Busy` (la API responde 503 con `Retry-After`). Nunca
  hay una cola ilimitada.
- El cupo se libera **cuando termina el hilo**, no cuando se cancela quien esperaba (un cliente que se desconecta no deja dos cálculos a la vez).
- Es un límite **por proceso**. La aplicación está pensada para UN proceso (la clave de firma del JWT, las sesiones y los limitadores viven en memoria de
  cada proceso, así que `--workers N` no está soportado): con N procesos la memoria máxima sería N × 64 MiB y este semáforo no sería un límite global.
- No registra ni conserva contraseñas, hashes ni resultados.
"""
import asyncio
from collections.abc import Callable
from typing import Any, Final

DEFAULT_MAX_WAITING: Final = 4  # con MAX_LOGIN_FAILURES = 5 intentos en vuelo (1 activo + 4 esperando) la cola nunca se desborda por el uso normal
DEFAULT_WAIT_TIMEOUT_S: Final = 3.0  # una verificación dura ~0,05-0,1 s: 4 esperando son ~0,4 s; 3 s indica un sistema saturado o sin memoria


class Busy(Exception):
    """Capacidad de verificación agotada (cola llena o espera máxima superada). No es un fallo de credenciales."""


class VerificationGate:
    def __init__(self, *, max_waiting: int = DEFAULT_MAX_WAITING, wait_timeout_s: float = DEFAULT_WAIT_TIMEOUT_S) -> None:
        if max_waiting < 0 or wait_timeout_s <= 0:
            raise ValueError("configuracion de la compuerta invalida")
        self._semaphore = asyncio.Semaphore(1)
        self._max_waiting, self._timeout = max_waiting, wait_timeout_s
        self._waiting = 0

    @property
    def waiting(self) -> int:
        return self._waiting

    async def run[T](self, function: Callable[..., T], *args: object) -> T:
        """Ejecuta `function(*args)` en un hilo cuando haya cupo; `Busy` si la cola está llena o la espera supera el máximo."""
        if self._semaphore.locked() and self._waiting >= self._max_waiting:
            raise Busy
        self._waiting += 1
        try:
            await asyncio.wait_for(self._semaphore.acquire(), self._timeout)
        except TimeoutError:
            raise Busy from None
        finally:
            self._waiting -= 1
        future = asyncio.ensure_future(asyncio.to_thread(function, *args))
        future.add_done_callback(self._finished)  # el cupo se libera al TERMINAR el hilo, aunque quien esperaba se haya cancelado
        return await asyncio.shield(future)

    def _finished(self, future: "asyncio.Future[Any]") -> None:
        self._semaphore.release()
        if not future.cancelled():
            future.exception()  # se consume (si la tarea de arriba ya se canceló, evita «exception was never retrieved»); no se registra

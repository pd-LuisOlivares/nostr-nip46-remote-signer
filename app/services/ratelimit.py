"""Limitador de frecuencia de ventana MÓVIL con almacenamiento acotado (D-17, modo `continuous`).

Cuenta las solicitudes aceptadas en los últimos `window_s` segundos (60 por defecto) para cada clave. Al alcanzar el límite rechaza sin más: no detiene el firmante
ni revoca nada; el cupo se libera solo a medida que las solicitudes antiguas salen de la ventana. Las solicitudes rechazadas NO consumen cupo (un exceso sostenido no
se «hereda» más allá de la ventana). El almacenamiento está acotado: como mucho `max_keys` claves, cada una con como mucho `limit` marcas de tiempo (se descartan las
claves menos recientes). La primera solicitud rechazada de cada ventana se señala (`LIMITED_FIRST`) para auditarla UNA vez por ventana y clave, no una vez por solicitud.
"""
from collections import OrderedDict, deque
from collections.abc import Callable
from enum import StrEnum
from typing import Final

GLOBAL_REQUESTS_PER_MIN: Final = 120  # tope global del firmante, aplicado ANTES de verificar la firma o descifrar nada
WINDOW_S: Final = 60.0


class Verdict(StrEnum):
    ALLOWED = "allowed"
    LIMITED_FIRST = "limited_first"  # primera solicitud rechazada de esta ventana para esta clave: es la que se audita
    LIMITED = "limited"


class SlidingWindowLimiter:
    def __init__(self, *, now: Callable[[], float], limit: int, window_s: float = WINDOW_S, max_keys: int = 512) -> None:
        if limit < 1 or window_s <= 0 or max_keys < 1:
            raise ValueError("limit, window_s y max_keys deben ser positivos")
        self._now, self._limit, self._window, self._max_keys = now, limit, float(window_s), max_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()  # clave -> marcas de tiempo de las solicitudes ACEPTADAS dentro de la ventana
        self._notified: dict[str, float] = {}  # clave -> instante de la última señal de rechazo (para auditar una vez por ventana)

    @property
    def limit(self) -> int:
        return self._limit

    def hit(self, key: str) -> Verdict:
        """Registra una solicitud de `key` y dice si se acepta. Una solicitud aceptada consume cupo; una rechazada no."""
        now = self._now()
        cutoff = now - self._window
        hits = self._hits.get(key)
        if hits is None:
            hits = self._hits[key] = deque()
            while len(self._hits) > self._max_keys:  # acotado: se olvida la clave usada hace más tiempo
                forgotten, _ = self._hits.popitem(last=False)
                self._notified.pop(forgotten, None)
        else:
            self._hits.move_to_end(key)
        while hits and hits[0] <= cutoff:  # una marca de exactamente `window_s` segundos ya salió de la ventana
            hits.popleft()
        if len(hits) >= self._limit:
            last = self._notified.get(key)
            if last is None or last <= cutoff:
                self._notified[key] = now
                return Verdict.LIMITED_FIRST
            return Verdict.LIMITED
        hits.append(now)
        return Verdict.ALLOWED

    def tracked_keys(self) -> int:
        return len(self._hits)

    def stored_marks(self) -> int:
        """Marcas de tiempo guardadas en total (para comprobar que el almacenamiento sigue acotado)."""
        return sum(len(h) for h in self._hits.values())

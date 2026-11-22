"""Estado del firmante que, en modo `continuous` (D-17), sobrevive a una caída recuperable del relay: clave de transporte, conexiones y registros anti-replay.

Qué se conserva y qué no (reglas de ciclo de vida):
  - Fallo RECUPERABLE del relay (conexión cerrada por el relay, relay no disponible, firmante que no llegó a estar listo): el estado se CONSERVA y el
    siguiente arranque lo reanuda, así que no hay que repetir el emparejamiento (misma clave de transporte, mismas conexiones).
  - Detención manual, apagado, tope de solicitudes, AUTH o cierre de la suscripción: las conexiones se REVOCAN y el estado se INVALIDA. El siguiente arranque
    crea una clave de transporte y un administrador de conexiones nuevos. Los retos ya firmados se recuerdan (vigencia acotada) mientras no cambie la identidad.
  - Cambio de identidad: se descarta todo, incluidos los retos.
  - Reinicio del proceso: no se conserva nada (la clave Nostr vive solo en memoria, D-3).
En modo `supervised` el estado es de UNA sesión: el runtime crea uno nuevo en cada arranque, exactamente como antes.

Los registros anti-replay están acotados en tamaño (se descarta lo más antiguo) y en vigencia, para que la memoria no crezca sin límite.
"""
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterator
from dataclasses import dataclass
from typing import Final

from app.config import Settings
from app.nostr.keys import Keypair
from app.services.connections import MAX_CLIENTS, ConnectionManager
from app.services.ratelimit import GLOBAL_REQUESTS_PER_MIN, SlidingWindowLimiter

REPLAY_MEMORY_TTL_S: Final = 86_400  # solicitudes y retos: 24 h (una sesión supervisada dura como máximo SESSION_TTL_S = 86 400 s, así que el comportamiento no cambia)
TRANSPORT_EVENT_MARGIN_S: Final = 60  # un id de evento solo importa mientras `created_at` esté dentro de la ventana (más el adelanto de 30 s)
MAX_SEEN_EVENTS: Final = 4096
MAX_SEEN_REQUESTS: Final = 4096
MAX_SEEN_CHALLENGES: Final = 4096

# Motivos de fin de sesión tras los cuales, EN MODO CONTINUO, se conservan las conexiones autorizadas. Cualquier otro motivo las revoca (denegar por defecto).
RECOVERABLE_END_REASONS: Final = frozenset({"el_relay_cerro_la_conexion", "relay_no_disponible", "no_llego_a_estar_listo"})


class BoundedSeen[K: Hashable]:
    """Conjunto de «ya visto» con vigencia por entrada y tamaño máximo. Cumple `Collection` (lo que espera la política para los retos).

    Una clave ya presente conserva su vigencia original (no se alarga al volver a verla). Al llenarse se descarta lo más antiguo.
    """

    def __init__(self, *, now: Callable[[], float], ttl_s: float, max_entries: int) -> None:
        if ttl_s <= 0 or max_entries < 1:
            raise ValueError("ttl_s y max_entries deben ser positivos")
        self._now, self._ttl, self._max = now, float(ttl_s), max_entries
        self._items: OrderedDict[K, float] = OrderedDict()  # clave -> instante de caducidad (en orden de inserción)

    def _prune(self) -> None:
        now = self._now()
        while self._items:
            expires = next(iter(self._items.values()))
            if expires > now:
                break
            self._items.popitem(last=False)

    def add(self, key: K) -> None:
        self._prune()
        if key in self._items:
            return
        self._items[key] = self._now() + self._ttl
        while len(self._items) > self._max:
            self._items.popitem(last=False)

    def __contains__(self, key: object) -> bool:
        self._prune()
        try:
            return key in self._items
        except TypeError:  # clave no hashable: nunca pudo registrarse
            return False

    def __len__(self) -> int:
        self._prune()
        return len(self._items)

    def __iter__(self) -> Iterator[K]:
        self._prune()
        return iter(list(self._items))

    @property
    def max_entries(self) -> int:
        return self._max

    @property
    def ttl_s(self) -> float:
        return self._ttl


@dataclass(slots=True, repr=False)
class ServiceState:
    """Lo que un `SignerService` necesita y que, en modo continuo, el runtime conserva entre arranques."""

    transport: Keypair  # clave de transporte: DISTINTA de la identidad; las URI y los clientes emparejados dependen de ella
    connections: ConnectionManager
    seen_events: BoundedSeen[str]  # ids de eventos de transporte
    seen_requests: BoundedSeen[tuple[str, str]]  # (cliente, id de solicitud)
    seen_challenges: BoundedSeen[str]  # huellas de los retos ya firmados
    global_limiter: SlidingWindowLimiter  # modo continuo: solicitudes por minuto de TODO el firmante (una sola clave); se aplica antes de descifrar
    connection_limiter: SlidingWindowLimiter  # modo continuo: solicitudes por minuto de cada conexión ACTIVA (clave verificada del cliente; acotado)
    stale: bool = False  # True tras una parada que revocó las conexiones: el siguiente arranque debe crear un estado nuevo

    @classmethod
    def create(cls, settings: Settings, now: Callable[[], float], *, connections: ConnectionManager | None = None,
               challenges: BoundedSeen[str] | None = None) -> "ServiceState":
        return cls(
            transport=Keypair.generate(),
            connections=connections or ConnectionManager(now=now, secret_ttl_s=settings.secret_ttl_s, connection_ttl_s=settings.connection_ttl_s),
            seen_events=BoundedSeen(now=now, ttl_s=settings.window_s + TRANSPORT_EVENT_MARGIN_S, max_entries=MAX_SEEN_EVENTS),
            seen_requests=BoundedSeen(now=now, ttl_s=REPLAY_MEMORY_TTL_S, max_entries=MAX_SEEN_REQUESTS),
            seen_challenges=challenges if challenges is not None else BoundedSeen(now=now, ttl_s=REPLAY_MEMORY_TTL_S, max_entries=MAX_SEEN_CHALLENGES),
            global_limiter=SlidingWindowLimiter(now=now, limit=GLOBAL_REQUESTS_PER_MIN, max_keys=1),
            connection_limiter=SlidingWindowLimiter(now=now, limit=settings.requests_per_min, max_keys=2 * MAX_CLIENTS))

    def __repr__(self) -> str:
        """Sin claves, secretos ni identificadores completos: solo el prefijo público de la clave de transporte y los tamaños."""
        return (f"ServiceState(transport={self.transport.public_hex[:8]}..., stale={self.stale}, events={len(self.seen_events)}, "
                f"requests={len(self.seen_requests)}, challenges={len(self.seen_challenges)})")

    def invalidate(self) -> None:
        """Marca el estado como inservible (las conexiones ya se revocaron): el siguiente arranque crea uno nuevo."""
        self.stale = True

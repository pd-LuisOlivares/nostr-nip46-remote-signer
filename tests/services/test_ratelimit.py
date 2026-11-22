"""D-17, Componente 3: limitador de frecuencia de ventana móvil (`app/services/ratelimit.py`). Deterministas, con reloj inyectado."""
import ast
from pathlib import Path

import pytest

from app.services.ratelimit import GLOBAL_REQUESTS_PER_MIN, WINDOW_S, SlidingWindowLimiter, Verdict
from tests.support import Clock

SOURCE = Path(__file__).resolve().parents[2] / "app" / "services" / "ratelimit.py"


def limiter(clock: Clock, limit: int = 3, **kw: float) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(now=clock, limit=limit, **kw)  # type: ignore[arg-type]


def test_the_approved_constants() -> None:
    assert GLOBAL_REQUESTS_PER_MIN == 120 and WINDOW_S == 60.0


def test_the_window_slides_and_the_quota_returns_exactly_after_sixty_seconds() -> None:
    clock = Clock()
    lim = limiter(clock)
    assert [lim.hit("a") for _ in range(3)] == [Verdict.ALLOWED] * 3
    assert lim.hit("a") is Verdict.LIMITED_FIRST and lim.hit("a") is Verdict.LIMITED  # al límite: se rechaza
    clock.advance(59.9)
    assert lim.hit("a") is Verdict.LIMITED  # todavía dentro de la ventana de las primeras
    clock.advance(0.1)  # exactamente 60 s: las tres primeras salen de la ventana
    assert [lim.hit("a") for _ in range(3)] == [Verdict.ALLOWED] * 3 and lim.hit("a") is Verdict.LIMITED_FIRST


def test_the_window_is_sliding_not_a_fixed_minute() -> None:
    clock = Clock()
    lim = limiter(clock, limit=4)
    assert [lim.hit("a") for _ in range(2)] == [Verdict.ALLOWED] * 2  # t = 0
    clock.advance(30)
    assert [lim.hit("a") for _ in range(2)] == [Verdict.ALLOWED] * 2  # t = 30: ya hay 4 en la ventana
    clock.advance(29)
    assert lim.hit("a") is Verdict.LIMITED_FIRST  # t = 59
    clock.advance(1)  # t = 60: salen SOLO las dos de t = 0 (la última señal de rechazo fue en t = 59: aún no se vuelve a auditar)
    assert [lim.hit("a") for _ in range(3)] == [Verdict.ALLOWED, Verdict.ALLOWED, Verdict.LIMITED]
    clock.advance(30)  # t = 90: salen las dos de t = 30; quedan las dos de t = 60
    assert [lim.hit("a") for _ in range(3)] == [Verdict.ALLOWED, Verdict.ALLOWED, Verdict.LIMITED]
    clock.advance(30)  # t = 120: salen las dos de t = 60 (quedan las de t = 90) y la señal de t = 59 ya tiene más de 60 s: se vuelve a auditar, una vez
    assert [lim.hit("a") for _ in range(5)] == [Verdict.ALLOWED, Verdict.ALLOWED, Verdict.LIMITED_FIRST, Verdict.LIMITED, Verdict.LIMITED]


def test_rejected_requests_do_not_consume_quota() -> None:
    clock = Clock()
    lim = limiter(clock)
    for _ in range(3):
        lim.hit("a")
    for _ in range(500):  # un exceso sostenido no se «hereda» más allá de la ventana
        lim.hit("a")
    assert lim.stored_marks() == 3
    clock.advance(60)
    assert lim.hit("a") is Verdict.ALLOWED


def test_the_rejection_is_signalled_once_per_window_and_key_for_the_audit() -> None:
    clock = Clock()
    lim = limiter(clock, limit=1)
    lim.hit("a")
    verdicts = [lim.hit("a") for _ in range(20)]
    assert verdicts.count(Verdict.LIMITED_FIRST) == 1 and verdicts.count(Verdict.LIMITED) == 19  # una auditoría, no veinte
    clock.advance(61)
    assert lim.hit("a") is Verdict.ALLOWED
    assert lim.hit("a") is Verdict.LIMITED_FIRST  # en la ventana siguiente vuelve a señalarse, una vez


def test_keys_are_independent() -> None:
    clock = Clock()
    lim = limiter(clock, limit=2)
    for _ in range(2):
        lim.hit("a")
    assert lim.hit("a") is Verdict.LIMITED_FIRST and lim.hit("b") is Verdict.ALLOWED and lim.hit("b") is Verdict.ALLOWED and lim.hit("b") is Verdict.LIMITED_FIRST


def test_storage_stays_bounded_by_keys_and_by_marks_per_key() -> None:
    clock = Clock()
    lim = limiter(clock, limit=5, max_keys=10)
    for n in range(10_000):
        lim.hit(f"cliente-{n}")
        assert lim.tracked_keys() <= 10 and lim.stored_marks() <= 10 * 5
    for _ in range(10_000):
        lim.hit("uno-solo")
    assert lim.stored_marks() <= 10 * 5 and lim.tracked_keys() <= 10  # ni las claves ni las marcas por clave crecen sin límite
    assert len(lim._notified) <= 10  # tampoco el registro de señales


def test_the_least_recently_used_key_is_forgotten_first_and_forgetting_resets_it() -> None:
    clock = Clock()
    lim = limiter(clock, limit=1, max_keys=2)
    lim.hit("a")
    lim.hit("b")
    lim.hit("a")  # `a` se usó más recientemente que `b`
    lim.hit("c")  # entra `c`: se olvida `b`
    assert lim.tracked_keys() == 2 and lim.hit("b") is Verdict.ALLOWED  # `b` fue olvidada: empieza de cero


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": -1}, {"window_s": 0}, {"max_keys": 0}])
def test_invalid_parameters_are_rejected(kwargs: dict[str, float]) -> None:
    base: dict[str, float] = {"limit": 3, "window_s": 60, "max_keys": 10}
    with pytest.raises(ValueError):
        SlidingWindowLimiter(now=Clock(), **{**base, **kwargs})  # type: ignore[arg-type]


def test_the_module_is_standard_library_only_and_has_no_signing_or_approval_logic() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert modules <= {"collections", "collections.abc", "enum", "typing"}, modules
    text = SOURCE.read_text(encoding="utf-8").lower()
    for forbidden in ("sign_event", "approve", "resolve(", "revoke", "stop(", "open(", "logging", "print("):
        assert forbidden not in text, forbidden  # solo cuenta: rechazar nunca detiene el firmante ni revoca

"""D-17, paso 2: registros anti-replay acotados (`BoundedSeen`) y estado del firmante (`ServiceState`). Deterministas, sin red ni relays."""
import ast
from pathlib import Path

import pytest

from app.config import Settings
from app.services.connections import ClientState, ConnectionManager
from app.services.session_state import (MAX_SEEN_CHALLENGES, MAX_SEEN_EVENTS, MAX_SEEN_REQUESTS, RECOVERABLE_END_REASONS, REPLAY_MEMORY_TTL_S,
                                        TRANSPORT_EVENT_MARGIN_S, BoundedSeen, ServiceState)
from tests.support import Clock

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app" / "services" / "session_state.py"


# ------------------------------------------------------------------------------------------------ BoundedSeen
def test_an_entry_is_remembered_until_its_ttl_and_then_forgotten() -> None:
    clock = Clock()
    seen: BoundedSeen[str] = BoundedSeen(now=clock, ttl_s=10, max_entries=100)
    seen.add("a")
    assert "a" in seen and len(seen) == 1 and list(seen) == ["a"]
    clock.advance(9.9)
    assert "a" in seen
    clock.advance(0.2)
    assert "a" not in seen and len(seen) == 0 and list(seen) == []


def test_seeing_a_key_again_does_not_extend_its_lifetime() -> None:
    clock = Clock()
    seen: BoundedSeen[str] = BoundedSeen(now=clock, ttl_s=10, max_entries=100)
    seen.add("a")
    clock.advance(6)
    seen.add("a")  # ya estaba: conserva su vigencia original (no se puede mantener viva repitiéndola)
    clock.advance(5)
    assert "a" not in seen


def test_the_size_is_bounded_and_the_oldest_entries_are_dropped_first() -> None:
    seen: BoundedSeen[int] = BoundedSeen(now=Clock(), ttl_s=1000, max_entries=3)
    for n in range(5):
        seen.add(n)
    assert len(seen) == 3 and list(seen) == [2, 3, 4] and 0 not in seen and 4 in seen


def test_memory_stays_bounded_under_a_flood_of_distinct_keys() -> None:
    clock = Clock()
    seen: BoundedSeen[str] = BoundedSeen(now=clock, ttl_s=60, max_entries=100)
    for n in range(10_000):
        seen.add(f"evento-{n}")
        if n % 500 == 0:
            clock.advance(1)
        assert len(seen._items) <= 100  # el almacén interno nunca supera el tope, ni siquiera entre consultas
    assert len(seen) == 100 and "evento-9999" in seen and "evento-0" not in seen


def test_expired_entries_are_pruned_so_the_store_does_not_keep_growing_in_time() -> None:
    clock = Clock()
    seen: BoundedSeen[str] = BoundedSeen(now=clock, ttl_s=5, max_entries=1000)
    for n in range(50):
        seen.add(f"k{n}")
    clock.advance(6)
    seen.add("nueva")
    assert len(seen._items) == 1  # al insertar se purga lo caducado


def test_it_behaves_as_a_collection_and_tolerates_unhashable_keys() -> None:
    seen: BoundedSeen[str] = BoundedSeen(now=Clock(), ttl_s=10, max_entries=10)
    seen.add("x")
    assert ("x" in seen, "y" in seen, [] in seen, {} in seen) == (True, False, False, False)  # type: ignore[comparison-overlap]
    assert seen.max_entries == 10 and seen.ttl_s == 10.0


@pytest.mark.parametrize("ttl, size", [(0, 10), (-1, 10), (10, 0), (10, -3)])
def test_invalid_limits_are_rejected(ttl: float, size: int) -> None:
    with pytest.raises(ValueError):
        BoundedSeen(now=Clock(), ttl_s=ttl, max_entries=size)


# ------------------------------------------------------------------------------------------------ ServiceState
def test_a_new_state_has_its_own_transport_key_connections_and_empty_bounded_registries() -> None:
    clock = Clock()
    a, b = ServiceState.create(Settings(), clock), ServiceState.create(Settings(), clock)
    assert a.transport.public_hex != b.transport.public_hex and a.connections is not b.connections and not a.stale
    for state in (a, b):
        assert (len(state.seen_events), len(state.seen_requests), len(state.seen_challenges)) == (0, 0, 0)
        assert (state.seen_events.max_entries, state.seen_requests.max_entries, state.seen_challenges.max_entries) == (MAX_SEEN_EVENTS, MAX_SEEN_REQUESTS, MAX_SEEN_CHALLENGES)


def test_registry_lifetimes_follow_the_freshness_window_and_the_longest_session() -> None:
    settings = Settings(window_s=120)
    state = ServiceState.create(settings, Clock())
    assert state.seen_events.ttl_s == 120 + TRANSPORT_EVENT_MARGIN_S  # un id solo importa mientras `created_at` esté dentro de la ventana
    assert state.seen_requests.ttl_s == state.seen_challenges.ttl_s == REPLAY_MEMORY_TTL_S == 86_400  # >= SESSION_TTL_S máximo: sin cambio en el modo supervisado


def test_expired_registry_entries_are_forgotten_by_the_documented_lifetimes() -> None:
    clock = Clock()
    state = ServiceState.create(Settings(window_s=120), clock)
    state.seen_events.add("e")
    state.seen_requests.add(("cliente", "r1"))
    state.seen_challenges.add("c" * 64)
    clock.advance(120 + TRANSPORT_EVENT_MARGIN_S + 1)
    assert (len(state.seen_events), len(state.seen_requests), len(state.seen_challenges)) == (0, 1, 1)
    clock.advance(REPLAY_MEMORY_TTL_S)
    assert (len(state.seen_events), len(state.seen_requests), len(state.seen_challenges)) == (0, 0, 0)


def test_a_given_connection_manager_and_challenge_registry_are_reused_not_replaced() -> None:
    clock = Clock()
    manager = ConnectionManager(now=clock, secret_ttl_s=300, connection_ttl_s=60)
    old = ServiceState.create(Settings(), clock)
    old.seen_challenges.add("reto")
    new = ServiceState.create(Settings(), clock, connections=manager, challenges=old.seen_challenges)
    assert new.connections is manager and new.seen_challenges is old.seen_challenges and "reto" in new.seen_challenges
    assert new.transport.public_hex != old.transport.public_hex


def test_invalidate_only_marks_the_state() -> None:
    state = ServiceState.create(Settings(), Clock())
    state.invalidate()
    assert state.stale is True


def test_the_repr_never_shows_keys_or_full_identifiers() -> None:
    state = ServiceState.create(Settings(), Clock())
    state.seen_challenges.add("ab" * 32)
    state.seen_requests.add(("cd" * 32, "r1"))
    text = repr(state) + str(state) + f"{state!r}"
    secret = state.transport._secret.hex()  # type: ignore[attr-defined]
    assert secret not in text and state.transport.public_hex not in text and "ab" * 32 not in text and "cd" * 32 not in text
    assert state.transport.public_hex[:8] in text and "challenges=1" in text


def test_only_recoverable_relay_failures_keep_the_pairings() -> None:
    assert RECOVERABLE_END_REASONS == frozenset({"el_relay_cerro_la_conexion", "relay_no_disponible", "no_llego_a_estar_listo"})
    for reason in ("detenido_por_el_operador", "apagado_de_la_aplicacion", "tope_de_solicitudes", "el_relay_exige_auth", "el_relay_cerro_la_suscripcion",
                   "vida_maxima_de_sesion", "cancelado", "sin_motivo"):
        assert reason not in RECOVERABLE_END_REASONS  # denegar por defecto


# ------------------------------------------------------------------------------------------------ ConnectionManager.forget_pending
def test_forget_pending_removes_only_unfinished_pairings() -> None:
    clock = Clock()
    m = ConnectionManager(now=clock, secret_ttl_s=300, connection_ttl_s=1000)
    m.begin("pendiente")
    m.begin("activo")
    m.activate("activo")
    m.begin("denegado")
    m.deny("denegado")
    assert m.forget_pending() == 1
    assert (m.state_of("pendiente"), m.state_of("activo"), m.state_of("denegado")) == (None, ClientState.ACTIVE, ClientState.DENIED)
    assert m.forget_pending() == 0


# ------------------------------------------------------------------------------------------------ revisión estática del módulo
def test_the_module_has_no_signing_logic_no_implicit_approvals_and_only_standard_and_internal_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert modules <= {"collections", "collections.abc", "dataclasses", "typing", "app.config", "app.nostr.keys", "app.services.connections", "app.services.ratelimit"}, modules
    text = SOURCE.read_text(encoding="utf-8").lower()
    for forbidden in ("auto_sign", "grant", "sign_event", "sign_schnorr", "approve", "resolve(", "open(", "write_", "sqlite", "logging", "print("):
        assert forbidden not in text, forbidden

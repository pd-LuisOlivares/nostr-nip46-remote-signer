"""Auditoría sanitizada en memoria. LISTA BLANCA de eventos y campos: rechaza cualquier cosa con forma de secreto.

Nunca contiene claves, URI `bunker://`, secretos, retos en claro, textos descifrados ni cargas cifradas: los identificadores se registran
truncados (`*8`, `*16`) y los hashes como prefijos (`*_sha16`). Cada entrada se envía también al registro `app.audit` (sin secretos).
"""
import json
import logging
import re
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Final

HEX64: Final = re.compile(r"[0-9a-fA-F]{64}")
FORBIDDEN_KEY_PARTS: Final = ("secret", "priv", "nsec", "cookie", "token", "authorization", "password", "uri")
SCHEMA: Final[dict[str, frozenset[str]]] = {
    "session_start": frozenset({"relay_host", "origin", "max_signatures", "window_s", "tls_groups"}),
    "relay_ready": frozenset(),
    "bunker_issued": frozenset({"transport_pub8", "ttl_s"}),
    "request": frozenset({"method", "scheme", "client8"}),
    "pending_created": frozenset({"request_id", "kind", "client8", "ttl_s"}),
    "decision": frozenset({"request_id", "kind", "approved", "reason", "latency_ms"}),
    "policy": frozenset({"ok", "failed", "origin_seen", "content_ok", "challenge_sha16", "created_at_age_s"}),
    "sign_ok": frozenset({"event_id16", "self_verify"}),
    "response_published": frozenset({"method", "relay_ok", "relay_message"}),
    "relay_notice": frozenset({"kind", "message"}),
    "error": frozenset({"where", "error_type"}),
    "session_end": frozenset({"reason", "signatures"}),
}
_FORBIDDEN_VALUES: Final = re.compile(r"bunker://|secret=|nsec1", re.IGNORECASE)


class AuditViolation(Exception):
    """Se intentó registrar un evento o campo fuera de la lista blanca, o un valor con forma de secreto."""


class AuditLog:
    def __init__(self, *, max_entries: int = 500, now: Callable[[], float] = time.time, logger: logging.Logger | None = None) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._now, self._seq = now, 0
        self._logger = logger or logging.getLogger("app.audit")

    def emit(self, event: str, **fields: Any) -> None:
        allowed = SCHEMA.get(event)
        if allowed is None:
            raise AuditViolation(f"evento no permitido: {event}")
        extra = set(fields) - allowed
        if extra:
            raise AuditViolation(f"campos no permitidos en {event}: {sorted(extra)}")
        for key in fields:
            if any(part in key.lower() for part in FORBIDDEN_KEY_PARTS):
                raise AuditViolation(f"nombre de campo sospechoso: {key}")
        text = json.dumps(fields, ensure_ascii=True, default=str)
        if HEX64.search(text) or _FORBIDDEN_VALUES.search(text):
            raise AuditViolation(f"valor sospechoso en {event}")
        self._seq += 1
        entry: dict[str, Any] = {"seq": self._seq, "ts": round(self._now(), 3), "event": event, **fields}
        self._entries.append(entry)
        self._logger.info("audit %s", json.dumps(entry, ensure_ascii=True, default=str))

    def entries(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, len(self._entries) or 1))
        return list(self._entries)[-limit:]

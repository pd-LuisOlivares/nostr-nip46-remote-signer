"""Evidencia JSONL con LISTA BLANCA de eventos y campos. Defensa en profundidad contra la fuga de secretos.

Rechaza (lanza EvidenceViolation y NO escribe) cualquier evento o campo fuera del esquema, nombres de campo
que sugieran secretos, y valores que parezcan claves/ids completos (64 hex), URI bunker:// o `secret=`.
Los hashes se registran como prefijos de 16 hex (`*_sha16`).
"""
import datetime
import json
import os
import re

HEX64 = re.compile(r"[0-9a-fA-F]{64}")
FORBIDDEN_KEY_PARTS = ("secret", "priv", "nsec", "cookie", "token", "authorization", "password", "uri")

SCHEMA = {
    "session_start": {"versions", "relay_host", "config_sha16", "sn_origin", "mode", "max_signatures", "window_s", "approval_mode"},
    "relay_ready": set(),
    "bunker_issued": {"transport_pub8", "ttl_s", "index"},
    "request": {"method", "scheme", "client8", "plaintext_sha16"},
    # Solo en modo observacion (Compuerta B): estructura de lo recibido, sin secretos ni retos en claro.
    "observed_request": {"method", "params_n", "param_types", "perms_seen"},
    "observed_sign": {"params_n", "param0_type", "size_b", "json_ok", "fields", "kind", "created_at_age_s", "content_seen", "n_tags",
                      "tags", "u_seen", "method_seen", "challenge_shape", "challenge_sha16", "policy_failed"},
    "decision": {"kind", "approved", "reason", "latency_ms"},
    "policy": {"ok", "failed", "origin_seen", "content_ok", "challenge_sha16", "created_at_age_s"},
    "sign_ok": {"event_id16", "tags0", "self_verify"},
    "response_published": {"method", "relay_ok", "relay_message"},
    "error": {"where", "error_type"},
    "session_end": {"reason", "signatures"},
}


class EvidenceViolation(Exception):
    pass


class Evidence:
    def __init__(self, path: str | None):
        self.path = path
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def emit(self, event: str, **fields) -> None:
        allowed = SCHEMA.get(event)
        if allowed is None:
            raise EvidenceViolation(f"evento no permitido: {event}")
        extra = set(fields) - allowed
        if extra:
            raise EvidenceViolation(f"campos no permitidos en {event}: {sorted(extra)}")
        for key in fields:
            if any(part in key.lower() for part in FORBIDDEN_KEY_PARTS):
                raise EvidenceViolation(f"nombre de campo sospechoso: {key}")
        text = json.dumps(fields, ensure_ascii=True)
        low = text.lower()
        if HEX64.search(text) or "bunker://" in low or "secret=" in low or "nsec1" in low:
            raise EvidenceViolation(f"valor sospechoso en {event}")
        rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"), "ev": event, **fields}
        line = json.dumps(rec, ensure_ascii=True) + "\n"
        if self.path:
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line)

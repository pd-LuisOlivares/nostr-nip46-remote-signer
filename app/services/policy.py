"""Política restrictiva para el evento de login `kind 27235` (NIP-98) de Stacker News: 11 comprobaciones puras, sin red ni reloj.

Adaptada del laboratorio (`lab_real/policy.py`, verificada contra el evento real observado en la Compuerta B: sin fallos). Se evalúan TODAS
las comprobaciones (no solo la primera) para poder mostrárselas al operador. La política es más estricta que el servidor de Stacker News.
La plantilla que llega trae `id` y `pubkey` (hallazgo F-5): se VERIFICAN, no se ignoran. Nada del evento se edita: se firma lo recibido.
"""
import hashlib
import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final

from app.nostr.errors import InvalidEventError
from app.nostr.event import MAX_CREATED_AT, MAX_KIND, Tags, compute_event_id
from app.nostr.keys import is_valid_pubkey

KIND_AUTH: Final = 27235
CHECK_ORDER: Final = ("size", "fields", "kind", "pubkey_id", "created_at", "structure", "challenge", "origin", "method", "content", "replay")
_ALLOWED_FIELDS: Final = frozenset({"kind", "content", "tags", "created_at", "pubkey", "id", "sig"})
_REQUIRED_FIELDS: Final = frozenset({"kind", "content", "tags", "created_at"})
_CHALLENGE_RE: Final = re.compile(r"^[0-9a-f]{64}\Z")
_SECRET_SHAPE: Final = re.compile(r"[0-9a-fA-F]{64}|bunker://|secret=|nsec1", re.IGNORECASE)


def safe_text(value: object, limit: int = 80) -> str:
    """Texto no confiable apto para mostrar y registrar: ASCII imprimible, acotado y sin nada con forma de clave, URI o secreto."""
    text = "".join(c if 32 <= ord(c) < 127 else "?" for c in str(value))
    text = text if len(text) <= limit else text[:limit] + "..."
    return "<redactado>" if _SECRET_SHAPE.search(text) else text


def challenge_hash(challenge: str) -> str:
    return hashlib.sha256(challenge.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    origin: str  # valor EXACTO esperado de la etiqueta `u`
    content: str = "Stacker News Authentication"
    window_s: int = 120  # antigüedad máxima de created_at
    max_future_s: int = 30  # adelanto máximo de created_at
    max_size: int = 1024  # bytes del evento recibido


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SignTemplate:
    """Los cuatro campos que se firman, exactamente como los envió el cliente."""

    kind: int
    created_at: int
    tags: Tags
    content: str


@dataclass(frozen=True, slots=True)
class PolicyResult:
    checks: tuple[Check, ...]
    origin_seen: str | None
    content_ok: bool | None
    challenge_sha16: str | None
    created_at_age_s: int | None
    template: SignTemplate | None  # solo si TODAS las comprobaciones pasaron

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failed(self) -> list[str]:
        return [c.name for c in self.checks if not c.ok]


def _parse(raw: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _fields_ok(tpl: dict[str, object]) -> bool:
    kind, created_at, content, tags = tpl.get("kind"), tpl.get("created_at"), tpl.get("content"), tpl.get("tags")
    return (_REQUIRED_FIELDS <= set(tpl) <= _ALLOWED_FIELDS
            and isinstance(kind, int) and not isinstance(kind, bool) and 0 <= kind <= MAX_KIND
            and isinstance(created_at, int) and not isinstance(created_at, bool) and 0 <= created_at <= MAX_CREATED_AT
            and isinstance(content, str) and isinstance(tags, list)
            and all(isinstance(t, list) and all(isinstance(x, str) for x in t) for t in tags))


def evaluate(raw: object, identity_pubkey: str, now: int, seen_challenge_hashes: Collection[str], cfg: PolicyConfig) -> PolicyResult:
    """Evalúa el parámetro de `sign_event` (texto JSON de la plantilla). Devuelve las 11 comprobaciones en `CHECK_ORDER`."""
    results: dict[str, Check] = {}

    def put(name: str, ok: bool, detail: str = "") -> None:
        results[name] = Check(name, bool(ok), detail)

    def finish(origin_seen: str | None = None, content_ok: bool | None = None, challenge_sha16: str | None = None,
               created_at_age_s: int | None = None, template: SignTemplate | None = None) -> PolicyResult:
        for name in CHECK_ORDER:
            results.setdefault(name, Check(name, False, "no evaluado"))
        return PolicyResult(tuple(results[n] for n in CHECK_ORDER), origin_seen, content_ok, challenge_sha16, created_at_age_s, template)

    size_ok = isinstance(raw, str) and len(raw.encode("utf-8", errors="replace")) <= cfg.max_size
    put("size", size_ok, f"limite {cfg.max_size} B")
    tpl = _parse(raw) if size_ok and isinstance(raw, str) else None
    fields_ok = tpl is not None and _fields_ok(tpl)
    put("fields", fields_ok, "" if fields_ok else "esquema no valido o campos desconocidos")
    if not fields_ok or tpl is None:
        return finish()
    kind, created_at, content, tags_raw = tpl["kind"], tpl["created_at"], tpl["content"], tpl["tags"]
    assert isinstance(kind, int) and isinstance(created_at, int) and isinstance(content, str) and isinstance(tags_raw, list)
    tags: Tags = tuple(tuple(t) for t in tags_raw)
    put("kind", kind == KIND_AUTH, f"esperado {KIND_AUTH}")
    try:
        id_ok = "id" not in tpl or tpl["id"] == compute_event_id(identity_pubkey, created_at, kind, tags, content)
    except InvalidEventError:
        id_ok = False
    pubkey_ok = "pubkey" not in tpl or (isinstance(tpl["pubkey"], str) and is_valid_pubkey(tpl["pubkey"]) and tpl["pubkey"] == identity_pubkey)
    put("pubkey_id", pubkey_ok and id_ok, ("pubkey ajena " if not pubkey_ok else "") + ("id no coincide" if not id_ok else ""))
    age = now - created_at
    put("created_at", -cfg.max_future_s <= age <= cfg.window_s, f"ventana {cfg.window_s} s / adelanto {cfg.max_future_s} s")
    shape_ok = len(tags) == 3 and all(len(t) == 2 for t in tags) and [t[0] for t in tags] == ["challenge", "u", "method"]
    put("structure", shape_ok, "exactamente 3 etiquetas en este orden: challenge, u, method")
    challenge, origin, method = (tags[0][1], tags[1][1], tags[2][1]) if shape_ok else ("", "", "")
    challenge_ok = shape_ok and bool(_CHALLENGE_RE.match(challenge))
    put("challenge", challenge_ok, "64 caracteres hexadecimales en minusculas")
    put("origin", shape_ok and origin == cfg.origin, f"esperado {cfg.origin}")
    put("method", shape_ok and method == "GET", "esperado GET")
    put("content", content == cfg.content, "igualdad exacta con el texto de Stacker News")
    c_hash = challenge_hash(challenge) if challenge_ok else None
    put("replay", challenge_ok and c_hash not in seen_challenge_hashes, "el reto no se ha visto antes en esta sesion")
    template = SignTemplate(kind, created_at, tags, content) if all(c.ok for c in results.values()) else None
    return finish(origin_seen=safe_text(origin) if shape_ok else None, content_ok=content == cfg.content,
                  challenge_sha16=c_hash[:16] if c_hash else None, created_at_age_s=age, template=template)

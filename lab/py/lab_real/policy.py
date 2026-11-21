"""Politica restrictiva para kind 27235 (login de Stacker News). Funciones PURAS: sin red, sin reloj, sin estado.

Es mas estricta que el servidor de Stacker News, que solo valida id, firma y tags[0] (nextauth.js:241-270).
Se evaluan TODAS las comprobaciones (no solo la primera) para poder mostrarselas al operador.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from lab_common import nostr

KIND_AUTH = 27235
ALLOWED_FIELDS = {"kind", "content", "tags", "created_at", "pubkey", "id", "sig"}
REQUIRED_FIELDS = {"kind", "content", "tags", "created_at"}
CHALLENGE = re.compile(r"^[0-9a-f]{64}$")
CHECK_ORDER = ("tamano", "campos", "kind", "pubkey_id", "created_at", "estructura", "challenge",
               "origen", "metodo", "content", "reutilizacion")


@dataclass(frozen=True)
class PolicyConfig:
    origin: str                      # valor EXACTO esperado de la etiqueta `u` (NEXT_PUBLIC_URL de Stacker News)
    content: str = "Stacker News Authentication"
    window_s: int = 120              # antiguedad maxima de created_at
    max_future_s: int = 30           # adelanto maximo de created_at
    max_size: int = 1024             # bytes del evento recibido

    def __post_init__(self):
        u = urlsplit(self.origin)
        if (u.scheme != "https" or not u.hostname or u.username or u.path or u.query or u.fragment
                or self.origin.endswith("/")):
            raise ValueError("SN_ORIGIN debe ser un origen https sin ruta, consulta ni barra final")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def sanitize(text, limit: int = 80) -> str:
    """Texto no confiable apto para mostrar y registrar: ASCII imprimible y longitud acotada."""
    s = "".join(c if 32 <= ord(c) < 127 else "?" for c in str(text))
    return s if len(s) <= limit else s[:limit] + "..."


def challenge_hash(challenge: str) -> str:
    return hashlib.sha256(challenge.encode("utf-8")).hexdigest()


def evaluate(raw: str, identity_pk: str, now: int, seen_challenge_hashes: set, cfg: PolicyConfig):
    """Devuelve (comprobaciones, info). `info` solo trae datos no secretos aptos para evidencia y pantalla."""
    results: dict[str, Check] = {}
    info: dict = {}

    def put(name, ok, detail=""):
        results[name] = Check(name, bool(ok), detail)

    put("tamano", len(raw.encode("utf-8")) <= cfg.max_size, f"limite {cfg.max_size} B")
    tpl = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            tpl = parsed
    except (json.JSONDecodeError, RecursionError):
        pass
    fields_ok = (tpl is not None and REQUIRED_FIELDS <= set(tpl) <= ALLOWED_FIELDS
                 and isinstance(tpl["kind"], int) and not isinstance(tpl["kind"], bool)
                 and isinstance(tpl["created_at"], int) and not isinstance(tpl["created_at"], bool)
                 and isinstance(tpl["content"], str) and isinstance(tpl["tags"], list)
                 and all(isinstance(t, list) and all(isinstance(x, str) for x in t) for t in tpl["tags"]))
    put("campos", fields_ok, "" if fields_ok else "esquema no valido o campos desconocidos")
    if not fields_ok:
        for name in CHECK_ORDER:
            results.setdefault(name, Check(name, False, "no evaluado"))
        return [results[n] for n in CHECK_ORDER], info

    put("kind", tpl["kind"] == KIND_AUTH, f"esperado {KIND_AUTH}, recibido {tpl['kind']}")

    id_ok = "id" not in tpl or tpl["id"] == nostr.event_id(
        {"pubkey": identity_pk, "created_at": tpl["created_at"], "kind": tpl["kind"], "tags": tpl["tags"], "content": tpl["content"]})
    pk_ok = "pubkey" not in tpl or tpl["pubkey"] == identity_pk
    put("pubkey_id", pk_ok and id_ok, ("pubkey ajena " if not pk_ok else "") + ("id no coincide" if not id_ok else ""))

    age = now - tpl["created_at"]
    info["created_at_age_s"] = age
    put("created_at", -cfg.max_future_s <= age <= cfg.window_s, f"antiguedad {age} s, ventana {cfg.window_s} s / adelanto {cfg.max_future_s} s")

    tags = tpl["tags"]
    shape_ok = (len(tags) == 3 and all(len(t) == 2 for t in tags)
                and [t[0] for t in tags] == ["challenge", "u", "method"])
    put("estructura", shape_ok, "se exigen exactamente 3 etiquetas en este orden: challenge, u, method")
    c = tags[0][1] if shape_ok else ""
    u = tags[1][1] if shape_ok else ""
    m = tags[2][1] if shape_ok else ""
    put("challenge", shape_ok and bool(CHALLENGE.match(c)), "64 caracteres hexadecimales en minusculas")
    info["challenge_sha16"] = challenge_hash(c)[:16] if shape_ok and CHALLENGE.match(c) else None
    info["origin_seen"] = sanitize(u) if shape_ok else None
    put("origen", shape_ok and u == cfg.origin, f"esperado {cfg.origin}")
    put("metodo", shape_ok and m == "GET", "esperado GET")
    put("content", tpl["content"] == cfg.content, "igualdad exacta con el texto de Stacker News")
    info["content_ok"] = tpl["content"] == cfg.content
    put("reutilizacion", shape_ok and bool(CHALLENGE.match(c)) and challenge_hash(c) not in seen_challenge_hashes,
        "el challenge no se ha visto antes en esta sesion")
    return [results[n] for n in CHECK_ORDER], info


_SECRET_SHAPE = re.compile(r"[0-9a-fA-F]{64}|bunker://|secret=|nsec1", re.IGNORECASE)


def safe_text(text, limit: int = 80) -> str:
    """Texto no confiable para pantalla y evidencia: ASCII, acotado y sin nada con forma de clave, URI o secreto."""
    s = sanitize(text, limit)
    return "<redactado>" if _SECRET_SHAPE.search(s) else s


def describe_sign_params(params, now: int) -> dict:
    """Descripcion ESTRUCTURAL (Compuerta B) de lo que realmente envia el cliente en `sign_event`, sin suponer su forma.

    Pura y tolerante: nunca lanza ante entradas raras. No devuelve el reto en claro (solo su hash y su forma), ni
    valores completos de etiquetas distintos de `u`/`method`; los textos pasan por `safe_text`.
    """
    d: dict = {"params_n": len(params) if isinstance(params, list) else None,
               "param0_type": type(params[0]).__name__ if isinstance(params, list) and params else None}
    raw = params[0] if isinstance(params, list) and params and isinstance(params[0], str) else None
    d["size_b"] = len(raw.encode("utf-8")) if raw is not None else None
    tpl = None
    if raw is not None:
        try:
            parsed = json.loads(raw)
            tpl = parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, RecursionError):
            pass
    d["json_ok"] = tpl is not None
    if tpl is None:
        return d
    d["fields"] = sorted(safe_text(k, 16) for k in list(tpl)[:10])
    d["kind"] = tpl["kind"] if isinstance(tpl.get("kind"), int) and not isinstance(tpl.get("kind"), bool) else None
    ca = tpl.get("created_at")
    d["created_at_age_s"] = now - ca if isinstance(ca, int) and not isinstance(ca, bool) else None
    content = tpl.get("content")
    d["content_seen"] = safe_text(content) if isinstance(content, str) else None
    tags = tpl.get("tags") if isinstance(tpl.get("tags"), list) else None
    d["n_tags"] = len(tags) if tags is not None else None
    shaped = [t for t in (tags or []) if isinstance(t, list) and t and isinstance(t[0], str)]
    d["tags"] = [[safe_text(t[0], 16), len(t) - 1, len(t[1]) if len(t) > 1 and isinstance(t[1], str) else None] for t in shaped[:8]]
    first = lambda name: next((t[1] for t in shaped if t[0] == name and len(t) > 1 and isinstance(t[1], str)), None)  # noqa: E731
    d["u_seen"] = safe_text(first("u")) if first("u") is not None else None
    d["method_seen"] = safe_text(first("method"), 16) if first("method") is not None else None
    c = first("challenge")
    d["challenge_shape"] = None if c is None else ("hex64" if CHALLENGE.match(c) else "otro")
    d["challenge_sha16"] = challenge_hash(c)[:16] if c is not None else None
    return d


def all_ok(checks) -> bool:
    return all(c.ok for c in checks)


def failed(checks) -> list:
    return [c.name for c in checks if not c.ok]

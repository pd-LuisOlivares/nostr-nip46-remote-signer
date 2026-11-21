"""Eventos Nostr (NIP-01): validación estricta, serialización canónica, `id`, firma y verificación (BIP-340)."""
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from app.nostr.errors import InvalidEventError
from app.nostr.keys import Keypair, is_valid_pubkey, verify_schnorr

MAX_KIND: Final = 65535
MAX_CREATED_AT: Final = 2**53 - 1  # mayor entero exacto de JavaScript: Stacker News y NDK usan números de JS
_ID_RE: Final = re.compile(r"^[0-9a-f]{64}\Z")
_SIG_RE: Final = re.compile(r"^[0-9a-f]{128}\Z")
_FIELDS: Final = frozenset({"id", "pubkey", "created_at", "kind", "tags", "content", "sig"})

Tags = tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class NostrEvent:
    id: str
    pubkey: str
    created_at: int
    kind: int
    tags: Tags
    content: str
    sig: str

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "pubkey": self.pubkey, "created_at": self.created_at, "kind": self.kind,
                "tags": [list(tag) for tag in self.tags], "content": self.content, "sig": self.sig}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=False)


def _normalize_tags(tags: object) -> Tags:
    if not isinstance(tags, Sequence) or isinstance(tags, str | bytes):
        raise InvalidEventError("tags invalidos")
    out: list[tuple[str, ...]] = []
    for tag in tags:
        if not isinstance(tag, Sequence) or isinstance(tag, str | bytes) or not all(isinstance(item, str) for item in tag):
            raise InvalidEventError("tags invalidos")
        out.append(tuple(tag))
    return tuple(out)


def _check_template(created_at: object, kind: object, tags: object, content: object) -> tuple[int, int, Tags, str]:
    """Valida los campos que forman el `id` y los devuelve con su tipo ya estrechado."""
    if not isinstance(created_at, int) or isinstance(created_at, bool) or not 0 <= created_at <= MAX_CREATED_AT:
        raise InvalidEventError("created_at invalido")
    if not isinstance(kind, int) or isinstance(kind, bool) or not 0 <= kind <= MAX_KIND:
        raise InvalidEventError("kind invalido")
    if not isinstance(content, str):
        raise InvalidEventError("content invalido")
    return created_at, kind, _normalize_tags(tags), content


def serialize_for_id(pubkey: str, created_at: int, kind: int, tags: Tags, content: str) -> bytes:
    """Serialización canónica de NIP-01: `[0, pubkey, created_at, kind, tags, content]` en JSON compacto y UTF-8.

    Se escapan solo las comillas, la barra invertida y los caracteres de control (`\\n`, `\\r`, `\\t`, `\\b`, `\\f` y el resto como
    `\\u00XX`), igual que `JSON.stringify` (comprobado contra Node 22 en `tests/nostr/fixtures`). Un texto con sustitutos
    aislados no tiene representación UTF-8 y se rechaza.
    """
    created_at, kind, normalized, content = _check_template(created_at, kind, tags, content)
    text = json.dumps([0, pubkey, created_at, kind, [list(tag) for tag in normalized], content], separators=(",", ":"), ensure_ascii=False)
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidEventError("texto no representable en UTF-8") from None


def compute_event_id(pubkey: str, created_at: int, kind: int, tags: Tags, content: str) -> str:
    return hashlib.sha256(serialize_for_id(pubkey, created_at, kind, tags, content)).hexdigest()


def sign_event(keypair: Keypair, kind: int, tags: Sequence[Sequence[str]], content: str, created_at: int) -> NostrEvent:
    """Crea y firma un evento con la clave dada. No acepta ni conserva ninguna firma previa."""
    created_at, kind, normalized, content = _check_template(created_at, kind, tags, content)
    event_id = compute_event_id(keypair.public_hex, created_at, kind, normalized, content)
    signature = keypair.sign(bytes.fromhex(event_id)).hex()
    return NostrEvent(event_id, keypair.public_hex, created_at, kind, normalized, content, signature)


def parse_event(data: object) -> NostrEvent:
    """Convierte un objeto JSON en un evento tras validar forma y tipos. NO comprueba `id` ni firma (ver `verify_event`).

    Estricto: exactamente los siete campos de NIP-01, hexadecimales en minúsculas, enteros de verdad (no booleanos) y etiquetas
    de cadenas. Cualquier otra cosa se rechaza.
    """
    if not isinstance(data, Mapping) or set(data) != _FIELDS:
        raise InvalidEventError("evento mal formado")
    event_id, pubkey, sig = data["id"], data["pubkey"], data["sig"]
    if not (isinstance(event_id, str) and _ID_RE.match(event_id)):
        raise InvalidEventError("id invalido")
    if not isinstance(pubkey, str) or not is_valid_pubkey(pubkey):
        raise InvalidEventError("pubkey invalida")
    if not (isinstance(sig, str) and _SIG_RE.match(sig)):
        raise InvalidEventError("sig invalida")
    created_at, kind, tags, content = _check_template(data["created_at"], data["kind"], data["tags"], data["content"])
    return NostrEvent(event_id, pubkey, created_at, kind, tags, content, sig)


def verify_event(event: NostrEvent) -> None:
    """Comprueba que el `id` sea el hash del contenido y que la firma sea válida para `pubkey`. Lanza `InvalidEventError`."""
    if compute_event_id(event.pubkey, event.created_at, event.kind, event.tags, event.content) != event.id:
        raise InvalidEventError("id no coincide con el contenido")
    if not verify_schnorr(event.pubkey, bytes.fromhex(event.sig), bytes.fromhex(event.id)):
        raise InvalidEventError("firma invalida")


def parse_and_verify_event(data: object) -> NostrEvent:
    event = parse_event(data)
    verify_event(event)
    return event

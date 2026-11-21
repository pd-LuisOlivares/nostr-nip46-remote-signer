"""Primitivas Nostr minimas del laboratorio: claves, evento NIP-01, firma y verificacion BIP-340."""
import hashlib
import json
import re

from coincurve import PrivateKey, PublicKeyXOnly

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX128 = re.compile(r"^[0-9a-f]{128}$")


def new_secret() -> bytes:
    return PrivateKey().secret


def pubkey_of(secret: bytes) -> str:
    return PrivateKey(secret).public_key_xonly.format().hex()


def serialize(ev: dict) -> bytes:
    arr = [0, ev["pubkey"], ev["created_at"], ev["kind"], ev["tags"], ev["content"]]
    return json.dumps(arr, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def event_id(ev: dict) -> str:
    return hashlib.sha256(serialize(ev)).hexdigest()


def sign_event(secret: bytes, kind: int, tags: list, content: str, created_at: int) -> dict:
    ev = {"pubkey": pubkey_of(secret), "created_at": created_at, "kind": kind, "tags": tags, "content": content}
    ev["id"] = event_id(ev)
    ev["sig"] = PrivateKey(secret).sign_schnorr(bytes.fromhex(ev["id"])).hex()
    return {k: ev[k] for k in ("id", "pubkey", "created_at", "kind", "tags", "content", "sig")}


def verify_event(ev) -> tuple[bool, str]:
    """Valida forma, id y firma. Devuelve (ok, motivo)."""
    if not isinstance(ev, dict):
        return False, "evento no es un objeto"
    try:
        if not (isinstance(ev.get("id"), str) and _HEX64.match(ev["id"])):
            return False, "id con formato invalido"
        if not (isinstance(ev.get("pubkey"), str) and _HEX64.match(ev["pubkey"])):
            return False, "pubkey con formato invalido"
        if not (isinstance(ev.get("sig"), str) and _HEX128.match(ev["sig"])):
            return False, "sig con formato invalido"
        if not (isinstance(ev.get("kind"), int) and not isinstance(ev["kind"], bool) and 0 <= ev["kind"] <= 65535):
            return False, "kind invalido"
        if not (isinstance(ev.get("created_at"), int) and not isinstance(ev["created_at"], bool)):
            return False, "created_at invalido"
        tags = ev.get("tags")
        if not (isinstance(tags, list) and all(isinstance(t, list) and all(isinstance(x, str) for x in t) for t in tags)):
            return False, "tags invalidos"
        if not isinstance(ev.get("content"), str):
            return False, "content invalido"
        if event_id(ev) != ev["id"]:
            return False, "id no coincide con el contenido"
        if not PublicKeyXOnly(bytes.fromhex(ev["pubkey"])).verify(bytes.fromhex(ev["sig"]), bytes.fromhex(ev["id"])):
            return False, "firma invalida"
    except (ValueError, KeyError, TypeError) as exc:
        return False, f"error de validacion: {type(exc).__name__}"
    return True, ""

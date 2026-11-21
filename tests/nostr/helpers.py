"""Utilidades de las pruebas del nucleo Nostr: fixtures y vectores oficiales."""
import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
NIP44_VECTORS_SHA256 = "269ed0f69e4c192512cc779e78c555090cebc7c785b609e338a62afc3ce25040"  # nip44.vectors.json @ 1f8dba17 (paulmillr/nip44)


def load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def nostr_tools() -> Any:
    return load_json("nostr_tools_fixtures.json")


def nip44_vectors_path() -> Path:
    return Path(os.environ.get("NIP44_VECTORS_PATH") or ROOT / "lab" / "vendor" / "vectors" / "nip44.vectors.json")


def load_nip44_vectors() -> Any | None:
    """Devuelve los vectores oficiales, o None si el archivo no esta (las pruebas se omiten con aviso). Si el hash no coincide, FALLA."""
    path = nip44_vectors_path()
    if not path.exists():
        return None
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != NIP44_VECTORS_SHA256:
        raise AssertionError(f"el archivo de vectores NIP-44 no coincide con el SHA-256 esperado ({actual})")
    return json.loads(data)["v2"]

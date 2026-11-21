"""NIP-46: modelos estrictos de solicitud y respuesta, y construcción/validación de la URI `bunker://`. Sin E/S de red.

Las reglas del proyecto sobre la URI: al menos un relay `wss://` (obligatorio; `ws://` solo con `allow_insecure_relays` para
laboratorio local), un secreto de conexión aleatorio de al menos 128 bits (se emite uno por URI y es de un solo uso), y ningún
parámetro adicional. La URI contiene el secreto: nunca debe registrarse; `BunkerUri.__repr__` lo oculta.
"""
import json
import re
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Self
from urllib.parse import parse_qsl, quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.nostr.errors import InvalidBunkerUri, InvalidKeyError, InvalidNip46Message
from app.nostr.keys import require_pubkey

NIP46_KIND: Final = 24133
SUPPORTED_METHODS: Final = ("connect", "get_public_key", "sign_event", "ping")
MAX_MESSAGE_CHARS: Final = 65535  # igual que el máximo de texto plano de NIP-44 (P-14)
MAX_URI_CHARS: Final = 2048
MAX_RELAY_URL_CHARS: Final = 255
MAX_RELAYS: Final = 3
SECRET_BYTES: Final = 16  # 128 bits
_SECRET_RE: Final = re.compile(r"^[A-Za-z0-9_-]{22,128}\Z")  # base64url sin relleno: 22 caracteres = 132 bits
_MIN_DISTINCT_SECRET_CHARS: Final = 10  # descarta secretos obviamente constantes; el aleatorio de 22 caracteres supera 10 sin problema
_HOST_RE: Final = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\Z")


class Nip46Request(BaseModel):
    """Solicitud NIP-46 (ya descifrada): `{"id", "method", "params"}`. Todos los parámetros son cadenas."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    id: str = Field(min_length=1, max_length=64)
    method: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    params: list[str] = Field(default_factory=list, max_length=8)


class Nip46Response(BaseModel):
    """Respuesta NIP-46: `{"id", "result"}` y `error` solo si lo hay."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    id: str = Field(min_length=1, max_length=64)
    result: str
    error: str | None = None

    @classmethod
    def ok(cls, request_id: str, result: str) -> Self:
        return cls(id=request_id, result=result)

    @classmethod
    def fail(cls, request_id: str, message: str) -> Self:
        """Respuesta de error. `result` va como `error`: el comportamiento verificado con NDK 2.12.2 en el laboratorio."""
        return cls(id=request_id, result="error", error=message)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(exclude_none=True), separators=(",", ":"), ensure_ascii=False)


def _parse_message[T: BaseModel](model: type[T], plaintext: object) -> T:
    if not isinstance(plaintext, str) or not plaintext or len(plaintext) > MAX_MESSAGE_CHARS:
        raise InvalidNip46Message("mensaje nip46 invalido")
    try:
        return model.model_validate_json(plaintext, strict=True)
    except (ValidationError, ValueError, RecursionError):
        raise InvalidNip46Message("mensaje nip46 invalido") from None


def parse_request(plaintext: str) -> Nip46Request:
    """Valida el texto plano de una solicitud. Cualquier defecto es un `InvalidNip46Message` que no reproduce el contenido."""
    return _parse_message(Nip46Request, plaintext)


def parse_response(plaintext: str) -> Nip46Response:
    return _parse_message(Nip46Response, plaintext)


def new_connection_secret() -> str:
    """Secreto de conexión: 16 bytes aleatorios del sistema (128 bits) en base64url sin relleno (22 caracteres)."""
    return secrets.token_urlsafe(SECRET_BYTES)


def validate_secret(secret: object) -> str:
    if not isinstance(secret, str) or not _SECRET_RE.match(secret) or len(set(secret)) < _MIN_DISTINCT_SECRET_CHARS:
        raise InvalidBunkerUri("secreto invalido")
    return secret


def validate_relay_url(url: object, *, allow_insecure: bool = False) -> str:
    """Relay `wss://host[:puerto][/ruta]`: sin credenciales, consulta ni fragmento; el nombre de host debe ser válido."""
    if not isinstance(url, str) or not url or len(url) > MAX_RELAY_URL_CHARS or any(ord(c) <= 32 or ord(c) >= 127 for c in url):
        raise InvalidBunkerUri("relay invalido")
    try:
        parts = urlsplit(url)
        _ = parts.port  # lanza ValueError si el puerto es inválido
    except ValueError:
        raise InvalidBunkerUri("relay invalido") from None
    allowed = ("wss", "ws") if allow_insecure else ("wss",)
    if (parts.scheme not in allowed or parts.netloc.endswith(":") or parts.username is not None or parts.password is not None or parts.query or parts.fragment
            or not parts.hostname or not _HOST_RE.match(parts.hostname)):
        raise InvalidBunkerUri("relay invalido")
    return url


@dataclass(frozen=True, slots=True)
class BunkerUri:
    signer_pubkey: str
    relays: tuple[str, ...]
    secret: str | None = field(default=None, repr=False)  # el secreto no aparece en repr ni en registros

    def to_uri(self) -> str:
        query = [f"relay={quote(relay, safe='')}" for relay in self.relays]
        if self.secret is not None:
            query.append(f"secret={quote(self.secret, safe='')}")
        return f"bunker://{self.signer_pubkey}?{'&'.join(query)}"


def build_bunker_uri(signer_pubkey: str, relays: Sequence[str], secret: str, *, allow_insecure_relays: bool = False) -> str:
    """URI `bunker://<pubkey>?relay=...&secret=...`. Valida todo y exige relay y secreto."""
    pubkey = _validated_pubkey(signer_pubkey)
    checked = _validated_relays(relays, allow_insecure_relays)
    return BunkerUri(pubkey, checked, validate_secret(secret)).to_uri()


def parse_bunker_uri(uri: str, *, require_secret: bool = True, allow_insecure_relays: bool = False) -> BunkerUri:
    """Analiza una URI `bunker://` aplicando las reglas del proyecto. Cualquier defecto: `InvalidBunkerUri` sin reproducir la URI."""
    if not isinstance(uri, str) or not uri.isascii() or not 0 < len(uri) <= MAX_URI_CHARS or any(ord(c) <= 32 for c in uri):
        raise InvalidBunkerUri("uri invalida")
    try:
        parts = urlsplit(uri)
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InvalidBunkerUri("uri invalida") from None
    if parts.scheme != "bunker" or parts.path or parts.fragment or not parts.netloc:
        raise InvalidBunkerUri("uri invalida")
    pubkey = _validated_pubkey(parts.netloc)
    relays = [value for key, value in pairs if key == "relay"]
    secrets_found = [value for key, value in pairs if key == "secret"]
    if len(relays) + len(secrets_found) != len(pairs) or len(secrets_found) > 1:
        raise InvalidBunkerUri("uri invalida")
    checked = _validated_relays(relays, allow_insecure_relays)
    if not secrets_found:
        if require_secret:
            raise InvalidBunkerUri("secreto invalido")
        return BunkerUri(pubkey, checked, None)
    return BunkerUri(pubkey, checked, validate_secret(secrets_found[0]))


def _validated_pubkey(value: str) -> str:
    try:
        return require_pubkey(value)
    except InvalidKeyError:
        raise InvalidBunkerUri("clave publica invalida") from None


def _validated_relays(relays: Sequence[str], allow_insecure: bool) -> tuple[str, ...]:
    if isinstance(relays, str) or not 1 <= len(relays) <= MAX_RELAYS:
        raise InvalidBunkerUri("relay invalido")
    checked = tuple(validate_relay_url(relay, allow_insecure=allow_insecure) for relay in relays)
    if len(set(checked)) != len(checked):
        raise InvalidBunkerUri("relay invalido")
    return checked

"""Modelos de la API de control (B3). Entradas estrictas; las salidas nunca incluyen claves, secretos, retos ni eventos completos."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class IdentityImport(StrictIn):
    """Clave privada que el operador aporta EXPLÍCITAMENTE: 64 hexadecimales o `nsec1...`. Nunca se devuelve ni se registra."""

    secret: SecretStr = Field(min_length=8, max_length=200)


class IdentityOut(BaseModel):
    public_key: str


class IdentityStatus(BaseModel):
    present: bool
    public_key: str | None


class SignerOut(BaseModel):
    state: str
    relay_host: str | None
    signatures: int
    max_signatures: int
    end_reason: str | None
    pending: int
    connections_active: int
    connections_pending: int
    connections_unused_secrets: int


class StatusOut(BaseModel):
    identity: IdentityStatus
    signer: SignerOut


class BunkerOut(BaseModel):
    """La URI contiene el secreto de conexión: se entrega UNA vez, con `Cache-Control: no-store`, y no se registra."""

    uri: str
    expires_in_s: int
    relay: str


class RequestOut(BaseModel):
    id: str
    kind: str
    status: str
    client: str
    reason: str | None
    expires_in_s: int
    summary: dict[str, Any]
    checks: list[dict[str, Any]]


class AuditOut(BaseModel):
    entries: list[dict[str, Any]]


class ErrorOut(BaseModel):
    detail: str


class ConnectionOut(BaseModel):
    client: str
    state: str
    expires_in_s: int


class LoginIn(StrictIn):
    """Código de acceso mostrado una vez en la terminal al arrancar. Nunca se devuelve ni se registra."""

    code: SecretStr = Field(min_length=8, max_length=200)


class LoginOut(BaseModel):
    token: str  # JWT (solo para la línea de comandos: la interfaz usa la cookie HttpOnly y NO lo guarda)
    csrf_token: str
    expires_in_s: int


class SessionOut(BaseModel):
    authenticated: bool
    csrf_token: str
    expires_in_s: int

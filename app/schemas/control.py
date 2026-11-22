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
    max_signatures: int | None  # None en modo continuo: no hay tope total (cada firma exige aprobación humana)
    end_reason: str | None
    pending: int
    connections_active: int
    connections_pending: int
    connections_unused_secrets: int
    reconnect_attempt: int | None = None  # solo mientras se reconecta (modo continuo): número del intento (P-49)
    reconnect_max: int | None = None  # total de intentos antes de pasar a «Fallido»


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
    outcome: str | None = None  # P-42: resultado real de una firma aprobada: signed, refused o failed (None = aun sin resultado)
    outcome_reason: str | None = None  # codigo corto y fijo (p. ej. politica_incumplida, aprobacion_caducada)
    sign_expires_in_s: int | None = None  # B6.1D-R3: segundos que quedan para poder FIRMAR (plazo real de la politica); solo en firmas pendientes


class AuditOut(BaseModel):
    entries: list[dict[str, Any]]


class ErrorOut(BaseModel):
    detail: str


class ConnectionOut(BaseModel):
    id: str  # identificador OPACO de la conexión (aleatorio, sin relación con la clave del cliente): lo único que se usa para revocarla
    client: str
    state: str
    expires_in_s: int


class LoginIn(StrictIn):
    """Credenciales del administrador local (D-9). La contraseña no se devuelve ni se registra.

    Las reglas de FORMATO del usuario se validan aquí; la longitud mínima de la contraseña NO (una contraseña corta debe llegar a la verificación y
    dar el mismo 401 que cualquier otra incorrecta, sin diferenciar cuentas). `return_token` es solo para la línea de comandos (ver `LoginOut`).
    """

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    password: SecretStr = Field(min_length=1, max_length=128)
    return_token: bool = False


class LoginOut(BaseModel):
    """Por defecto el JWT viaja SOLO en la cookie HttpOnly (el JavaScript de la interfaz nunca lo recibe). `token` aparece únicamente si el cliente de
    línea de comandos lo pide con `return_token: true` (para usarlo como `Authorization: Bearer`)."""

    csrf_token: str
    expires_in_s: int
    token: str | None = None


class SessionOut(BaseModel):
    authenticated: bool
    csrf_token: str
    expires_in_s: int

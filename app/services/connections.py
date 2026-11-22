"""Conexiones de clientes NIP-46 y secretos de conexión, en memoria.

Estados de un cliente: PENDING (secreto válido, esperando la decisión del operador) → ACTIVE (aprobado) | DENIED. Una conexión ACTIVE caduca
y puede revocarse. Un cliente desconocido solo puede enviar `connect` con un secreto válido. De cada secreto solo se guarda su SHA-256, es de
UN solo uso (se gasta aunque después se deniegue) y caduca. Los secretos en claro nunca se almacenan ni se registran.
"""
import hashlib
import hmac
import secrets
from collections.abc import Callable
from enum import StrEnum

from app.nostr.nip46 import new_connection_secret

MAX_CLIENTS = 256


class ClientState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DENIED = "denied"
    REVOKED = "revoked"


class TooManySecrets(Exception):
    """Hay demasiadas URI sin usar y vigentes."""


class TooManyClients(Exception):
    """Se alcanzó el máximo de clientes distintos registrados en la sesión."""


class UnknownConnection(Exception):
    """El identificador no corresponde a ninguna conexión de este estado (activo del runtime)."""


class ConnectionNotActive(Exception):
    """La conexión existe pero ya no está activa (pendiente, denegada, caducada o revocada): no hay nada que revocar."""


class ConnectionManager:
    def __init__(self, *, now: Callable[[], float], secret_ttl_s: int, connection_ttl_s: int, max_unused_secrets: int = 3) -> None:
        self._now, self._secret_ttl, self._conn_ttl, self._max_unused = now, secret_ttl_s, connection_ttl_s, max_unused_secrets
        self._secrets: dict[str, dict[str, float | bool]] = {}  # sha256(secreto) -> {used, expires}
        self._clients: dict[str, tuple[ClientState, float]] = {}  # clave del cliente -> (estado, caducidad de la conexión)
        # Identificadores OPACOS de conexión (D-17): aleatorios, sin relación con la clave del cliente; son lo único que la API y la interfaz usan para
        # referirse a una conexión (p. ej. para revocarla). Acotados por `MAX_CLIENTS`: se borran junto con el cliente.
        self._ids: dict[str, str] = {}  # clave del cliente -> id
        self._by_id: dict[str, str] = {}  # id -> clave del cliente

    # ----------------------------------------------------------------------------- secretos
    def issue_secret(self) -> str:
        """Secreto nuevo de 128 bits para una URI. Lo devuelve en claro UNA vez; solo guarda su hash."""
        now = self._now()
        self._secrets = {h: m for h, m in self._secrets.items() if not m["used"] and float(m["expires"]) > now}
        if len(self._secrets) >= self._max_unused:
            raise TooManySecrets
        secret = new_connection_secret()
        self._secrets[hashlib.sha256(secret.encode("utf-8")).hexdigest()] = {"used": False, "expires": now + self._secret_ttl}
        return secret

    def consume_secret(self, provided: object) -> bool:
        """True si el secreto es válido, vigente y no usado; lo gasta. Comparación en tiempo constante, sin cortocircuito."""
        digest = hashlib.sha256((provided if isinstance(provided, str) else "").encode("utf-8")).hexdigest()
        now, match = self._now(), None
        for known, meta in self._secrets.items():
            if hmac.compare_digest(known, digest) and not meta["used"] and float(meta["expires"]) > now:
                match = known
        if match is None:
            return False
        self._secrets[match]["used"] = True
        return True

    # ----------------------------------------------------------------------------- clientes
    def state_of(self, client: str) -> ClientState | None:
        entry = self._clients.get(client)
        if entry is None:
            return None
        state, expires = entry
        if state is ClientState.ACTIVE and expires <= self._now():
            self._clients[client] = (ClientState.REVOKED, 0.0)
            return ClientState.REVOKED
        return state

    def is_active(self, client: str) -> bool:
        return self.state_of(client) is ClientState.ACTIVE

    def begin(self, client: str) -> None:
        if client not in self._clients and len(self._clients) >= MAX_CLIENTS:
            raise TooManyClients
        self._clients[client] = (ClientState.PENDING, 0.0)
        self._new_id(client)  # cada emparejamiento recibe un id NUEVO

    def _new_id(self, client: str) -> str:
        """Id opaco de 72 bits aleatorios (12 caracteres URL-safe), sin relación alguna con la clave del cliente. Sustituye al anterior si lo hubiera."""
        self._by_id.pop(self._ids.pop(client, ""), None)
        while (connection_id := secrets.token_urlsafe(9)) in self._by_id:  # la comprobación solo evita una colisión astronómica
            continue
        self._ids[client], self._by_id[connection_id] = connection_id, client
        return connection_id

    def _ensure_id(self, client: str) -> None:
        if client not in self._ids:
            self._new_id(client)

    def id_of(self, client: str) -> str | None:
        return self._ids.get(client)

    def revoke(self, connection_id: str) -> str:
        """Revoca UNA conexión activa por su identificador opaco. Devuelve la clave del cliente (uso interno del servicio, nunca de la API).

        `UnknownConnection` si el id no pertenece a este estado; `ConnectionNotActive` si ya no estaba activa (también cuando acaba de caducar).
        """
        client = self._by_id.get(connection_id)
        if client is None:
            raise UnknownConnection
        if self.state_of(client) is not ClientState.ACTIVE:
            raise ConnectionNotActive
        self._clients[client] = (ClientState.REVOKED, 0.0)
        return client

    def activate(self, client: str) -> None:
        self._clients[client] = (ClientState.ACTIVE, self._now() + self._conn_ttl)
        self._ensure_id(client)

    def deny(self, client: str) -> None:
        self._clients[client] = (ClientState.DENIED, 0.0)
        self._ensure_id(client)

    def forget_pending(self) -> int:
        """Olvida a los clientes que siguen PENDING: su aprobación se canceló al cortarse la sesión y no deben quedar a medias al reanudar. Nunca estuvieron
        autorizados y su secreto ya se gastó, así que solo pueden volver a conectar con una URI nueva (sin quedar DENIED para siempre). Devuelve cuántos."""
        pending = [c for c, (state, _expires) in self._clients.items() if state is ClientState.PENDING]
        for client in pending:
            del self._clients[client]
            self._by_id.pop(self._ids.pop(client, ""), None)
        return len(pending)

    def revoke_all(self) -> None:
        self._clients = {c: (ClientState.REVOKED, 0.0) for c in self._clients}
        self._secrets.clear()

    def counts(self) -> dict[str, int]:
        states = [self.state_of(c) for c in list(self._clients)]
        return {"active": states.count(ClientState.ACTIVE), "pending": states.count(ClientState.PENDING),
                "unused_secrets": sum(1 for m in self._secrets.values() if not m["used"] and float(m["expires"]) > self._now())}

    def snapshot(self) -> list[dict[str, str | int]]:
        """Vista para la API: id opaco, cliente truncado, estado y segundos restantes de una conexión activa."""
        now = self._now()
        view: list[dict[str, str | int]] = []
        for client in list(self._clients):
            state = self.state_of(client)
            if state is None:
                continue
            _state, expires = self._clients[client]
            left = max(0, round(expires - now)) if state is ClientState.ACTIVE else 0
            view.append({"id": self._ids.get(client, ""), "client": client[:8], "state": state.value, "expires_in_s": left})
        return view

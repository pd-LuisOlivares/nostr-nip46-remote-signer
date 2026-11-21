"""Autenticación del operador con JWT (decisión D-8, reemplaza a D-4). Local y monousuario; sin base de datos ni usuarios.

Diseño: al arrancar se genera un CÓDIGO DE ACCESO aleatorio (se muestra una vez en la terminal; aquí solo se conserva su SHA-256) y una CLAVE DE FIRMA
aleatoria de 384 bits que vive solo en memoria. `login()` canjea el código por un JWT HS256 de vida corta con `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`,
`jti` y un `csrf` propio. El servidor recuerda los `jti` activos: cerrar sesión revoca el token y reiniciar el proceso invalida todos (clave nueva y
memoria vacía). Este módulo no depende de FastAPI. Nada de lo que contiene (código, clave, tokens) se registra.
"""
import hashlib
import hmac
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import jwt

ISSUER: Final = "nostr-nip46-remote-signer"
AUDIENCE: Final = "operator-api"
SUBJECT: Final = "operator"
ALGORITHM: Final = "HS256"  # lista cerrada: nunca se acepta `none` ni otro algoritmo
REQUIRED_CLAIMS: Final = ("exp", "iat", "nbf", "iss", "aud", "sub", "jti", "csrf")
MAX_FAILURES: Final = 10  # fallos de autenticación por ventana antes de responder 429
FAILURE_WINDOW_S: Final = 60.0
MAX_SESSIONS: Final = 8


class AuthError(Exception):
    """Credencial o token inválido, vencido o revocado (sin detalle hacia el cliente)."""


class RateLimited(Exception):
    """Demasiados fallos recientes."""


@dataclass(frozen=True, slots=True)
class Session:
    jti: str
    csrf: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    csrf: str
    expires_in_s: int


def new_access_code() -> str:
    return secrets.token_urlsafe(24)


class OperatorAuth:
    def __init__(self, access_code: str, *, ttl_s: int, now: Callable[[], float] = time.time, monotonic: Callable[[], float] = time.monotonic) -> None:
        if len(access_code) < 16 or ttl_s <= 0:
            raise ValueError("configuracion de autenticacion invalida")
        self._digest = hashlib.sha256(access_code.encode("utf-8")).digest()
        self._key = secrets.token_bytes(48)  # clave de firma: solo en memoria, distinta en cada arranque
        self._ttl, self._now, self._mono = ttl_s, now, monotonic
        self._sessions: dict[str, Session] = {}
        self._failures: deque[float] = deque()

    # ------------------------------------------------------------------------------------------ límite de fallos
    def note_failure(self) -> None:
        self._failures.append(self._mono())

    def limited(self) -> bool:
        cutoff = self._mono() - FAILURE_WINDOW_S
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        return len(self._failures) > MAX_FAILURES

    # ------------------------------------------------------------------------------------------ inicio y cierre de sesión
    def check_code(self, code: object) -> bool:
        candidate = hashlib.sha256((code if isinstance(code, str) else "").encode("utf-8")).digest()
        return hmac.compare_digest(self._digest, candidate) and isinstance(code, str)

    def login(self, code: object) -> IssuedToken:
        if not self.check_code(code):
            self.note_failure()
            raise AuthError
        now = int(self._now())
        self._purge(now)
        if len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions.values(), key=lambda s: s.expires_at)
            self._sessions.pop(oldest.jti, None)
        session = Session(secrets.token_urlsafe(16), secrets.token_urlsafe(24), float(now + self._ttl))
        self._sessions[session.jti] = session
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": SUBJECT, "iat": now, "nbf": now, "exp": now + self._ttl, "jti": session.jti, "csrf": session.csrf}
        return IssuedToken(jwt.encode(claims, self._key, algorithm=ALGORITHM), session.csrf, self._ttl)

    def verify(self, token: object) -> Session:
        """Valida firma, algoritmo, caducidad, claims y que la sesión siga activa. Cualquier fallo es `AuthError` y cuenta como fallo."""
        try:
            if not isinstance(token, str) or not 20 <= len(token) <= 2048:
                raise AuthError
            claims = jwt.decode(token, self._key, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER, leeway=0,
                                options={"require": list(REQUIRED_CLAIMS), "verify_signature": True})
            jti, csrf = claims["jti"], claims["csrf"]
            if claims["sub"] != SUBJECT or not isinstance(jti, str) or not isinstance(csrf, str):
                raise AuthError
            session = self._sessions.get(jti)
            if session is None or session.expires_at <= self._now() or not hmac.compare_digest(session.csrf, csrf):
                raise AuthError
        except (jwt.PyJWTError, AuthError, KeyError):
            self.note_failure()
            raise AuthError from None
        return session

    def revoke(self, jti: str) -> None:
        self._sessions.pop(jti, None)

    def revoke_all(self) -> None:
        self._sessions.clear()

    def _purge(self, now: float) -> None:
        self._sessions = {j: s for j, s in self._sessions.items() if s.expires_at > now}

    def remaining_s(self, session: Session) -> int:
        return max(0, round(session.expires_at - self._now()))

    @property
    def ttl_s(self) -> int:
        return self._ttl

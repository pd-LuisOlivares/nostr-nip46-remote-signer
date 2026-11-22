"""Sesión del operador con JWT (decisión D-8; el ingreso con usuario y contraseña de SQLite es la decisión D-9). Local y monousuario. Sin FastAPI.

Diseño: la clave de firma es aleatoria de 384 bits, nace al arrancar y vive solo en memoria (nunca se deriva de la contraseña ni se guarda). Cuando el
llamador ya verificó usuario y contraseña (`AdminAccounts`), `issue()` emite un JWT HS256 de vida corta con `iss`, `aud`, `sub`, `iat`, `nbf`, `exp`,
`jti` y un `csrf` propio. El servidor recuerda los `jti` activos: cerrar sesión revoca el token y reiniciar el proceso invalida todos (clave nueva y
memoria vacía). Nada de lo que contiene (claves, tokens) se registra.

Límites de fallos (P-35), dos contadores INDEPENDIENTES y GLOBALES (no dependen de ninguna cabecera que el cliente pueda cambiar):
- intentos de inicio de sesión: cada intento cuenta desde que empieza (los simultáneos también) y se descuenta solo si tiene éxito; al llegar a
  `MAX_LOGIN_FAILURES` en la ventana se responde 429 aunque la contraseña sea correcta;
- tokens presentes pero inválidos (caducados, revocados, falsificados): frenan solo a quien los envía. Una petición SIN credenciales (la sonda normal de la
  interfaz) no cuenta como fallo de nada, y un token válido nunca se frena.
"""
import math
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
MAX_LOGIN_FAILURES: Final = 5  # intentos de inicio de sesión fallidos (o en curso) por ventana antes de responder 429
LOGIN_WINDOW_S: Final = 300.0
MAX_TOKEN_FAILURES: Final = 20  # tokens inválidos por ventana antes de responder 429 a quien los envía
TOKEN_WINDOW_S: Final = 60.0
MAX_SESSIONS: Final = 8


class AuthError(Exception):
    """Token inválido, vencido o revocado (sin detalle hacia el cliente)."""


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
    jti: str  # identificador de la sesión (no es secreto por sí solo; sirve para el registro y la revocación)


class SlidingWindow:
    """Marcas de tiempo (reloj monótono) dentro de una ventana deslizante."""

    def __init__(self, max_events: int, window_s: float, monotonic: Callable[[], float]) -> None:
        self._max, self._window, self._mono = max_events, window_s, monotonic
        self._stamps: deque[float] = deque()

    def _purge(self) -> None:
        cutoff = self._mono() - self._window
        while self._stamps and self._stamps[0] <= cutoff:
            self._stamps.popleft()

    def add(self) -> float:
        stamp = self._mono()
        self._stamps.append(stamp)
        return stamp

    def discard(self, stamp: float) -> None:
        try:
            self._stamps.remove(stamp)
        except ValueError:
            pass  # ya salió de la ventana

    def full(self) -> bool:
        self._purge()
        return len(self._stamps) >= self._max

    def retry_after_s(self) -> int:
        self._purge()
        if not self._stamps:
            return 1
        return max(1, math.ceil(self._stamps[0] + self._window - self._mono()))


class OperatorAuth:
    def __init__(self, *, ttl_s: int, now: Callable[[], float] = time.time, monotonic: Callable[[], float] = time.monotonic) -> None:
        if ttl_s <= 0:
            raise ValueError("configuracion de autenticacion invalida")
        self._key = secrets.token_bytes(48)  # clave de firma: solo en memoria, distinta en cada arranque; independiente de cualquier contraseña
        self._ttl, self._now = ttl_s, now
        self._sessions: dict[str, Session] = {}
        self._logins = SlidingWindow(MAX_LOGIN_FAILURES, LOGIN_WINDOW_S, monotonic)
        self._token_failures = SlidingWindow(MAX_TOKEN_FAILURES, TOKEN_WINDOW_S, monotonic)

    # ------------------------------------------------------------------------------------------ límite de intentos de inicio de sesión
    def login_limited(self) -> bool:
        return self._logins.full()

    def login_retry_after_s(self) -> int:
        return self._logins.retry_after_s()

    def reserve_login_attempt(self) -> float:
        """Registra el intento ANTES de verificar la contraseña (así una ráfaga concurrente no supera el límite). Se libera solo si tiene éxito."""
        return self._logins.add()

    def release_login_attempt(self, stamp: float) -> None:
        self._logins.discard(stamp)

    # ------------------------------------------------------------------------------------------ límite de tokens inválidos
    def token_limited(self) -> bool:
        return self._token_failures.full()

    def token_retry_after_s(self) -> int:
        return self._token_failures.retry_after_s()

    # ------------------------------------------------------------------------------------------ emisión, verificación y revocación
    def issue(self) -> IssuedToken:
        """Emite el JWT de una sesión nueva. El llamador YA verificó usuario y contraseña."""
        now = int(self._now())
        self._purge(now)
        if len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions.values(), key=lambda s: s.expires_at)
            self._sessions.pop(oldest.jti, None)
        session = Session(secrets.token_urlsafe(16), secrets.token_urlsafe(24), float(now + self._ttl))
        self._sessions[session.jti] = session
        claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": SUBJECT, "iat": now, "nbf": now, "exp": now + self._ttl, "jti": session.jti, "csrf": session.csrf}
        return IssuedToken(jwt.encode(claims, self._key, algorithm=ALGORITHM), session.csrf, self._ttl, session.jti)

    def verify(self, token: object) -> Session:
        """Valida firma, algoritmo, caducidad, claims y que la sesión siga activa. Cualquier fallo es `AuthError` y cuenta como token inválido."""
        try:
            if not isinstance(token, str) or not 20 <= len(token) <= 2048:
                raise AuthError
            claims = jwt.decode(token, self._key, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER, leeway=0,
                                options={"require": list(REQUIRED_CLAIMS), "verify_signature": True})
            jti, csrf = claims["jti"], claims["csrf"]
            if claims["sub"] != SUBJECT or not isinstance(jti, str) or not isinstance(csrf, str):
                raise AuthError
            session = self._sessions.get(jti)
            if session is None or session.expires_at <= self._now() or not _same(session.csrf, csrf):
                raise AuthError
        except (jwt.PyJWTError, AuthError, KeyError):
            self._token_failures.add()
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


def _same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))

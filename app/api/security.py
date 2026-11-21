"""Seguridad de la capa HTTP: guardia JWT (D-8), validación de `Host` y `Origin`, y cabeceras de seguridad (incluida la CSP).

El JWT puede llegar en la cookie `nip46_session` (HttpOnly, SameSite=Strict; lo usa la interfaz) o en `Authorization: Bearer` (línea de comandos).
Con cookie, las operaciones que cambian estado exigen además la cabecera `X-CSRF-Token` y un `Origin` local; con `Authorization` no hace falta CSRF
porque el navegador no lo envía solo. Nada de esto se registra.
"""
import hmac
import re
from collections.abc import Awaitable, Callable
from typing import Final
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.security.operator_auth import FAILURE_WINDOW_S, AuthError, OperatorAuth, Session

COOKIE_NAME: Final = "nip46_session"
CSRF_HEADER: Final = "x-csrf-token"
_BEARER: Final = re.compile(r"^Bearer ([A-Za-z0-9_.-]{20,2048})\Z")
_SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})
CSP: Final = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; "
              "form-action 'self'; frame-ancestors 'none'")


def host_without_port(value: str) -> str:
    if value.startswith("["):
        return value.split("]", 1)[0] + "]"
    return value.split(":", 1)[0]


def origin_is_local(request: Request, allowed_hosts: frozenset[str]) -> bool:
    """`Origin` ausente = válido (peticiones que no son de navegador o del mismo origen sin cabecera); presente = debe ser local y coincidir con `Host`."""
    origin = request.headers.get("origin")
    if origin is None:
        return True
    parts = urlsplit(origin)
    host = request.headers.get("host", "")
    return (parts.scheme in ("http", "https") and (parts.hostname or "") != "" and host_without_port(parts.netloc).lower() in allowed_hosts
            and parts.netloc.lower() == host.lower())


class JwtGuard:
    """Dependencia de FastAPI: todo endpoint protegido la usa (denegar por defecto)."""

    def __init__(self, auth: OperatorAuth, allowed_hosts: tuple[str, ...]) -> None:
        self.auth = auth
        self._hosts = frozenset(h.lower() for h in allowed_hosts)

    def _reject(self, status: int, detail: str) -> HTTPException:
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return HTTPException(status_code=status, detail=detail, headers=headers)

    async def __call__(self, request: Request) -> Session:
        header = request.headers.get("authorization")
        from_cookie = header is None
        match = _BEARER.match(header) if header is not None else None
        token = request.cookies.get(COOKIE_NAME) if from_cookie else (match.group(1) if match else None)
        try:
            session = self.auth.verify(token)
        except AuthError:
            if self.auth.limited():  # un token valido sigue funcionando; solo se frena a quien falla repetidamente
                raise HTTPException(status_code=429, detail="demasiados intentos", headers={"Retry-After": str(int(FAILURE_WINDOW_S))}) from None
            raise self._reject(401, "no autorizado") from None
        if from_cookie and request.method not in _SAFE_METHODS:
            sent = request.headers.get(CSRF_HEADER, "")
            if not origin_is_local(request, self._hosts) or not hmac.compare_digest(sent.encode("utf-8"), session.csrf.encode("utf-8")):
                raise self._reject(403, "solicitud no permitida")
        request.state.session = session
        return session


class LocalHostMiddleware(BaseHTTPMiddleware):
    """Rechaza peticiones cuya cabecera Host no sea una de las admitidas (defensa frente a DNS rebinding: la API es solo local) y añade cabeceras."""

    def __init__(self, app: ASGIApp, allowed_hosts: tuple[str, ...]) -> None:
        super().__init__(app)
        self._allowed = frozenset(h.lower() for h in allowed_hosts)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if host_without_port(request.headers.get("host", "")).lower() not in self._allowed:
            return JSONResponse({"detail": "host no permitido"}, status_code=400)
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), clipboard-read=()")
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

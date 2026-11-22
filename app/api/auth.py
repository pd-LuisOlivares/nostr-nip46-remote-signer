"""Inicio y cierre de sesión del operador (D-8, D-9). Usuario y contraseña (SQLite + Argon2id) se canjean por un JWT en una cookie HttpOnly.

El JWT lo genera el servidor tras verificar las credenciales; el navegador no copia ni recibe ningún token (solo la cookie, que el JavaScript no puede
leer). Respuesta única e idéntica (401) para usuario inexistente y contraseña incorrecta. Registro mínimo en `nip46.auth`: sin usuario, contraseña,
hash, token ni cookie.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.security import COOKIE_NAME, JwtGuard, origin_is_local
from app.schemas.control import ErrorOut, LoginIn, LoginOut, SessionOut
from app.security.operator_auth import Session
from app.security.verification_gate import Busy, VerificationGate
from app.services.admin_accounts import AdminAccounts
from app.storage.database import StorageError

log = logging.getLogger("nip46.auth")


def build_auth_router(guard: JwtGuard, accounts: AdminAccounts, gate: VerificationGate, *, cookie_secure: bool, allowed_hosts: tuple[str, ...]) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    hosts = frozenset(h.lower() for h in allowed_hosts)
    Current = Annotated[Session, Depends(guard)]

    @router.post("/login", response_model=LoginOut, response_model_exclude_none=True,
                 responses={401: {"model": ErrorOut}, 403: {"model": ErrorOut}, 429: {"model": ErrorOut}, 503: {"model": ErrorOut}})
    async def login(body: LoginIn, request: Request, response: Response) -> LoginOut:
        if not origin_is_local(request, hosts):
            raise HTTPException(403, "solicitud no permitida")
        auth = guard.auth
        if auth.login_limited():
            retry = auth.login_retry_after_s()
            log.warning("auth event=login_blocked retry_after_s=%d", retry)
            raise HTTPException(429, "demasiados intentos", headers={"Retry-After": str(retry)})
        stamp = auth.reserve_login_attempt()  # cuenta como fallo hasta que se demuestre lo contrario (ráfagas concurrentes incluidas)
        try:
            # P-41: UNA verificación Argon2id activa por proceso (cola acotada y espera máxima). Cubre usuario existente e inexistente (mismo costo).
            valid = await gate.run(accounts.authenticate, body.username, body.password.get_secret_value())
        except Busy:
            auth.release_login_attempt(stamp)  # no se llegó a verificar nada: no es un fallo de credenciales y no da ventaja de fuerza bruta
            log.warning("auth event=login_busy")
            raise HTTPException(503, "servicio ocupado", headers={"Retry-After": "2"}) from None
        except StorageError:
            log.error("auth event=login_error reason=storage")
            raise HTTPException(503, "servicio no disponible") from None
        if not valid:
            log.warning("auth event=login_failed")
            raise HTTPException(401, "credenciales invalidas", headers={"WWW-Authenticate": "Bearer"})
        auth.release_login_attempt(stamp)
        issued = auth.issue()
        log.info("auth event=login_ok session=%s", issued.jti[:8])
        response.set_cookie(COOKIE_NAME, issued.token, max_age=issued.expires_in_s, path="/api", httponly=True, samesite="strict", secure=cookie_secure)
        response.headers["Cache-Control"] = "no-store"
        return LoginOut(csrf_token=issued.csrf, expires_in_s=issued.expires_in_s, token=issued.token if body.return_token else None)

    @router.get("/session", response_model=SessionOut, responses={401: {"model": ErrorOut}})
    async def session(current: Current) -> SessionOut:
        return SessionOut(authenticated=True, csrf_token=current.csrf, expires_in_s=guard.auth.remaining_s(current))

    @router.post("/logout", status_code=204, responses={401: {"model": ErrorOut}, 403: {"model": ErrorOut}})
    async def logout(current: Current, response: Response) -> None:
        guard.auth.revoke(current.jti)
        log.info("auth event=logout session=%s", current.jti[:8])
        response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, samesite="strict", secure=cookie_secure)

    return router

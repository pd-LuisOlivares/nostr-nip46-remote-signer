"""Inicio y cierre de sesión del operador (D-8). El código de acceso se canjea por un JWT en una cookie HttpOnly; no hay credenciales fijas."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.security import COOKIE_NAME, JwtGuard, origin_is_local
from app.schemas.control import ErrorOut, LoginIn, LoginOut, SessionOut
from app.security.operator_auth import FAILURE_WINDOW_S, AuthError, Session


def build_auth_router(guard: JwtGuard, *, cookie_secure: bool, allowed_hosts: tuple[str, ...]) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    hosts = frozenset(h.lower() for h in allowed_hosts)
    Current = Annotated[Session, Depends(guard)]

    @router.post("/login", response_model=LoginOut, responses={401: {"model": ErrorOut}, 403: {"model": ErrorOut}, 429: {"model": ErrorOut}})
    async def login(body: LoginIn, request: Request, response: Response) -> LoginOut:
        if not origin_is_local(request, hosts):
            raise HTTPException(403, "solicitud no permitida")
        if guard.auth.limited():
            raise HTTPException(429, "demasiados intentos", headers={"Retry-After": str(int(FAILURE_WINDOW_S))})
        try:
            issued = guard.auth.login(body.code.get_secret_value())
        except AuthError:
            raise HTTPException(401, "no autorizado", headers={"WWW-Authenticate": "Bearer"}) from None
        response.set_cookie(COOKIE_NAME, issued.token, max_age=issued.expires_in_s, path="/api", httponly=True, samesite="strict", secure=cookie_secure)
        response.headers["Cache-Control"] = "no-store"
        return LoginOut(token=issued.token, csrf_token=issued.csrf, expires_in_s=issued.expires_in_s)

    @router.get("/session", response_model=SessionOut, responses={401: {"model": ErrorOut}})
    async def session(current: Current) -> SessionOut:
        return SessionOut(authenticated=True, csrf_token=current.csrf, expires_in_s=guard.auth.remaining_s(current))

    @router.post("/logout", status_code=204, responses={401: {"model": ErrorOut}, 403: {"model": ErrorOut}})
    async def logout(current: Current, response: Response) -> None:
        guard.auth.revoke(current.jti)
        response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, samesite="strict", secure=cookie_secure)

    return router

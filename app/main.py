import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import build_auth_router
from app.api.control import build_router
from app.api.health import router as health_router
from app.api.security import JwtGuard, LocalHostMiddleware
from app.config import Settings
from app.security.operator_auth import OperatorAuth, new_access_code
from app.services.runtime import RelayFactory, SignerRuntime, default_relay_factory

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None, *, access_code: str | None = None, relay_factory: RelayFactory = default_relay_factory,
               announce_code: bool = True) -> FastAPI:
    """Construye la aplicación: `/health`, la interfaz web (`/`), el inicio de sesión del operador y la API local de control (JWT, D-8).

    El código de acceso se genera al arrancar (o se recibe, solo en pruebas) y se muestra UNA vez en la terminal; nunca se escribe en archivos.
    """
    cfg = settings or Settings.from_env(os.environ)
    code = access_code or new_access_code()
    runtime = SignerRuntime(cfg, relay_factory=relay_factory)
    auth = OperatorAuth(code, ttl_s=cfg.jwt_ttl_s)
    guard = JwtGuard(auth, cfg.allowed_hosts)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if announce_code:
            sys.stdout.write(f"\n[operador] Codigo de acceso de ESTA ejecucion (se muestra una sola vez; no se guarda): {code}\n"
                             "[operador] Abra la interfaz en esta direccion y escribalo en el formulario de inicio de sesion.\n\n")
            sys.stdout.flush()
        try:
            yield
        finally:
            auth.revoke_all()
            await runtime.shutdown()  # parada ordenada con evidencia de cierre

    application = FastAPI(title="nostr-nip46-remote-signer", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    application.state.runtime = runtime
    application.state.auth = auth
    application.add_middleware(LocalHostMiddleware, allowed_hosts=cfg.allowed_hosts)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Sin `input` ni valores: una clave o un codigo mal formados no deben reaparecer en la respuesta.
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        return JSONResponse({"detail": "solicitud invalida", "fields": fields}, status_code=422)

    application.include_router(health_router)
    application.include_router(build_auth_router(guard, cookie_secure=cfg.cookie_secure, allowed_hosts=cfg.allowed_hosts))
    application.include_router(build_router(guard))
    application.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")  # interfaz web (B5): solo archivos estaticos
    return application


app = create_app()

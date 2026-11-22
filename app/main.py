import asyncio
import logging
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
from app.logging_config import configure_logging
from app.security.operator_auth import OperatorAuth
from app.security.passwords import PasswordService
from app.security.verification_gate import VerificationGate
from app.services.admin_accounts import AdminAccounts, AdminBootstrapError
from app.services.runtime import RelayFactory, SignerRuntime, default_relay_factory
from app.storage.admins import AdminRepository
from app.storage.database import Database, StorageError
from app.storage.secret_file import read_password_file

STATIC_DIR = Path(__file__).resolve().parent / "static"
log = logging.getLogger("nip46.auth")


def create_app(settings: Settings | None = None, *, relay_factory: RelayFactory = default_relay_factory, passwords: PasswordService | None = None,
               gate: VerificationGate | None = None) -> FastAPI:
    """Construye la aplicación: `/health`, la interfaz web (`/`), el inicio de sesión del administrador y la API local de control (D-8, D-9).

    Construirla NO toca el disco: la base SQLite se crea y el administrador inicial se prepara al ARRANCAR (lifespan). Si no hay administrador y falta
    una contraseña inicial válida, el arranque falla con instrucciones. `passwords` solo se inyecta en pruebas (parámetros de Argon2 reducidos).
    """
    cfg = settings or Settings.from_env(os.environ)
    runtime = SignerRuntime(cfg, relay_factory=relay_factory)
    auth = OperatorAuth(ttl_s=cfg.jwt_ttl_s)
    database = Database(cfg.database_path)
    accounts = AdminAccounts(database, AdminRepository(database), passwords or PasswordService())
    guard = JwtGuard(auth, cfg.allowed_hosts)

    def initial_password() -> str | None:
        if cfg.admin_password:
            return cfg.admin_password
        return read_password_file(cfg.admin_password_file) if cfg.admin_password_file else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        try:
            await asyncio.to_thread(accounts.prepare, cfg.admin_username, initial_password)
        except (AdminBootstrapError, StorageError) as exc:
            log.error("auth event=startup_failed reason=%s", type(exc).__name__)
            sys.stderr.write(f"\n[arranque] {exc}\n\n")  # mensajes seguros por construcción: sin contraseña, hash ni ruta
            sys.stderr.flush()
            raise
        try:
            yield
        finally:
            auth.revoke_all()
            await runtime.shutdown()  # parada ordenada con evidencia de cierre

    application = FastAPI(title="nostr-nip46-remote-signer", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    application.state.runtime = runtime
    application.state.auth = auth
    application.state.accounts = accounts
    application.add_middleware(LocalHostMiddleware, allowed_hosts=cfg.allowed_hosts)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Sin `input` ni valores: una clave o una contraseña mal formadas no deben reaparecer en la respuesta.
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        return JSONResponse({"detail": "solicitud invalida", "fields": fields}, status_code=422)

    application.include_router(health_router)
    application.include_router(build_auth_router(guard, accounts, gate or VerificationGate(), cookie_secure=cfg.cookie_secure, allowed_hosts=cfg.allowed_hosts))
    application.include_router(build_router(guard))
    application.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")  # interfaz web (B5): solo archivos estaticos
    return application


app = create_app()

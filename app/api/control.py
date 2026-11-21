"""API local de control (B3): identidad, firmante, URI bunker://, solicitudes pendientes y auditoría. Solo validación y delegación.

TODOS los endpoints exigen una sesión JWT de operador (dependencia a nivel de router: denegar por defecto). Errores genéricos y estables; nunca se
devuelven claves, secretos, retos ni eventos completos. La URI `bunker://` solo viaja en la respuesta de `POST /api/connections`.
"""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from app.api.security import JwtGuard
from app.nostr.errors import InvalidKeyError
from app.nostr.keys import Keypair
from app.schemas.control import AuditOut, BunkerOut, ConnectionOut, ErrorOut, IdentityImport, IdentityOut, RequestOut, StatusOut
from app.services.approvals import AlreadyResolved, UnknownRequest
from app.services.connections import TooManySecrets
from app.services.runtime import AlreadyRunning, NoIdentity, NotRunning, SignerRuntime, StartFailed
from app.services.signer import NotReady, SignerState

RequestId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
_ERRORS: dict[int | str, dict[str, Any]] = {401: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def runtime_of(request: Request) -> SignerRuntime:
    runtime: SignerRuntime = request.app.state.runtime
    return runtime


def build_router(guard: JwtGuard) -> APIRouter:
    router = APIRouter(prefix="/api", dependencies=[Depends(guard)], responses={401: {"model": ErrorOut}})
    Runtime = Annotated[SignerRuntime, Depends(runtime_of)]

    @router.get("/status", response_model=StatusOut)
    async def status(runtime: Runtime) -> dict[str, object]:
        return runtime.status()

    # ----------------------------------------------------------------------------- identidad
    @router.get("/identity", response_model=IdentityOut, responses={404: {"model": ErrorOut}})
    async def get_identity(runtime: Runtime) -> IdentityOut:
        if runtime.public_key is None:
            raise HTTPException(404, "sin identidad")
        return IdentityOut(public_key=runtime.public_key)

    @router.post("/identity", response_model=IdentityOut, status_code=201, responses={409: {"model": ErrorOut}})
    async def create_identity(runtime: Runtime) -> IdentityOut:
        """Identidad temporal NUEVA, solo en memoria. Devuelve únicamente la clave pública."""
        try:
            return IdentityOut(public_key=runtime.set_identity(Keypair.generate()))
        except AlreadyRunning:
            raise HTTPException(409, "detenga el firmante antes de cambiar la identidad") from None

    @router.put("/identity", response_model=IdentityOut, responses={400: {"model": ErrorOut}, 409: {"model": ErrorOut}})
    async def import_identity(body: IdentityImport, runtime: Runtime) -> IdentityOut:
        """Importa la clave que el operador proporciona (hex o nsec). No se devuelve, no se registra y no se escribe en disco."""
        try:
            keypair = Keypair.from_secret_input(body.secret.get_secret_value())
            return IdentityOut(public_key=runtime.set_identity(keypair))
        except InvalidKeyError:
            raise HTTPException(400, "clave invalida") from None
        except AlreadyRunning:
            raise HTTPException(409, "detenga el firmante antes de cambiar la identidad") from None

    # ----------------------------------------------------------------------------- firmante
    @router.get("/signer")
    async def signer_status(runtime: Runtime) -> dict[str, object]:
        signer: dict[str, object] = runtime.status()["signer"]
        return signer

    @router.post("/signer/start", responses={**_ERRORS, 502: {"model": ErrorOut}})
    async def start_signer(runtime: Runtime) -> dict[str, object]:
        try:
            await runtime.start()
        except NoIdentity:
            raise HTTPException(409, "cree o importe una identidad antes de iniciar") from None
        except AlreadyRunning:
            raise HTTPException(409, "el firmante ya esta en marcha") from None
        except StartFailed:
            raise HTTPException(502, "el firmante no llego a estar listo (relay)") from None
        signer: dict[str, object] = runtime.status()["signer"]
        return signer

    @router.post("/signer/stop", responses=_ERRORS)
    async def stop_signer(runtime: Runtime) -> dict[str, object]:
        if not runtime.running:
            raise HTTPException(409, "el firmante no esta en marcha")
        try:
            await runtime.stop()
        except NotRunning:
            raise HTTPException(409, "el firmante no esta en marcha") from None
        signer: dict[str, object] = runtime.status()["signer"]
        return signer

    @router.post("/connections", response_model=BunkerOut, status_code=201, responses={**_ERRORS, 429: {"model": ErrorOut}})
    async def issue_connection(runtime: Runtime, response: Response) -> BunkerOut:
        """Emite una URI `bunker://` de un solo uso. Se muestra UNA vez: no se vuelve a consultar ni se registra."""
        service = runtime.service
        if service is None or service.state is not SignerState.READY:
            raise HTTPException(409, "el firmante no esta listo")
        try:
            uri = service.issue_bunker_uri()
        except NotReady:
            raise HTTPException(409, "el firmante no esta listo") from None
        except TooManySecrets:
            raise HTTPException(429, "demasiadas URI sin usar") from None
        response.headers["Cache-Control"] = "no-store"
        return BunkerOut(uri=uri, expires_in_s=runtime.settings.secret_ttl_s, relay=runtime.settings.relay_url)

    @router.get("/connections", response_model=list[ConnectionOut])
    async def list_connections(runtime: Runtime) -> list[ConnectionOut]:
        """Clientes conocidos en la sesión actual (identificador truncado y estado); nunca secretos ni claves completas."""
        service = runtime.service
        return [ConnectionOut(client=str(c["client"]), state=str(c["state"]), expires_in_s=int(c["expires_in_s"])) for c in (service.connections.snapshot() if service else [])]

    # ----------------------------------------------------------------------------- solicitudes
    @router.get("/requests", response_model=list[RequestOut])
    async def list_requests(runtime: Runtime, scope: Annotated[Literal["pending", "recent", "all"], Query()] = "pending") -> list[RequestOut]:
        now = runtime.now()
        return [RequestOut(**r.public(now)) for r in runtime.requests(scope)]

    async def _decide(request_id: str, approve: bool, runtime: SignerRuntime) -> RequestOut:
        service = runtime.service
        if service is None:
            raise HTTPException(404, "solicitud desconocida")
        try:
            req = service.approvals.resolve(request_id, approve)
        except UnknownRequest:
            raise HTTPException(404, "solicitud desconocida") from None
        except AlreadyResolved:
            raise HTTPException(409, "la solicitud ya se resolvio o caduco") from None
        return RequestOut(**req.public(runtime.now()))

    @router.post("/requests/{request_id}/approve", response_model=RequestOut, responses={**_ERRORS, 404: {"model": ErrorOut}})
    async def approve(request_id: RequestId, runtime: Runtime) -> RequestOut:
        return await _decide(request_id, True, runtime)

    @router.post("/requests/{request_id}/deny", response_model=RequestOut, responses={**_ERRORS, 404: {"model": ErrorOut}})
    async def deny(request_id: RequestId, runtime: Runtime) -> RequestOut:
        return await _decide(request_id, False, runtime)

    # ----------------------------------------------------------------------------- auditoría
    @router.get("/audit", response_model=AuditOut)
    async def audit(runtime: Runtime, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> AuditOut:
        return AuditOut(entries=runtime.audit.entries(limit))

    return router

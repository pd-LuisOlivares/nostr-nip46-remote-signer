from fastapi import FastAPI

from app.api.health import router as health_router


def create_app() -> FastAPI:
    """Construye la aplicación FastAPI y registra los routers."""
    application = FastAPI(title="nostr-nip46-remote-signer")
    application.include_router(health_router)
    return application


app = create_app()

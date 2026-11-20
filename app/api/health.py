from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Liveness del proceso. No consulta relays, Stacker News ni otros servicios."""
    return HealthResponse(status="ok")

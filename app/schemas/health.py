from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Contrato de GET /health: respuesta fija, sin datos internos."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]

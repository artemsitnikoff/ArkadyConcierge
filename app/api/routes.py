import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.schemas import BreakdownRequest, BreakdownResponse, HealthResponse
from app.config import settings
from app.services.concierge_service import BreakdownError, ConciergeService

router = APIRouter()


def get_concierge_service(request: Request) -> ConciergeService:
    service = getattr(request.app.state, "concierge_service", None)
    if service is None:
        # Happens only if a request hits the process before lifespan finished.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "service not ready")
    return service


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Gate HTTP endpoints with a shared secret.

    If `API_KEY` is unset in settings, the endpoint is treated as disabled
    (503) rather than "open to the world" — fail-closed by default.
    """
    expected = settings.api_key.get_secret_value()
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "HTTP API is disabled — set API_KEY in settings to enable",
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse()


@router.post(
    "/concierge/breakdown",
    response_model=BreakdownResponse,
    status_code=status.HTTP_200_OK,
    tags=["concierge"],
    summary="Break a free-form task description into a structured JSON plan",
    dependencies=[Depends(require_api_key)],
)
async def breakdown(
    payload: BreakdownRequest,
    service: ConciergeService = Depends(get_concierge_service),
) -> BreakdownResponse:
    try:
        result = await service.breakdown(payload.text)
    except BreakdownError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    return BreakdownResponse(data=result.data)

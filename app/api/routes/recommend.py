from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.schemas import ErrorResponse, RecommendRequest, RecommendResponse
from app.core.config import Settings, get_settings
from app.pipeline.errors import QueryAnalyzerUnavailableError
from app.pipeline.orchestrator import run_orchestrator

router = APIRouter(prefix="/v1", tags=["recommend"])


def _verify_internal_key(
    settings: Settings = Depends(get_settings),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> None:
    expected = settings.reco_internal_api_key
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def recommend(
    body: RecommendRequest,
    _: None = Depends(_verify_internal_key),
    settings: Settings = Depends(get_settings),
) -> RecommendResponse:
    """
    Corps aligné sur stackai recommendSchema.
    Auth Clerk / quotas / saveStack restent côté Next.js.
    """
    ctx = body.to_user_context()
    try:
        result = await run_orchestrator(ctx, settings)
    except QueryAnalyzerUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc) or "LLM analysis unavailable — retry later",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Recommendation failed") from exc

    if result is None:
        raise HTTPException(status_code=500, detail="Recommendation failed")

    return RecommendResponse.model_validate(result.model_dump())

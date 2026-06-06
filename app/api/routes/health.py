from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings

router = APIRouter(tags=["health"])


def _env_readiness() -> tuple[bool, dict[str, bool]]:
    s = get_settings()
    has_llm = bool((s.cerebras_api_key or "").strip() or (s.groq_api_key or "").strip())
    has_jina = bool((s.jina_api_key or "").strip())
    has_supabase = bool((s.supabase_url or "").strip() and (s.supabase_service_role_key or "").strip())
    checks = {
        "llm": has_llm,
        "jina": has_jina,
        "supabase": has_supabase,
    }
    return all(checks.values()), checks


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness — le process répond."""
    return {"status": "ok", "service": "raspquery-reco"}


@router.get("/health/ready")
async def health_ready() -> JSONResponse:
    """Readiness — variables critiques présentes (sans appeler les APIs externes)."""
    ready, checks = _env_readiness()
    body = {
        "status": "ready" if ready else "degraded",
        "service": "raspquery-reco",
        "checks": checks,
    }
    return JSONResponse(content=body, status_code=200 if ready else 503)

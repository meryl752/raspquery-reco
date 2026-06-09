"""Supabase REST — RPC smart_search_agents_v2 + fallback catégories."""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings
from app.core.models import VectorAgent

logger = logging.getLogger(__name__)

SMART_SEARCH_AGENTS_V2 = "smart_search_agents_v2"
SMART_SEARCH_V2_MATCH_COUNT = 50


class SupabaseNotConfiguredError(RuntimeError):
    pass


def _headers(settings: Settings) -> dict[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SupabaseNotConfiguredError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY manquants"
        )
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _base_url(settings: Settings) -> str:
    return settings.supabase_url.rstrip("/") + "/rest/v1"


def _row_to_vector_agent(row: dict) -> VectorAgent:
    return VectorAgent(
        id=str(row["id"]),
        name=row["name"],
        category=row["category"],
        description=row.get("description") or "",
        price_from=float(row.get("price_from") or 0),
        score=float(row.get("score") or 0),
        roi_score=float(row.get("roi_score") or 0),
        use_cases=row.get("use_cases") or [],
        compatible_with=row.get("compatible_with") or [],
        best_for=row.get("best_for"),
        not_for=row.get("not_for"),
        integrations=row.get("integrations"),
        website_domain=row.get("website_domain"),
        logo_url=row.get("logo_url"),
        website_url=row.get("website_url") or row.get("url"),
        setup_difficulty=row.get("setup_difficulty"),
        time_to_value=row.get("time_to_value"),
        catalog_status=row.get("catalog_status") or "active",
        similarity=float(row.get("similarity") or 0),
    )


async def vector_search_agents(
    settings: Settings,
    embedding: list[float],
    budget_max: int,
    category: str | None = None,
    match_count: int = SMART_SEARCH_V2_MATCH_COUNT,
) -> list[VectorAgent]:
    """RPC smart_search_agents_v2 — aligné stackai/lib/supabase/rpc.ts."""
    url = _base_url(settings) + f"/rpc/{SMART_SEARCH_AGENTS_V2}"
    payload = {
        "query_embedding": embedding,
        "user_budget_max": budget_max or 0,
        "user_category": category,
        "match_count": match_count,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=_headers(settings), json=payload)

    if response.status_code >= 400:
        raise RuntimeError(
            f"RPC {SMART_SEARCH_AGENTS_V2} HTTP {response.status_code}: {response.text[:400]}"
        )

    rows = response.json()
    if not rows:
        return []
    return [_row_to_vector_agent(r) for r in rows]


async def get_agents_by_categories(
    settings: Settings,
    categories: list[str],
) -> list[VectorAgent]:
    """Fallback orchestrateur — table agents filtrée par catégorie."""
    base = _base_url(settings) + "/agents"
    params = "select=*&order=score.desc"
    if categories:
        cats = ",".join(categories)
        params += f"&category=in.({cats})"

    url = f"{base}?{params}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=_headers(settings))

    if response.status_code >= 400:
        logger.error("get_agents_by_categories HTTP %s", response.status_code)
        return []

    rows = response.json()
    return [
        _row_to_vector_agent({**r, "similarity": 1.0})
        for r in (rows or [])
    ]
